"""Passive Nextflow execution-provenance harvester (BNS-021).

Provides:
1. Parsing of Nextflow execution directories (execution_trace.txt, software_versions.yml,
   samplesheet.csv, output artifact digests).
2. Production of cryptographic tool execution receipts (bionexus.tool-execution-receipt.v1).
3. Optional descriptive parsing of a samplesheet only when the caller supplies
   its path explicitly.

This module does not implement the generic BNS-019 workflow boundary. It never
turns workflow success, samplesheet shape, filenames, or software names into
scientific evidence factors. Artifact-level scientific meaning belongs in an
explicit external BNS-019 annotation over existing provenance such as WRROC.
"""

from __future__ import annotations

import csv
import hashlib
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from bionexus.tool_receipt import ToolReceiptLevel, create_tool_receipt
from bionexus.versions import VERSION


@dataclass
class NextflowExecutionSummary:
    """Structured summary of a completed or inspected Nextflow pipeline execution."""

    pipeline_name: str
    pipeline_version: Optional[str] = None
    nextflow_version: Optional[str] = None
    execution_status: str = "SUCCESS"  # "SUCCESS" | "FAILED" | "INCOMPLETE"
    run_dir: str = ""
    samplesheet_path: Optional[str] = None
    sample_count: int = 0
    samples: List[Dict[str, Any]] = field(default_factory=list)
    biological_replicates_count: int = 0
    min_replicates_per_condition: int = 0
    conditions_count: int = 0
    total_processes: int = 0
    succeeded_processes: int = 0
    failed_processes: int = 0
    cached_processes: int = 0
    total_cpu_hours: float = 0.0
    peak_rss_gb: float = 0.0
    software_versions: Dict[str, str] = field(default_factory=dict)
    primary_outputs: Dict[str, str] = field(default_factory=dict)  # filename -> sha256
    derived_evidence_factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _sha256_file(path: Union[str, Path]) -> str:
    """Compute SHA-256 of a file if readable, else return empty string."""
    try:
        p = Path(path)
        if not p.is_file():
            return ""
        h = hashlib.sha256()
        with open(p, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def parse_trace_file(trace_path: Union[str, Path]) -> Dict[str, Any]:
    """Parse a Nextflow tab-separated execution_trace.txt file.

    Extracts:
    - total, succeeded, failed, and cached process counts
    - execution_status (SUCCESS if 0 failed and total > 0, else FAILED)
    - total_cpu_hours and peak_rss_gb
    """
    p = Path(trace_path)
    if not p.is_file():
        return {
            "total_processes": 0,
            "succeeded_processes": 0,
            "failed_processes": 0,
            "cached_processes": 0,
            "execution_status": "UNKNOWN",
            "total_cpu_hours": 0.0,
            "peak_rss_gb": 0.0,
        }

    total = 0
    succeeded = 0
    failed = 0
    cached = 0
    total_cpu_ms = 0
    peak_rss_bytes = 0

    with open(p, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            total += 1
            status = (row.get("status") or "").strip().upper()
            if status in ("COMPLETED", "OK"):
                succeeded += 1
            elif status in ("FAILED", "ABORTED", "ERROR"):
                failed += 1
            elif status in ("CACHED", "STORED"):
                cached += 1
                succeeded += 1

            # Parse realtime / duration if available
            realtime_str = row.get("realtime") or row.get("duration") or "0"
            try:
                total_cpu_ms += int(float(realtime_str))
            except (ValueError, TypeError):
                pass

            # Parse peak_rss
            peak_str = row.get("peak_rss") or "0"
            try:
                rss = int(float(peak_str))
                if rss > peak_rss_bytes:
                    peak_rss_bytes = rss
            except (ValueError, TypeError):
                pass

    overall_status = (
        "SUCCESS" if (total > 0 and failed == 0) else ("FAILED" if failed > 0 else "INCOMPLETE")
    )
    cpu_hours = round(total_cpu_ms / (1000.0 * 3600.0), 4)
    rss_gb = round(peak_rss_bytes / (1024.0**3), 4)

    return {
        "total_processes": total,
        "succeeded_processes": succeeded,
        "failed_processes": failed,
        "cached_processes": cached,
        "execution_status": overall_status,
        "total_cpu_hours": cpu_hours,
        "peak_rss_gb": rss_gb,
    }


def parse_versions_file(versions_path: Union[str, Path]) -> Dict[str, str]:
    """Parse software_versions.yml / versions.yml from Nextflow pipeline run."""
    p = Path(versions_path)
    if not p.is_file():
        return {}

    versions: Dict[str, str] = {}
    try:
        content = p.read_text(encoding="utf-8", errors="replace")
        current_process = ""
        for line in content.splitlines():
            line_str = line.strip()
            if not line_str or line_str.startswith("#"):
                continue
            if line.startswith(" ") or line.startswith("\t"):
                parts = line_str.split(":", 1)
                if len(parts) == 2:
                    tool = parts[0].strip().strip("\"'")
                    ver = parts[1].strip().strip("\"'")
                    key = f"{current_process}.{tool}" if current_process else tool
                    versions[key] = ver
            else:
                parts = line_str.split(":", 1)
                if len(parts) == 2:
                    tool = parts[0].strip().strip("\"'")
                    ver = parts[1].strip().strip("\"'")
                    if ver:
                        versions[tool] = ver
                    else:
                        current_process = tool
    except Exception:
        pass
    return versions


def parse_samplesheet(
    samplesheet_path: Union[str, Path],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse nf-core samplesheet.csv and derive statistical experimental design facts.

    Returns:
        (samples_list, design_facts_dict)
    """
    p = Path(samplesheet_path)
    if not p.is_file():
        return [], {
            "sample_count": 0,
            "min_replicates_per_condition": 0,
            "biological_replicates_count": 0,
            "conditions_count": 0,
        }

    samples: List[Dict[str, Any]] = []
    with open(p, "r", encoding="utf-8", errors="replace") as f:
        sample_snippet = f.read(2048)
        delimiter = "," if "," in sample_snippet else ("\t" if "\t" in sample_snippet else ",")
        f.seek(0)
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            samples.append({k.strip(): v.strip() for k, v in row.items() if k})

    condition_counts: Dict[str, int] = {}
    donors: Set[str] = set()

    for s in samples:
        cond = (
            s.get("condition")
            or s.get("group")
            or s.get("treatment")
            or s.get("status")
            or s.get("genotype")
            or "default"
        )
        condition_counts[cond] = condition_counts.get(cond, 0) + 1
        donor = s.get("donor") or s.get("patient") or s.get("subject") or s.get("individual")
        if donor:
            donors.add(donor)

    min_reps = min(condition_counts.values()) if condition_counts else len(samples)
    total_reps = len(donors) if donors else len(samples)

    facts = {
        "sample_count": len(samples),
        "min_replicates_per_condition": min_reps,
        "biological_replicates_count": total_reps,
        "conditions_count": len(condition_counts),
        "conditions": sorted(condition_counts.keys()),
    }
    return samples, facts


def harvest_nextflow_run(
    run_dir: Union[str, Path],
    *,
    pipeline_name: Optional[str] = None,
    samplesheet_path: Optional[Union[str, Path]] = None,
) -> NextflowExecutionSummary:
    """Inspect and harvest a Nextflow pipeline execution directory into a NextflowExecutionSummary."""
    rdir = Path(run_dir)
    if not rdir.exists():
        raise FileNotFoundError(f"Nextflow run directory does not exist: {rdir}")

    # 1. Locate trace file
    trace_candidates = [
        rdir / "pipeline_info" / "execution_trace.txt",
        rdir / "execution_trace.txt",
        rdir / "trace.txt",
        rdir / ".nextflow" / "trace.txt",
    ]
    trace_file: Optional[Path] = None
    for cand in trace_candidates:
        if cand.is_file():
            trace_file = cand
            break
    if not trace_file:
        trace_matches = list(rdir.glob("**/execution_trace*.txt"))
        if trace_matches:
            trace_file = trace_matches[0]

    trace_stats = parse_trace_file(trace_file) if trace_file else parse_trace_file(rdir / "__missing_trace__")

    # 2. Locate versions file
    versions_candidates = [
        rdir / "pipeline_info" / "software_versions.yml",
        rdir / "pipeline_info" / "versions.yml",
        rdir / "versions.yml",
    ]
    versions_file: Optional[Path] = None
    for v_cand in versions_candidates:
        if v_cand.is_file():
            versions_file = v_cand
            break
    if not versions_file:
        v_matches = list(rdir.glob("**/software_versions*.yml")) or list(rdir.glob("**/versions.yml"))
        if v_matches:
            versions_file = v_matches[0]

    versions = parse_versions_file(versions_file) if versions_file else {}

    # 3. A generic run has no authoritative samplesheet shape. Parse one only
    # when a caller explicitly supplies a domain-specific path.
    sheet_file = Path(samplesheet_path) if samplesheet_path else None
    if sheet_file is not None and not sheet_file.is_file():
        raise FileNotFoundError(f"Explicit samplesheet does not exist: {sheet_file}")

    samples, design_facts = (
        parse_samplesheet(sheet_file)
        if sheet_file
        else (
            [],
            {
                "sample_count": 0,
                "min_replicates_per_condition": 0,
                "biological_replicates_count": 0,
                "conditions_count": 0,
            },
        )
    )

    # 4. Infer pipeline name & version
    p_name = pipeline_name or "nf-core/pipeline"
    p_ver: Optional[str] = None
    for k, v in versions.items():
        if any(term in k.lower() for term in ("workflow", "nf-core", "pipeline")):
            p_ver = v
            break

    # 5. Harvest primary output artifact digests
    primary_outputs: Dict[str, str] = {}
    for root, _, files in os.walk(rdir):
        for f in files:
            fp = Path(root) / f
            if ".nextflow" in str(fp) or "work" in fp.parts:
                continue
            if any(
                f.endswith(ext)
                for ext in (".tsv", ".csv", ".h5ad", ".vcf.gz", ".bam", ".html", ".parquet", ".json")
            ):
                primary_outputs[fp.relative_to(rdir).as_posix()] = _sha256_file(fp)

    # 6. Execution provenance never creates scientific evidence factors.
    derived_factors: List[str] = []
    min_reps = design_facts.get("min_replicates_per_condition", 0)

    return NextflowExecutionSummary(
        pipeline_name=p_name,
        pipeline_version=p_ver,
        nextflow_version=versions.get("nextflow"),
        execution_status=trace_stats["execution_status"],
        run_dir=str(rdir),
        samplesheet_path=str(sheet_file) if sheet_file else None,
        sample_count=design_facts.get("sample_count", len(samples)),
        samples=samples,
        biological_replicates_count=design_facts.get("biological_replicates_count", len(samples)),
        min_replicates_per_condition=min_reps,
        conditions_count=design_facts.get("conditions_count", 0),
        total_processes=trace_stats["total_processes"],
        succeeded_processes=trace_stats["succeeded_processes"],
        failed_processes=trace_stats["failed_processes"],
        cached_processes=trace_stats["cached_processes"],
        total_cpu_hours=trace_stats["total_cpu_hours"],
        peak_rss_gb=trace_stats["peak_rss_gb"],
        software_versions=versions,
        primary_outputs=primary_outputs,
        derived_evidence_factors=sorted(set(derived_factors)),
    )


def create_nextflow_tool_receipt(
    run_dir: Union[str, Path],
    *,
    pipeline_name: Optional[str] = None,
    samplesheet_path: Optional[Union[str, Path]] = None,
    plugin_version: Optional[str] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a tamper-evident provenance receipt for one Nextflow run.

    A content hash is not a signature. The receipt proves neither producer
    identity nor scientific design, replication, confound control, sensitivity,
    external validation, or warrant.
    """
    summary = harvest_nextflow_run(run_dir, pipeline_name=pipeline_name, samplesheet_path=samplesheet_path)
    p_ver = plugin_version or VERSION

    request_payload = {
        "pipeline_name": summary.pipeline_name,
        "samplesheet_path": summary.samplesheet_path,
        "samplesheet_sha256": _sha256_file(summary.samplesheet_path) if summary.samplesheet_path else None,
    }

    response_payload = {
        "execution_status": summary.execution_status,
        "primary_outputs": summary.primary_outputs,
        "total_processes": summary.total_processes,
        "succeeded_processes": summary.succeeded_processes,
        "failed_processes": summary.failed_processes,
        "total_cpu_hours": summary.total_cpu_hours,
        "software_versions": summary.software_versions,
    }

    meta = {
        "pipeline_name": summary.pipeline_name,
        "pipeline_version": summary.pipeline_version,
        "nextflow_version": summary.nextflow_version,
        "provenance_only": True,
        "scientific_evidence_effect": "NONE",
        "semantic_inference": "DISABLED",
    }
    if extra_metadata:
        forbidden = {
            "evidence_factors",
            "satisfied_factors",
            "declared_factors",
            "sample_design",
            "has_sample_design",
            "replication",
            "replicated",
            "confound_controls",
            "covariates_adjusted",
            "batch_corrected",
            "sensitivity_analysis",
            "parameter_sweep",
            "stability_verified",
            "effect_stability",
            "external_validation",
            "independent_validation",
        }
        overlap = forbidden.intersection(extra_metadata)
        if overlap:
            raise ValueError(
                "Nextflow provenance receipts cannot declare scientific evidence factors: "
                + ", ".join(sorted(overlap))
            )
        meta.update(extra_metadata)

    return create_tool_receipt(
        plugin_id="bionexus-nextflow",
        plugin_version=p_ver,
        tool_name=f"nf-core.{summary.pipeline_name.removeprefix('nf-core/')}",
        request_payload=request_payload,
        response_payload=response_payload,
        execution_status=summary.execution_status,
        metadata=meta,
        receipt_level=ToolReceiptLevel.LEVEL_2_PROVIDER_ATTESTED.value,
        attestation={
            "attested_by": "bionexus-nextflow",
            "attestation_type": "execution_trace_harvest",
            "nextflow_version": summary.nextflow_version,
        },
    )


def generate_nextflow_elastic_config(
    *,
    base_memory_gb: int = 16,
    base_cpus: int = 4,
    max_memory_gb: int = 256,
    max_cpus: int = 32,
    max_retries: int = 3,
    cloud_profile: str = "standard",
    custom_params: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate an elastic, production-ready nextflow.config with dynamic resource scaling on retries.
    Uses Nextflow exponential resource escalation on exit codes 137, 140, and 143 (OOM / Timeout).
    """
    lines = [
        "// Auto-generated by BioNexus Cloud-Native Elastic Infrastructure",
        "manifest {",
        "    name = 'bionexus-elastic-pipeline'",
        "    author = 'BioNexus'",
        "    description = 'Elastic cloud-native Nextflow pipeline with dynamic resource scaling'",
        "    nextflowVersion = '!>=23.04.0'",
        "}",
        "",
        "params {",
        f"    max_memory = '{max_memory_gb}.GB'",
        f"    max_cpus = {max_cpus}",
        "    max_time = '72.h'",
    ]

    if custom_params:
        for k, v in sorted(custom_params.items()):
            val_str = f"'{v}'" if isinstance(v, str) else str(v)
            lines.append(f"    {k} = {val_str}")

    lines.extend([
        "}",
        "",
        "process {",
        "    errorStrategy = { task.exitStatus in [137, 140, 143] ? 'retry' : 'finish' }",
        f"    maxRetries = {max_retries}",
        f"    cpus = {{ check_max( {base_cpus} * task.attempt, 'cpus' ) }}",
        f"    memory = {{ check_max( {base_memory_gb}.GB * task.attempt, 'memory' ) }}",
        "    time = { check_max( 8.h * task.attempt, 'time' ) }",
        "}",
        "",
        "profiles {",
        "    standard {",
        "        process.executor = 'local'",
        "    }",
        "    slurm {",
        "        process.executor = 'slurm'",
        "        process.clusterOptions = '--qos=normal'",
        "        singularity.enabled = true",
        "        singularity.autoMounts = true",
        "    }",
        "    awsbatch {",
        "        process.executor = 'awsbatch'",
        "        process.queue = 'arn:aws:batch:default-queue'",
        "        aws.batch.cliPath = '/home/ec2-user/miniconda/bin/aws'",
        "        docker.enabled = true",
        "    }",
        "    googlebatch {",
        "        process.executor = 'google-batch'",
        "        google.project = 'default-project'",
        "        google.location = 'us-central1'",
        "        docker.enabled = true",
        "    }",
        "    seqera_tower {",
        "        tower.enabled = true",
        "        tower.endpoint = 'https://api.tower.nf'",
        "    }",
        "}",
        "",
        "def check_max(obj, type) {",
        "    if (type == 'memory') {",
        "        try {",
        "            if (obj.compareTo(params.max_memory as nextflow.util.MemoryUnit) == 1)",
        "                return params.max_memory as nextflow.util.MemoryUnit",
        "            else",
        "                return obj",
        "        } catch (all) {",
        "            return obj",
        "        }",
        "    } else if (type == 'time') {",
        "        try {",
        "            if (obj.compareTo(params.max_time as nextflow.util.Duration) == 1)",
        "                return params.max_time as nextflow.util.Duration",
        "            else",
        "                return obj",
        "        } catch (all) {",
        "            return obj",
        "        }",
        "    } else if (type == 'cpus') {",
        "        try {",
        "            return Math.min( obj, params.max_cpus as int )",
        "        } catch (all) {",
        "            return obj",
        "        }",
        "    }",
        "}",
    ])

    return "\n".join(lines) + "\n"

