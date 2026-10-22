"""Nextflow admission control (P0): admit before launch, warrant after crate.

Does not own the pipeline DAG, does not emit a competing RO-Crate, and does
not start Nextflow when preflight refuses. nf-prov remains the provenance
producer; BioNexus consumes the crate and gates claims.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

from bionexus.ledger import ClaimLedger
from bionexus.nextflow_bridge import (
    NextflowExecutionSummary,
    create_nextflow_tool_receipt,
    harvest_nextflow_run,
)
from bionexus.preflight import PreflightReport, render_preflight, run_preflight
from bionexus.roc_validator import STATUS_VALIDATED
from bionexus.verification import VerificationReport, locate_ledger, verify_ledger

logger = logging.getLogger(__name__)

PathLike = Union[str, Path]
NextflowRunner = Callable[[List[str]], int]

EXIT_OK = 0
EXIT_REFUSED = 1
EXIT_MISSING = 2
EXIT_CLAIMS_REFUSED = 3

ALLOWED_PIPELINES = (
    "rnaseq",
    "scrnaseq",
    "differentialabundance",
    "sarek",
    "spatialtranscriptomics",
    "ampliseq",
)


@dataclass
class AdmitResult:
    """Launch-time gate: whether Nextflow is allowed to start."""

    allowed: bool
    exit_code: int
    rationale: str
    samplesheet_ok: bool
    scientific_admission: str
    preflight: Optional[PreflightReport] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        if self.preflight is not None:
            payload["preflight"] = self.preflight.to_dict()
        return payload


@dataclass
class WarrantResult:
    """Post-run claim gate over nf-prov crate provenance."""

    exit_code: int
    warrant_status: str
    provenance_source: str
    summary: NextflowExecutionSummary
    receipt: Dict[str, Any]
    verification: Optional[VerificationReport] = None
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        if self.warrant_status == "VERIFIED":
            effect = "LEDGER_VERIFIED"
        elif self.warrant_status == "CLAIMS_REFUSED":
            effect = "CLAIMS_REFUSED"
        else:
            effect = "NONE"
        return {
            "exit_code": self.exit_code,
            "warrant_status": self.warrant_status,
            "provenance_source": self.provenance_source,
            "summary": self.summary.to_dict(),
            "receipt": self.receipt,
            "verification": self.verification.to_dict() if self.verification else None,
            "notes": list(self.notes),
            "scientific_evidence_effect": effect,
            "verification_scope": "EXECUTION_BOUND_LEDGER_CONSISTENCY_ONLY",
            "external_identity_trust": "NOT_ESTABLISHED",
            "scientific_authorization": "NONE",
        }


def _samplesheet_precheck(path: Path) -> tuple[bool, str, int]:
    if not path.is_file():
        return False, f"samplesheet not found: {path}", EXIT_MISSING
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, f"samplesheet unreadable: {exc}", EXIT_MISSING
    if not text.strip():
        return False, "samplesheet is empty", EXIT_REFUSED
    header = text.splitlines()[0]
    if "," not in header and "\t" not in header:
        return False, "samplesheet has no delimited header", EXIT_REFUSED
    return True, "samplesheet present (shape is not an evidence factor)", EXIT_OK


def admit_nextflow_run(
    *,
    samplesheet: Optional[PathLike] = None,
    intent: Optional[str] = None,
    data_path: Optional[PathLike] = None,
    metadata: Optional[Dict[str, Any]] = None,
    metadata_path: Optional[PathLike] = None,
    claimed_maturity: Optional[str] = None,
    allow_degraded: bool = False,
    skip_scientific_preflight: bool = False,
    require_scientific_preflight: bool = False,
) -> AdmitResult:
    """Decide whether a Nextflow launch may start.

    Samplesheet checks are path/header existence only. Replication, condition
    counts, and filenames never become scientific evidence factors.
    """
    samplesheet_ok = True
    sheet_detail = "samplesheet not supplied"
    sheet_exit = EXIT_OK
    if samplesheet is not None:
        samplesheet_ok, sheet_detail, sheet_exit = _samplesheet_precheck(Path(samplesheet))
        if not samplesheet_ok:
            return AdmitResult(
                allowed=False,
                exit_code=sheet_exit,
                rationale=sheet_detail,
                samplesheet_ok=False,
                scientific_admission="NOT_RUN",
            )

    if skip_scientific_preflight:
        return AdmitResult(
            allowed=samplesheet_ok,
            exit_code=EXIT_OK if samplesheet_ok else sheet_exit,
            rationale=sheet_detail + "; scientific preflight skipped by caller",
            samplesheet_ok=samplesheet_ok,
            scientific_admission="SKIPPED",
        )

    if not intent and metadata_path is None and not metadata and data_path is None:
        if require_scientific_preflight:
            return AdmitResult(
                allowed=False,
                exit_code=EXIT_MISSING,
                rationale="scientific preflight required: pass --intent or --skip-scientific-preflight",
                samplesheet_ok=samplesheet_ok,
                scientific_admission="NOT_RUN",
            )
        return AdmitResult(
            allowed=samplesheet_ok,
            exit_code=EXIT_OK if samplesheet_ok else sheet_exit,
            rationale=sheet_detail + "; scientific preflight NOT_RUN (no intent)",
            samplesheet_ok=samplesheet_ok,
            scientific_admission="NOT_RUN",
        )

    report = run_preflight(
        intent=intent,
        data_path=data_path,
        metadata=metadata,
        metadata_path=metadata_path,
        claimed_maturity=claimed_maturity,
        allow_degraded=allow_degraded,
    )
    if report.prevented or report.exit_code != EXIT_OK:
        admission = "REFUSED" if int(report.exit_code) == EXIT_REFUSED else "ABSTAIN"
        return AdmitResult(
            allowed=False,
            exit_code=int(report.exit_code),
            rationale=report.rationale,
            samplesheet_ok=samplesheet_ok,
            scientific_admission=admission,
            preflight=report,
        )
    return AdmitResult(
        allowed=True,
        exit_code=EXIT_OK,
        rationale=report.rationale,
        samplesheet_ok=samplesheet_ok,
        scientific_admission="PERMITTED",
        preflight=report,
    )


def generate_bionexus_config(*, outdir: PathLike) -> str:
    """Emit a Nextflow config that enables nf-prov WRROC without touching the DAG."""

    def _nf_quote(value: str) -> str:
        return value.replace("\\", "/").replace("'", r"\'")

    crate = _nf_quote((Path(outdir) / "pipeline_info" / "ro-crate-metadata.json").as_posix())
    trace = _nf_quote((Path(outdir) / "pipeline_info" / "execution_trace.txt").as_posix())
    return "\n".join(
        [
            "// Generated by BioNexus admission control.",
            "// Enables nf-prov Workflow Run RO-Crate. Does not modify pipeline processes.",
            "plugins {",
            "    id 'nf-prov'",
            "}",
            "",
            "prov {",
            "    enabled = true",
            "    formats {",
            "        wrroc {",
            f"            file = '{crate}'",
            "            overwrite = true",
            "        }",
            "    }",
            "}",
            "",
            "trace {",
            "    enabled = true",
            f"    file = '{trace}'",
            "    overwrite = true",
            "}",
            "",
        ]
    )


def write_bionexus_config(path: PathLike, *, outdir: PathLike) -> Path:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(generate_bionexus_config(outdir=outdir), encoding="utf-8", newline="\n")
    return dest


def build_nextflow_execution_binding(
    summary: NextflowExecutionSummary, *, subject_artifact: str,
) -> Dict[str, Any]:
    """Build an explicit binding to one archived execution and subject input.

    This binds declarations to bytes; it does not authenticate the producer or
    infer biological subjects/design from file names or samplesheet shape.
    """
    if subject_artifact not in summary.primary_inputs:
        raise ValueError("subject_artifact must name a hash-bound workflow input")
    return {
        "schema_version": "bionexus.nextflow-execution-binding.v1",
        "workflow_run_id": summary.workflow_run_id,
        "workflow_id": summary.workflow_id,
        "crate_sha256": summary.crate_sha256,
        "pipeline_name": summary.pipeline_name,
        "pipeline_version": summary.pipeline_version,
        "execution_status": summary.execution_status,
        "input_sha256": dict(summary.primary_inputs),
        "output_sha256": dict(summary.primary_outputs),
        "subject_artifact": subject_artifact,
        "subject_sha256": summary.primary_inputs[subject_artifact],
    }


def _execution_binding_errors(ledger: ClaimLedger, summary: NextflowExecutionSummary) -> List[str]:
    errors: List[str] = []
    if summary.provenance_source != "WRROC":
        errors.append("A trace fallback cannot establish a run-bound claim warrant")
    if summary.official_validation_status != STATUS_VALIDATED:
        errors.append("Official RO-Crate profile validation has not passed")
    if summary.artifact_integrity_status != "VERIFIED":
        errors.append("Workflow artifact integrity has not been verified")
    if not summary.primary_inputs or not summary.primary_outputs:
        errors.append("Both producer-hashed workflow inputs and outputs are required")
    if not all((summary.workflow_run_id, summary.workflow_id, summary.crate_sha256, summary.pipeline_version)):
        errors.append("Workflow run identity, crate digest and analysis version are required")
    if summary.samplesheet_path:
        sheet_hash = hashlib.sha256(Path(summary.samplesheet_path).read_bytes()).hexdigest()
        if sheet_hash not in summary.primary_inputs.values():
            errors.append("Supplied samplesheet does not match a producer-hashed workflow input")
    if errors:
        return errors
    for claim in ledger.claims.values():
        binding = claim.provenance.get("nextflow_execution_binding")
        if not isinstance(binding, dict):
            errors.append(f"{claim.claim_id}: missing nextflow_execution_binding")
            continue
        try:
            expected = build_nextflow_execution_binding(
                summary, subject_artifact=binding.get("subject_artifact", ""),
            )
        except (TypeError, ValueError):
            errors.append(f"{claim.claim_id}: subject is not bound to an input artifact")
            continue
        if binding != expected:
            errors.append(f"{claim.claim_id}: execution binding differs from this run")
            continue
        output_support = False
        for ref_id in set(claim.supported_by + claim.depends_on + claim.contradicted_by):
            ref = ledger.evidence.get(ref_id)
            if ref is None:
                errors.append(f"{claim.claim_id}/{ref_id}: unbound evidence reference")
                continue
            prov = ref.provenance
            if prov.get("nextflow_execution_binding") != expected:
                errors.append(f"{claim.claim_id}/{ref_id}: evidence belongs to a different or unrecorded run")
                continue
            path = prov.get("artifact_path")
            digest = prov.get("artifact_sha256")
            artifacts = {**summary.primary_inputs, **summary.primary_outputs}
            if not isinstance(path, str) or path not in artifacts or artifacts[path] != digest:
                errors.append(f"{claim.claim_id}/{ref_id}: evidence is not bound to verified artifact bytes")
                continue
            if ref_id in claim.supported_by and path in summary.primary_outputs:
                output_support = True
        if not output_support:
            errors.append(f"{claim.claim_id}: no supporting evidence is bound to a workflow output")
    return errors


def warrant_nextflow_run(
    run_dir: PathLike,
    *,
    crate_path: Optional[PathLike] = None,
    ledger_path: Optional[PathLike] = None,
    pipeline_name: Optional[str] = None,
    samplesheet_path: Optional[PathLike] = None,
    observed_exit_code: Optional[int] = None,
) -> WarrantResult:
    """Ingest crate-first provenance, then optionally verify a claim ledger.

    Exit 3 means the pipeline provenance was harvested but claims are not
    warranted. Exit 2 means no usable provenance. Exit 1 is harvest failure.
    """
    rdir = Path(run_dir)
    notes: List[str] = []
    try:
        if crate_path is not None:
            from bionexus.wrroc import ingest_wrroc_crate

            summary = ingest_wrroc_crate(
                crate_path,
                pipeline_name=pipeline_name,
                samplesheet_path=samplesheet_path,
                run_dir=rdir,
                official_validation="auto",
            )
        else:
            summary = harvest_nextflow_run(
                rdir, pipeline_name=pipeline_name, samplesheet_path=samplesheet_path
            )
    except FileNotFoundError as exc:
        empty = NextflowExecutionSummary(pipeline_name=pipeline_name or "nf-core/pipeline")
        return WarrantResult(
            exit_code=EXIT_MISSING,
            warrant_status="MISSING_PROVENANCE",
            provenance_source="MISSING",
            summary=empty,
            receipt={},
            notes=[str(exc)],
        )
    except ValueError as exc:
        empty = NextflowExecutionSummary(pipeline_name=pipeline_name or "nf-core/pipeline")
        return WarrantResult(
            exit_code=EXIT_REFUSED,
            warrant_status="INVALID_CRATE",
            provenance_source="MISSING",
            summary=empty,
            receipt={},
            notes=[str(exc)],
        )

    if summary.provenance_source == "MISSING":
        return WarrantResult(
            exit_code=EXIT_MISSING,
            warrant_status="MISSING_PROVENANCE",
            provenance_source=summary.provenance_source,
            summary=summary,
            receipt={},
            notes=["No Workflow Run RO-Crate or execution_trace.txt was found"],
        )

    receipt = create_nextflow_tool_receipt(
        rdir,
        pipeline_name=pipeline_name or summary.pipeline_name,
        samplesheet_path=samplesheet_path,
        summary=summary,
    )
    if summary.provenance_source == "TRACE_FALLBACK":
        notes.append("Authoritative crate missing; used execution_trace.txt fallback")
    if (summary.execution_status != "SUCCESS" or summary.failed_processes > 0
            or (observed_exit_code is not None and observed_exit_code != 0)):
        return WarrantResult(
            exit_code=EXIT_CLAIMS_REFUSED, warrant_status="EXECUTION_NOT_SUCCESSFUL",
            provenance_source=summary.provenance_source, summary=summary, receipt=receipt,
            notes=notes + ["Failed, incomplete or unknown execution cannot warrant claims"],
        )

    resolved_ledger: Optional[Path] = None
    if ledger_path is not None:
        resolved_ledger = Path(ledger_path)
    else:
        try:
            resolved_ledger = Path(locate_ledger(rdir))
        except FileNotFoundError:
            resolved_ledger = None

    if resolved_ledger is None or not resolved_ledger.is_file():
        notes.append("No claim ledger supplied; scientific_evidence_effect=NONE")
        return WarrantResult(
            exit_code=EXIT_OK,
            warrant_status="PROVENANCE_ONLY",
            provenance_source=summary.provenance_source,
            summary=summary,
            receipt=receipt,
            notes=notes,
        )

    try:
        ledger = ClaimLedger.load(resolved_ledger)
        verification = verify_ledger(ledger, ledger_path=str(resolved_ledger))
        binding_errors = _execution_binding_errors(ledger, summary)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        verification = None
        binding_errors = [f"Ledger could not be validated: {exc}"]
    notes.extend(binding_errors)
    if verification is not None and verification.passed and not binding_errors:
        return WarrantResult(
            exit_code=EXIT_OK,
            warrant_status="VERIFIED",
            provenance_source=summary.provenance_source,
            summary=summary,
            receipt=receipt,
            verification=verification,
            notes=notes,
        )
    notes.append("Pipeline provenance harvested; claims are not warranted")
    return WarrantResult(
        exit_code=EXIT_CLAIMS_REFUSED,
        warrant_status="CLAIMS_REFUSED",
        provenance_source=summary.provenance_source,
        summary=summary,
        receipt=receipt,
        verification=verification,
        notes=notes,
    )


def build_nextflow_command(
    *,
    pipeline: str,
    samplesheet: PathLike,
    outdir: PathLike,
    profile: str = "docker",
    config_path: Optional[PathLike] = None,
    extra: Optional[Sequence[str]] = None,
    nextflow_bin: str = "nextflow",
) -> List[str]:
    name = pipeline.removeprefix("nf-core/")
    if name not in ALLOWED_PIPELINES:
        raise ValueError(
            "Only nf-core/" + "/".join(ALLOWED_PIPELINES) + f" are supported, got {pipeline}"
        )
    cmd = [
        nextflow_bin,
        "run",
        f"nf-core/{name}",
        "-profile",
        profile,
        "--input",
        str(samplesheet),
        "--outdir",
        str(outdir),
    ]
    if config_path is not None:
        cmd.extend(["-c", str(config_path)])
    if extra:
        cmd.extend(str(item) for item in extra)
    return cmd


def execute_nextflow(command: List[str], *, cwd: Optional[Path] = None) -> int:
    """Run a Nextflow argv list. Never uses ``shell=True``."""
    if not command:
        raise ValueError("empty nextflow command")
    binary = command[0]
    if shutil.which(binary) is None and not Path(binary).is_file():
        raise FileNotFoundError(f"nextflow executable not found: {binary}")
    proc = subprocess.run(command, cwd=str(cwd) if cwd else None, check=False)
    return int(proc.returncode)


def run_nextflow_gated(
    *,
    pipeline: str,
    samplesheet: PathLike,
    outdir: PathLike,
    intent: Optional[str] = None,
    profile: str = "docker",
    metadata: Optional[Dict[str, Any]] = None,
    metadata_path: Optional[PathLike] = None,
    data_path: Optional[PathLike] = None,
    ledger_path: Optional[PathLike] = None,
    extra: Optional[Sequence[str]] = None,
    nextflow_bin: str = "nextflow",
    runner: Optional[NextflowRunner] = None,
    config_path: Optional[PathLike] = None,
    dry_run: bool = False,
    skip_scientific_preflight: bool = False,
    claimed_maturity: Optional[str] = None,
    allow_degraded: bool = False,
) -> Dict[str, Any]:
    """Admit, optionally execute Nextflow, then warrant against the crate.

    If admit refuses, ``runner`` is never called. ``run`` requires scientific
    preflight unless ``skip_scientific_preflight`` is set.
    """
    sheet = Path(samplesheet)
    out = Path(outdir)
    admit = admit_nextflow_run(
        samplesheet=sheet,
        intent=intent,
        data_path=data_path,
        metadata=metadata,
        metadata_path=metadata_path,
        claimed_maturity=claimed_maturity,
        allow_degraded=allow_degraded,
        skip_scientific_preflight=skip_scientific_preflight,
        require_scientific_preflight=not skip_scientific_preflight,
    )
    result: Dict[str, Any] = {
        "admit": admit.to_dict(),
        "command": [],
        "nextflow_exit_code": None,
        "warrant": None,
        "exit_code": admit.exit_code,
        "nextflow_started": False,
    }
    if not admit.allowed:
        return result

    cfg_path = Path(config_path) if config_path is not None else out / "pipeline_info" / "bionexus.config"
    write_bionexus_config(cfg_path, outdir=out)
    command = build_nextflow_command(
        pipeline=pipeline,
        samplesheet=sheet,
        outdir=out,
        profile=profile,
        config_path=cfg_path,
        extra=extra,
        nextflow_bin=nextflow_bin,
    )
    result["command"] = command
    if dry_run:
        result["exit_code"] = EXIT_OK
        return result

    execute = runner or execute_nextflow
    from bionexus.wrroc import locate_wrroc_crate

    prior_crate = locate_wrroc_crate(out)
    prior_crate_hash = hashlib.sha256(prior_crate.read_bytes()).hexdigest() if prior_crate else None
    result["nextflow_started"] = True
    try:
        nf_rc = int(execute(command))
    except FileNotFoundError as exc:
        result["nextflow_started"] = False
        result["exit_code"] = EXIT_REFUSED
        result["error"] = str(exc)
        return result
    result["nextflow_exit_code"] = nf_rc
    warrant = warrant_nextflow_run(
        out,
        ledger_path=ledger_path,
        pipeline_name=f"nf-core/{pipeline.removeprefix('nf-core/')}",
        samplesheet_path=sheet,
        observed_exit_code=nf_rc,
    )
    if prior_crate_hash and warrant.summary.crate_sha256 == prior_crate_hash:
        warrant.warrant_status = "STALE_PROVENANCE"
        warrant.exit_code = EXIT_CLAIMS_REFUSED
        warrant.notes.append("Runner did not produce a new crate; prior-run provenance cannot warrant this invocation")
    result["warrant"] = warrant.to_dict()
    if nf_rc != 0:
        result["exit_code"] = nf_rc
        return result
    result["exit_code"] = warrant.exit_code
    return result


def render_admit(result: AdmitResult) -> str:
    lines = [
        "=== BioNexus Nextflow admit ===",
        f"allowed: {result.allowed}",
        f"exit_code: {result.exit_code}",
        f"samplesheet_ok: {result.samplesheet_ok}",
        f"scientific_admission: {result.scientific_admission}",
        f"rationale: {result.rationale}",
    ]
    if result.preflight is not None:
        lines.append("")
        lines.append(render_preflight(result.preflight))
    return "\n".join(lines)


def render_warrant(result: WarrantResult) -> str:
    summary = result.summary
    lines = [
        "=== BioNexus Nextflow warrant ===",
        f"warrant_status: {result.warrant_status}",
        f"exit_code: {result.exit_code}",
        f"provenance_source: {result.provenance_source}",
        f"pipeline: {summary.pipeline_name}",
        f"execution_status: {summary.execution_status}",
        f"crate_path: {summary.crate_path or '(none)'}",
        f"official_validation_status: {summary.official_validation_status}",
        f"scientific_evidence_effect: {result.to_dict()['scientific_evidence_effect']}",
    ]
    for note in result.notes:
        lines.append(f"note: {note}")
    if result.verification is not None:
        from bionexus.verification import render_verification

        lines.append("")
        lines.append(render_verification(result.verification))
    return "\n".join(lines)
