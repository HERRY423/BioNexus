#!/usr/bin/env python3
"""Actually execute an nf-core launch script, wrapped in a full Run Capsule.

Complements nfcore_launch.py (which only writes run.sh): this module runs the launch
script for real when Nextflow is available, captures exit status and logs, and records
a cryptographically verifiable Run Capsule (execution fidelity + provenance). It never
simulates success: a missing Nextflow or a non-zero exit is reported honestly.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.artifacts import RunBundle
from bionexus.contracts import (
    GRADE_A,
    ConclusionMaturity,
    DimensionGrade,
    EvidenceCard,
    ExecutionState,
    attach_meta,
    refuse,
)

CONTAINER_ENGINES = ("docker", "singularity", "apptainer", "podman")


def probe_execution_environment() -> Dict[str, Optional[str]]:
    """Locate nextflow, bash, and the first available container engine (advisory)."""
    container = next((engine for engine in CONTAINER_ENGINES if shutil.which(engine)), None)
    return {
        "nextflow": shutil.which("nextflow"),
        "bash": shutil.which("bash"),
        "container_engine": container,
    }


def execute_launch_script(
    script_path: str | Path,
    *,
    outdir: Optional[str] = None,
    capsule_root: str | Path = "runs",
    timeout_seconds: int = 86400,
    dry_run: bool = False,
) -> Dict:
    """Run a launch script and wrap the execution in a Run Capsule contract payload."""
    script = Path(script_path)
    probes = probe_execution_environment()
    env_notes = {
        "nextflow_path": probes["nextflow"],
        "bash_path": probes["bash"],
        "container_engine": probes["container_engine"],
    }

    if not script.is_file():
        return refuse(
            method="nf-core_execute",
            reason=f"Launch script not found: {script}",
            extra={"environment": env_notes},
        )
    if probes["nextflow"] is None:
        return refuse(
            method="nf-core_execute",
            reason=(
                "nextflow is not on PATH. BioNexus refuses to simulate pipeline execution. "
                "Install Nextflow (https://www.nextflow.io/) or run the launch script on an "
                "HPC/cloud host that provides it."
            ),
            extra={"environment": env_notes},
        )
    if probes["bash"] is None:
        return refuse(
            method="nf-core_execute",
            reason=(
                "bash is not available on this host, so the bash launch script cannot run. "
                "Use WSL, Git Bash, or a POSIX host."
            ),
            extra={"environment": env_notes},
        )

    if dry_run:
        return attach_meta(
            {
                "refused": False,
                "execution_plan": {
                    "script": str(script),
                    "environment": env_notes,
                    "timeout_seconds": timeout_seconds,
                },
            },
            method="nf-core_execute",
            backend="nextflow",
            limitations=["Dry run only. The pipeline was not executed."],
            execution_state=ExecutionState.PERMITTED.value,
            conclusion_maturity=ConclusionMaturity.UNASSESSED.value,
        )

    capsule_dir = Path(capsule_root) / f"nfcore_execute_{script.stem}"
    bundle = RunBundle.create(
        capsule_dir,
        capability_id="nextflow.pipeline_execute",
        skill_name="nextflow-development",
    )
    bundle.record_input("launch_script", script, semantic_type="pipeline_launch_script")
    bundle.record_parameters(
        script=str(script),
        outdir=outdir,
        timeout_seconds=timeout_seconds,
        **env_notes,
    )

    try:
        proc = subprocess.run(  # noqa: S603 - fixed argv ['bash', script], no shell
            [probes["bash"], str(script)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        returncode = int(proc.returncode)
        stdout_tail = (proc.stdout or "")[-8000:]
        stderr_tail = (proc.stderr or "")[-8000:]
    except subprocess.TimeoutExpired:
        returncode = -1
        stdout_tail = ""
        stderr_tail = f"Pipeline execution timed out after {timeout_seconds}s (fail-closed)."
    except OSError as e:
        returncode = -1
        stdout_tail = ""
        stderr_tail = f"OS error while launching nextflow: {e}"

    (bundle.logs_dir / "pipeline_stdout.log").write_text(stdout_tail, encoding="utf-8")
    (bundle.logs_dir / "pipeline_stderr.log").write_text(stderr_tail, encoding="utf-8")
    bundle.log(f"Executed '{script}' with bash; returncode={returncode}.")

    if returncode != 0:
        card = EvidenceCard(
            execution_state=ExecutionState.FAILED.value,
            input_integrity=DimensionGrade.UNTESTED.value,
            assumption_validity=DimensionGrade.UNTESTED.value,
            statistical_support=DimensionGrade.UNTESTED.value,
            parameter_robustness=DimensionGrade.UNTESTED.value,
            cross_method_concordance=DimensionGrade.UNTESTED.value,
            external_validation=DimensionGrade.UNTESTED.value,
            details={"execution_backend": "nextflow", "returncode": returncode},
        )
        bundle.attach_evidence_card(card)
        bundle.finalize(status="FAILED")
        payload = {
            "execution": {
                "script": str(script),
                "returncode": returncode,
                "stdout_tail": stdout_tail[-2000:],
                "stderr_tail": stderr_tail[-2000:],
                "capsule_dir": str(capsule_dir),
                "environment": env_notes,
            }
        }
        return attach_meta(
            payload,
            method="nf-core_execute",
            backend="nextflow",
            evidence_grade="abstain",
            execution_state=ExecutionState.FAILED.value,
            abstain=True,
            abstain_reason=f"Pipeline exited with returncode {returncode}. The Run Capsule records the failure.",
            conclusion_maturity=ConclusionMaturity.ABSTAIN.value,
            limitations=[
                "Pipeline execution failed. Downstream biological conclusions must NOT be drawn.",
            ],
        )

    out_path = Path(outdir) if outdir else None
    if out_path is not None and out_path.is_dir():
        produced = sorted(p.name for p in out_path.iterdir())
        bundle.log(f"Output directory '{out_path}' contains {len(produced)} entries after execution.")
    else:
        produced = None

    card = EvidenceCard(
        execution_state=ExecutionState.EXECUTED.value,
        input_integrity=DimensionGrade.UNTESTED.value,
        assumption_validity=DimensionGrade.UNTESTED.value,
        statistical_support=DimensionGrade.UNTESTED.value,
        parameter_robustness=DimensionGrade.UNTESTED.value,
        cross_method_concordance=DimensionGrade.UNTESTED.value,
        external_validation=DimensionGrade.UNTESTED.value,
        details={
            "execution_backend": "nextflow",
            "note": (
                "Official nf-core pipeline executed via Nextflow. Pipeline outputs require QA and "
                "biological interpretation before any conclusion."
            ),
        },
    )
    bundle.attach_evidence_card(card)
    bundle.finalize(status="COMPLETED")
    return attach_meta(
        {
            "refused": False,
            "execution": {
                "script": str(script),
                "returncode": 0,
                "stdout_tail": stdout_tail[-2000:],
                "stderr_tail": stderr_tail[-2000:],
                "outdir_entries": produced,
                "capsule_dir": str(capsule_dir),
                "environment": env_notes,
            },
        },
        method="nf-core_execute",
        backend="nextflow",
        evidence_grade=GRADE_A,
        conclusion_maturity=ConclusionMaturity.PRELIMINARY.value,
        limitations=[
            "Execution fidelity only: pipeline outputs still require QC and biological interpretation.",
            "Container engine status is advisory; verify the resolved profile matched your intent.",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute an nf-core launch script with capsule capture")
    parser.add_argument("--script", required=True, help="Launch script written by nfcore_launch.py")
    parser.add_argument("--outdir", default=None, help="Pipeline output directory (recorded if it exists)")
    parser.add_argument("--capsule-root", default="runs", help="Directory for the Run Capsule")
    parser.add_argument("--timeout", type=int, default=86400, help="Execution timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Probe the environment without executing")
    args = parser.parse_args()

    payload = execute_launch_script(
        args.script,
        outdir=args.outdir,
        capsule_root=args.capsule_root,
        timeout_seconds=args.timeout,
        dry_run=args.dry_run,
    )
    print(json.dumps(payload, indent=2, default=str))
    sys.exit(2 if payload.get("refused") or payload.get("abstain") else 0)


if __name__ == "__main__":
    main()
