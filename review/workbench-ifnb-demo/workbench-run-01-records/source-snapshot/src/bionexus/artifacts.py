"""
BioNexus Standardized Run Artifact Contract & Capsule Engine.

Enforces a machine-readable, multi-agent handoff bundle structure:

run/
├── run.json            # Master Run Capsule Descriptor & Agent Manifest
├── inputs.json         # Input files, semantic types, SHA-256 hashes, matrix stats
├── parameters.json     # Resolved hyperparameters and execution flags
├── results/            # Computed output datasets (.h5ad, .csv, .parquet, .tsv)
├── figures/            # Visualizations (.png, .svg, .pdf, .html)
├── evidence.json       # EvidenceCard 2.0 (execution_state, dimensions, maturity)
├── provenance.json     # W3C PROV-O record with cryptographic input/output hashes
├── environment.json    # OS, Python runtime, CPU/RAM, pinned package versions
└── logs/               # Detailed execution and preflight diagnostic logs
    └── pipeline.log
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from bionexus.contracts import EvidenceCard
from bionexus.provenance import capture_environment, sha256_file, sidecar
from bionexus.versions import PLUGIN_VERSION

BUNDLE_SCHEMA_VERSION = "2.0"
_CORE_DESCRIPTORS = (
    "inputs.json",
    "parameters.json",
    "evidence.json",
    "provenance.json",
    "environment.json",
    "logs/pipeline.log",
)


def _canonical_json_sha256(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contained_artifact_path(base_dir: Path, candidate: str | Path) -> tuple[Path, str]:
    """Resolve an output path and require it to remain inside the capsule."""
    base = base_dir.resolve()
    path = Path(candidate)
    resolved = path.resolve() if path.is_absolute() else (base / path).resolve()
    try:
        relative = resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"RunBundle artifact must remain inside {base}: {candidate}") from exc
    return resolved, relative.as_posix()


@dataclass
class InputArtifact:
    """Specification of an input file to a run capsule."""

    name: str
    path: str
    semantic_type: str
    sha256: str
    size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutputArtifact:
    """Specification of a generated result file in a run capsule."""

    name: str
    path: str
    semantic_type: str
    sha256: str
    size_bytes: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FigureArtifact:
    """Specification of a figure/plot generated in a run capsule."""

    title: str
    path: str
    format: str
    sha256: str
    size_bytes: int = 0
    description: str = ""


@dataclass
class DownstreamSuggestion:
    """Machine-readable suggestion for the next agent turn."""

    intent: str
    capability_id: str
    input_artifact: str
    recommended_command: str
    rationale: str = ""


@dataclass
class StepRecord:
    """
    One recorded execution step inside a run capsule.

    Steps are the honest source for step-level provenance (Workflow Run
    RO-Crate / Provenance Run Crate projections, BNS-IO-014): a step names the
    tool that ran and binds capsule artifacts as its inputs/outputs. Inputs
    reference capsule input names or output result names of *earlier* steps;
    outputs reference result names already registered via `add_result`.
    """

    name: str
    tool: str
    description: str = ""
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    status: str = "COMPLETED"
    error: str = ""
    tool_version: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


@dataclass
class BundleVerificationResult:
    """Result of validating a run bundle's integrity."""

    valid: bool
    run_id: str
    missing_files: List[str] = field(default_factory=list)
    tampered_files: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RunBundle:
    """
    Standardized execution bundle / capsule builder and reader.
    """

    def __init__(
        self,
        run_dir: str | Path,
        *,
        run_id: Optional[str] = None,
        capability_id: str = "custom.pipeline",
        skill_name: str = "generic-skill",
    ) -> None:
        self.run_dir = Path(run_dir)
        ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        clean_cap = capability_id.replace(".", "_")
        self.run_id = run_id or f"run_{ts_str}_{clean_cap}"
        self.capability_id = capability_id
        self.skill_name = skill_name

        self.status = "INITIALIZING"
        self.execution_state = "PENDING"
        self.conclusion_maturity = "UNASSESSED"

        self.timestamp_start: str = datetime.now(timezone.utc).isoformat()
        self.timestamp_end: Optional[str] = None
        self._t0 = time.perf_counter()

        self.inputs: Dict[str, InputArtifact] = {}
        self.parameters: Dict[str, Any] = {}
        self.results: Dict[str, OutputArtifact] = {}
        self.figures: Dict[str, FigureArtifact] = {}
        self.primary_result_path: Optional[str] = None

        self.evidence_card: Optional[EvidenceCard] = None
        self.downstream_suggestions: List[DownstreamSuggestion] = []
        self.steps: List[StepRecord] = []
        self.log_messages: List[str] = []

        # Directory layout
        self.results_dir = self.run_dir / "results"
        self.figures_dir = self.run_dir / "figures"
        self.logs_dir = self.run_dir / "logs"

    @classmethod
    def create(
        cls,
        run_dir: str | Path,
        capability_id: str,
        skill_name: str,
        run_id: Optional[str] = None,
    ) -> RunBundle:
        """Create and initialize a new RunBundle directory."""
        bundle = cls(
            run_dir=run_dir,
            run_id=run_id,
            capability_id=capability_id,
            skill_name=skill_name,
        )
        bundle.results_dir.mkdir(parents=True, exist_ok=True)
        bundle.figures_dir.mkdir(parents=True, exist_ok=True)
        bundle.logs_dir.mkdir(parents=True, exist_ok=True)
        bundle.status = "RUNNING"
        bundle.log(f"Initialized RunBundle '{bundle.run_id}' for capability '{capability_id}'")
        return bundle

    def log(self, message: str) -> None:
        """Append log message to in-memory buffer."""
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{ts}] {message}"
        self.log_messages.append(entry)

    def record_input(
        self,
        name: str,
        file_path: str | Path,
        semantic_type: str = "unspecified",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record an input file artifact."""
        p = Path(file_path).resolve()
        sha = sha256_file(p) if p.exists() and p.is_file() else "missing"
        size = p.stat().st_size if p.exists() and p.is_file() else 0

        self.inputs[name] = InputArtifact(
            name=name,
            path=p.as_posix(),
            semantic_type=semantic_type,
            sha256=sha,
            size_bytes=size,
            metadata=metadata or {},
        )
        self.log(f"Recorded input artifact '{name}' -> {p} (SHA-256: {sha[:8]}...)")

    def record_parameters(self, **kwargs: Any) -> None:
        """Record hyperparameters and configuration flags."""
        self.parameters.update(kwargs)
        self.log(f"Recorded execution parameters: {list(kwargs.keys())}")

    def add_result(
        self,
        name: str,
        file_path: str | Path,
        semantic_type: str = "unspecified",
        is_primary: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a generated result data artifact."""
        p, rel_path = _contained_artifact_path(self.run_dir, Path(file_path).resolve())
        if not p.is_file():
            raise FileNotFoundError(f"Result artifact does not exist: {p}")
        sha = sha256_file(p)
        size = p.stat().st_size

        self.results[name] = OutputArtifact(
            name=name,
            path=rel_path,
            semantic_type=semantic_type,
            sha256=sha,
            size_bytes=size,
            metadata=metadata or {},
        )
        if is_primary or self.primary_result_path is None:
            self.primary_result_path = rel_path
        self.log(f"Added result artifact '{name}' -> {rel_path}")

    def add_figure(
        self,
        title: str,
        file_path: str | Path,
        description: str = "",
    ) -> None:
        """Record a generated figure or visualization."""
        p, rel_path = _contained_artifact_path(self.run_dir, Path(file_path).resolve())
        if not p.is_file():
            raise FileNotFoundError(f"Figure artifact does not exist: {p}")
        sha = sha256_file(p)
        size = p.stat().st_size

        self.figures[title] = FigureArtifact(
            title=title,
            path=rel_path,
            format=p.suffix.lstrip("."),
            sha256=sha,
            size_bytes=size,
            description=description,
        )
        self.log(f"Added figure '{title}' -> {rel_path}")

    def attach_evidence_card(self, card: EvidenceCard) -> None:
        """Attach EvidenceCard to bundle and update status."""
        self.evidence_card = card
        self.execution_state = card.execution_state
        self.conclusion_maturity = card.synthesize_status()
        self.log(f"Attached EvidenceCard (Execution: {card.execution_state}, Maturity: {self.conclusion_maturity})")

    def add_downstream_suggestion(
        self,
        intent: str,
        capability_id: str,
        input_artifact: str,
        recommended_command: str,
        rationale: str = "",
    ) -> None:
        """Add actionable suggestion for the next agent turn."""
        self.downstream_suggestions.append(
            DownstreamSuggestion(
                intent=intent,
                capability_id=capability_id,
                input_artifact=input_artifact,
                recommended_command=recommended_command,
                rationale=rationale,
            )
        )

    def record_step(
        self,
        name: str,
        tool: str,
        *,
        description: str = "",
        inputs: Optional[List[str]] = None,
        outputs: Optional[List[str]] = None,
        status: str = "COMPLETED",
        error: str = "",
        tool_version: Optional[str] = None,
        started_at: Optional[str] = None,
        ended_at: Optional[str] = None,
    ) -> StepRecord:
        """
        Record one executed workflow step (call after the step completed).

        `inputs` must reference capsule input names or result names produced by
        earlier steps; `outputs` must reference result names already registered
        via `add_result`. Full binding validation happens in `finalize`.
        """
        record = StepRecord(
            name=name,
            tool=tool,
            description=description,
            inputs=list(inputs or []),
            outputs=list(outputs or []),
            status=status,
            error=error,
            tool_version=tool_version,
            started_at=started_at,
            ended_at=ended_at or datetime.now(timezone.utc).isoformat(),
        )
        self.steps.append(record)
        self.log(f"Recorded step '{name}' (tool: {tool}, status: {status})")
        return record

    def _validate_steps(self) -> None:
        """Fail-closed binding checks for recorded steps (run.json seal scope)."""
        seen_outputs: set[str] = set()
        known = set(self.inputs) | set(self.results)
        for idx, step in enumerate(self.steps):
            if not step.name or not step.tool:
                raise ValueError(f"Step #{idx} must record both a name and a tool.")
            if step.status.upper() in ("FAILED", "ERROR") and not step.error:
                raise ValueError(f"Step '{step.name}' failed but recorded no error detail.")
            for out in step.outputs:
                if out not in self.results:
                    raise ValueError(
                        f"Step '{step.name}' output '{out}' is not a registered result artifact."
                    )
                if out in seen_outputs:
                    raise ValueError(f"Result '{out}' is claimed as output by more than one step.")
                seen_outputs.add(out)
            for inp in step.inputs:
                if inp not in known:
                    raise ValueError(
                        f"Step '{step.name}' input '{inp}' is neither a capsule input "
                        f"nor an output of an earlier step."
                    )
            known = set(self.inputs) | seen_outputs

    def finalize(self, status: str = "COMPLETED") -> Path:
        """
        Finalize and write all capsule descriptor files.
        Returns the path to the master run.json.
        """
        self.status = status
        self.timestamp_end = datetime.now(timezone.utc).isoformat()
        duration = round(time.perf_counter() - self._t0, 3)
        self._validate_steps()

        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.figures_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # 1. Write inputs.json
        inputs_dict = {k: asdict(v) for k, v in self.inputs.items()}
        (self.run_dir / "inputs.json").write_text(json.dumps(inputs_dict, indent=2), encoding="utf-8")

        # 2. Write parameters.json
        (self.run_dir / "parameters.json").write_text(json.dumps(self.parameters, indent=2), encoding="utf-8")

        # 3. Write evidence.json
        if self.evidence_card:
            evidence_dict = self.evidence_card.to_dict()
        else:
            evidence_dict = {
                "execution_state": self.execution_state,
                "conclusion_maturity": self.conclusion_maturity,
            }
        (self.run_dir / "evidence.json").write_text(json.dumps(evidence_dict, indent=2), encoding="utf-8")

        # 4. Write provenance.json (W3C PROV-O)
        input_paths = [v.path for v in self.inputs.values() if Path(v.path).exists()]
        output_paths = [str((self.run_dir / v.path).as_posix()) for v in self.results.values()]
        prov_data = sidecar(
            activity_name=self.capability_id,
            input_files=input_paths,
            output_files=output_paths,
            method=self.skill_name,
            backend=self.evidence_card.details.get("execution_backend", "scanpy") if self.evidence_card else "default",
            parameters=self.parameters,
        )
        (self.run_dir / "provenance.json").write_text(json.dumps(prov_data, indent=2), encoding="utf-8")

        # 5. Write environment.json
        env_data = capture_environment()
        (self.run_dir / "environment.json").write_text(json.dumps(env_data, indent=2), encoding="utf-8")

        # 6. Write logs/pipeline.log
        log_file = self.logs_dir / "pipeline.log"
        log_file.write_text("\n".join(self.log_messages) + "\n", encoding="utf-8")

        # 7. Write master run.json
        manifest = {
            "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
            "run_id": self.run_id,
            "bionexus_version": PLUGIN_VERSION,
            "capability_id": self.capability_id,
            "skill_name": self.skill_name,
            "status": self.status,
            "execution_state": self.execution_state,
            "conclusion_maturity": self.conclusion_maturity,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "duration_seconds": duration,
            "artifacts": {
                "inputs_manifest": "inputs.json",
                "parameters_manifest": "parameters.json",
                "evidence_card": "evidence.json",
                "provenance_sidecar": "provenance.json",
                "environment_snapshot": "environment.json",
                "execution_log": "logs/pipeline.log",
                "primary_result": self.primary_result_path,
                "results": [asdict(v) for v in self.results.values()],
                "figures": [asdict(v) for v in self.figures.values()],
            },
            "downstream_suggestions": [asdict(v) for v in self.downstream_suggestions],
        }
        if self.steps:
            manifest["steps"] = [asdict(v) for v in self.steps]

        descriptor_hashes = {
            rel_path: sha256_file(self.run_dir / rel_path)
            for rel_path in _CORE_DESCRIPTORS
        }
        manifest["integrity"] = {
            "algorithm": "sha256",
            "descriptor_sha256": descriptor_hashes,
            "scope": "inputs, descriptors, results, figures, and manifest payload",
            "authentication": "none",
        }
        manifest["integrity"]["manifest_payload_sha256"] = _canonical_json_sha256(manifest)

        master_path = self.run_dir / "run.json"
        master_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return master_path


def load_run_bundle(run_dir: str | Path) -> Dict[str, Any]:
    """
    Load and parse a master run.json descriptor for agent handoff.
    """
    p = Path(run_dir)
    run_file = p / "run.json" if p.is_dir() else p
    if not run_file.exists():
        raise FileNotFoundError(f"Run descriptor not found: {run_file}")

    data = json.loads(run_file.read_text(encoding="utf-8"))
    return data


def verify_run_bundle(run_dir: str | Path) -> BundleVerificationResult:
    """
    Verify complete integrity of a RunBundle, detecting missing or tampered files.
    """
    p = Path(run_dir)
    run_file = p / "run.json" if p.is_dir() else p
    base_dir = run_file.parent

    if not run_file.exists():
        return BundleVerificationResult(
            valid=False,
            run_id="unknown",
            missing_files=["run.json"],
            notes=["Master run.json is missing."],
        )

    try:
        manifest = json.loads(run_file.read_text(encoding="utf-8"))
    except Exception as e:
        return BundleVerificationResult(
            valid=False,
            run_id="unknown",
            notes=[f"Failed to parse run.json: {e}"],
        )

    run_id = manifest.get("run_id", "unknown")
    missing: List[str] = []
    tampered: List[str] = []
    notes: List[str] = []

    integrity = manifest.get("integrity")
    if manifest.get("bundle_schema_version") != BUNDLE_SCHEMA_VERSION or not isinstance(integrity, dict):
        notes.append("Legacy or unsealed RunBundle: schema v2 integrity metadata is required.")
        tampered.append("run.json (missing v2 integrity seal)")
        integrity = {}

    expected_manifest_sha = integrity.get("manifest_payload_sha256")
    manifest_payload = dict(manifest)
    integrity_payload = dict(integrity)
    integrity_payload.pop("manifest_payload_sha256", None)
    manifest_payload["integrity"] = integrity_payload
    actual_manifest_sha = _canonical_json_sha256(manifest_payload)
    if not expected_manifest_sha or expected_manifest_sha != actual_manifest_sha:
        tampered.append("run.json (manifest payload checksum mismatch)")

    # Check required core descriptor files and their sealed checksums.
    descriptor_hashes = integrity.get("descriptor_sha256", {})
    for rel_f in _CORE_DESCRIPTORS:
        f_path = base_dir / rel_f
        if not f_path.is_file():
            missing.append(rel_f)
            continue
        expected_sha = descriptor_hashes.get(rel_f)
        actual_sha = sha256_file(f_path)
        if not expected_sha or expected_sha != actual_sha:
            tampered.append(f"{rel_f} (descriptor checksum mismatch)")

    # Inputs may intentionally live outside the capsule, but their recorded
    # bytes must still be present and unchanged at verification time.
    inputs_path = base_dir / "inputs.json"
    if inputs_path.is_file():
        try:
            inputs_manifest = json.loads(inputs_path.read_text(encoding="utf-8"))
        except Exception as exc:
            tampered.append(f"inputs.json (parse failure: {exc})")
            inputs_manifest = {}
        for input_item in inputs_manifest.values() if isinstance(inputs_manifest, dict) else []:
            recorded_path = input_item.get("path", "")
            expected_sha = input_item.get("sha256", "")
            input_path = Path(recorded_path)
            if not input_path.is_absolute():
                input_path = (base_dir / input_path).resolve()
            if not input_path.is_file():
                missing.append(f"input:{recorded_path}")
            elif not expected_sha or expected_sha == "missing" or sha256_file(input_path) != expected_sha:
                tampered.append(f"input:{recorded_path} (checksum mismatch)")

    # Check results files & checksums
    results_list = manifest.get("artifacts", {}).get("results", [])
    for res_item in results_list:
        rel_path = res_item.get("path", "")
        expected_sha = res_item.get("sha256", "")
        try:
            f_path, safe_rel_path = _contained_artifact_path(base_dir, rel_path)
        except ValueError:
            tampered.append(f"{rel_path} (path escapes run directory)")
            continue
        if not f_path.is_file():
            missing.append(rel_path)
        else:
            actual_sha = sha256_file(f_path)
            if not expected_sha or expected_sha == "pending" or actual_sha != expected_sha:
                tampered.append(
                    f"{safe_rel_path} (Expected: {expected_sha[:8]}..., Got: {actual_sha[:8]}...)"
                )

    # Check figures
    figures_list = manifest.get("artifacts", {}).get("figures", [])
    for fig_item in figures_list:
        rel_path = fig_item.get("path", "")
        expected_sha = fig_item.get("sha256", "")
        try:
            f_path, safe_rel_path = _contained_artifact_path(base_dir, rel_path)
        except ValueError:
            tampered.append(f"{rel_path} (path escapes run directory)")
            continue
        if not f_path.is_file():
            missing.append(rel_path)
        else:
            actual_sha = sha256_file(f_path)
            if not expected_sha or expected_sha == "pending" or actual_sha != expected_sha:
                tampered.append(
                    f"{safe_rel_path} (Expected: {expected_sha[:8]}..., Got: {actual_sha[:8]}...)"
                )

    valid = len(missing) == 0 and len(tampered) == 0
    if valid:
        notes.append(
            f"RunBundle '{run_id}' passed SHA-256 integrity checks. "
            "This detects byte changes but is not a digital signature or identity authentication."
        )
    else:
        if missing:
            notes.append(f"Missing {len(missing)} expected file(s).")
        if tampered:
            notes.append(f"Detected {len(tampered)} modified/tampered file(s).")

    return BundleVerificationResult(
        valid=valid,
        run_id=run_id,
        missing_files=missing,
        tampered_files=tampered,
        notes=notes,
    )
