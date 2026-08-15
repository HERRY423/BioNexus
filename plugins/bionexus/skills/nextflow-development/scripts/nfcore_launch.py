#!/usr/bin/env python3
"""Write an nf-core launch script and optionally run nextflow -preview.

Does not reimplement rnaseq/scrnaseq. Preview requires Nextflow on PATH.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.contracts import GRADE_A, attach_meta, refuse

ALLOWED = ("rnaseq", "scrnaseq")


def build_launch_command(
    *,
    pipeline: str,
    samplesheet: str,
    outdir: str,
    profile: str = "docker",
    extra: Optional[List[str]] = None,
) -> List[str]:
    name = pipeline.removeprefix("nf-core/")
    if name not in ALLOWED:
        raise ValueError(f"Only nf-core/{'/'.join(ALLOWED)} launch artifacts are supported, got {pipeline}")
    cmd = [
        "nextflow",
        "run",
        f"nf-core/{name}",
        "-profile",
        profile,
        "--input",
        samplesheet,
        "--outdir",
        outdir,
    ]
    if extra:
        cmd.extend(extra)
    return cmd


def write_launch_script(cmd: List[str], dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + " ".join(cmd) + "\n", encoding="utf-8")
    return dest


def run_preview(cmd: List[str], timeout: int = 180) -> dict:
    if shutil.which("nextflow") is None:
        return refuse(method="nextflow -preview", reason="nextflow not on PATH")
    preview_cmd = list(cmd) + ["-preview"]
    try:
        proc = subprocess.run(preview_cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return refuse(method="nextflow -preview", reason=f"preview timed out after {timeout}s")
    payload = {
        "command": preview_cmd,
        "returncode": int(proc.returncode),
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-2000:],
    }
    if proc.returncode != 0:
        return attach_meta(
            payload,
            method="nextflow -preview",
            backend="nextflow",
            evidence_grade="C",
            limitations=["Preview failed. The launch script was still written."],
            abstain=True,
            abstain_reason=f"nextflow -preview exited {proc.returncode}",
        )
    return attach_meta(
        payload,
        method="nextflow -preview",
        backend="nextflow",
        evidence_grade=GRADE_A,
        limitations=["Preview only. No pipeline execution."],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="nf-core launch artifact + optional -preview")
    parser.add_argument("--pipeline", required=True, choices=list(ALLOWED))
    parser.add_argument("--samplesheet", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--profile", default="docker")
    parser.add_argument("-o", "--output", required=True, help="Path to write run.sh")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--extra", nargs="*", default=None)
    args = parser.parse_args()
    from check_environment import check_samplesheet

    sheet = check_samplesheet(args.samplesheet)
    if not sheet.passed:
        print(json.dumps(refuse(method="nfcore_launch", reason=sheet.message), indent=2))
        sys.exit(2)
    cmd = build_launch_command(
        pipeline=args.pipeline,
        samplesheet=args.samplesheet,
        outdir=args.outdir,
        profile=args.profile,
        extra=args.extra,
    )
    script = write_launch_script(cmd, Path(args.output))
    contract = attach_meta(
        {"command": cmd, "script": str(script), "samplesheet": args.samplesheet},
        method="nf-core_launch_artifact",
        backend="nextflow",
        evidence_grade=GRADE_A,
        limitations=["Writes a launch script. Does not run the pipeline unless --preview."],
    )
    if args.preview:
        contract["preview"] = run_preview(cmd)
    print(json.dumps(contract, indent=2, default=str))


if __name__ == "__main__":
    main()
