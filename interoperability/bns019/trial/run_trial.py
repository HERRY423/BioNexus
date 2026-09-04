#!/usr/bin/env python3
"""Run the local BNS-019 interoperability trial without inflating missing tracks."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
INTEROP_ROOT = REPOSITORY_ROOT / "interoperability" / "bns019"
DEFAULT_STANDARD_ROOT = REPOSITORY_ROOT / "standards" / "scientific-semantic-conventions"
TRIAL_ID = "BNS019-INTEROP-2026-01"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_version(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (completed.stdout or completed.stderr).strip().splitlines()
    return output[0] if output else None


def run(command: list[str], *, cwd: Path = REPOSITORY_ROOT, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, check=False, capture_output=True, text=True, timeout=timeout)


def track(track_id: str, status: str, evidence: dict[str, Any], reason: str | None = None) -> dict[str, Any]:
    return {"id": track_id, "status": status, "evidence": evidence, "reason": reason}


def load_validator():
    path = INTEROP_ROOT / "python" / "bns019_validator.py"
    spec = importlib.util.spec_from_file_location("bns019_local_trial_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Python validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--standard-root", type=Path, default=DEFAULT_STANDARD_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)

    executed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    run_id = args.run_id or f"local-{executed_at.replace(':', '').replace('-', '')}"
    validator = load_validator()
    manifest, _ = validator.load_verified_release(args.standard_root)
    tracks: list[dict[str, Any]] = []
    python_result: dict[str, Any] | None = None
    r_result: dict[str, Any] | None = None
    ts_result: dict[str, Any] | None = None

    with tempfile.TemporaryDirectory(prefix="bns019-interop-") as temporary:
        temp = Path(temporary)

        python_output = temp / "python-result.json"
        python_command = [
            sys.executable,
            str(INTEROP_ROOT / "python" / "bns019_validator.py"),
            "--standard-root",
            str(args.standard_root),
            "--output",
            str(python_output),
        ]
        completed = run(python_command)
        if completed.returncode == 0 and python_output.is_file():
            python_result = json.loads(python_output.read_text(encoding="utf-8"))
            tracks.append(
                track(
                    "python-validator",
                    "PASS" if python_result["status"] == "PASS" else "FAIL",
                    {
                        "implementation": python_result["implementation"]["id"],
                        "cases_passed": sum(case["status"] == "PASS" for case in python_result["case_results"]),
                        "cases_total": len(python_result["case_results"]),
                        "result_sha256": sha256_file(python_output),
                    },
                )
            )
        else:
            tracks.append(
                track("python-validator", "FAIL", {"exit_code": completed.returncode}, completed.stderr[-1000:])
            )

        rscript = shutil.which("Rscript")
        r_ready = False
        if rscript:
            preflight = run(
                [
                    rscript,
                    "-e",
                    "cat(requireNamespace('jsonlite',quietly=TRUE) && requireNamespace('digest',quietly=TRUE))",
                ],
                timeout=60,
            )
            r_ready = preflight.returncode == 0 and preflight.stdout.strip().endswith("TRUE")
        if not r_ready:
            tracks.append(track("r-validator", "NOT_RUN", {}, "Rscript with jsonlite and digest is unavailable"))
        else:
            r_output = temp / "r-result.json"
            completed = run(
                [
                    rscript,
                    str(INTEROP_ROOT / "r" / "bns019_validator.R"),
                    "--standard-root",
                    str(args.standard_root),
                    "--output",
                    str(r_output),
                ]
            )
            if completed.returncode == 0 and r_output.is_file():
                r_result = json.loads(r_output.read_text(encoding="utf-8"))
                tracks.append(
                    track(
                        "r-validator",
                        "PASS" if r_result["status"] == "PASS" else "FAIL",
                        {
                            "implementation": r_result["implementation"]["id"],
                            "cases_passed": sum(case["status"] == "PASS" for case in r_result["case_results"]),
                            "cases_total": len(r_result["case_results"]),
                            "result_sha256": sha256_file(r_output),
                        },
                    )
                )
            else:
                tracks.append(
                    track("r-validator", "FAIL", {"exit_code": completed.returncode}, completed.stderr[-1000:])
                )

        node_bin = shutil.which("node")
        if not node_bin:
            tracks.append(track("typescript-validator", "NOT_RUN", {}, "node is unavailable"))
        else:
            ts_output = temp / "typescript-result.json"
            ts_cli = INTEROP_ROOT / "typescript" / "src" / "cli.ts"
            completed = run(
                [
                    node_bin,
                    str(ts_cli),
                    "--standard-root",
                    str(args.standard_root),
                    "--output",
                    str(ts_output),
                ]
            )
            if completed.returncode == 0 and ts_output.is_file():
                ts_result = json.loads(ts_output.read_text(encoding="utf-8"))
                tracks.append(
                    track(
                        "typescript-validator",
                        "PASS" if ts_result["status"] == "PASS" else "FAIL",
                        {
                            "implementation": ts_result["implementation"]["id"],
                            "cases_passed": sum(case["status"] == "PASS" for case in ts_result["case_results"]),
                            "cases_total": len(ts_result["case_results"]),
                            "result_sha256": sha256_file(ts_output),
                        },
                    )
                )
            else:
                tracks.append(
                    track("typescript-validator", "FAIL", {"exit_code": completed.returncode}, completed.stderr[-1000:])
                )

        if importlib.util.find_spec("anndata") is None or importlib.util.find_spec("numpy") is None:
            tracks.append(track("scanpy-anndata-adapter", "NOT_RUN", {}, "anndata and numpy are unavailable"))
        else:
            import anndata as ad
            import numpy as np

            scanpy_input = temp / "scanpy-input.h5ad"
            scanpy_output = temp / "scanpy-output.h5ad"
            scanpy_result = temp / "scanpy-result.json"
            ad.AnnData(np.asarray([[1, 0], [0, 2]], dtype="int32")).write_h5ad(scanpy_input)
            completed = run(
                [
                    sys.executable,
                    str(INTEROP_ROOT / "scanpy" / "bns019_scanpy_adapter.py"),
                    "--input",
                    str(scanpy_input),
                    "--output",
                    str(scanpy_output),
                    "--standard-root",
                    str(args.standard_root),
                    "--semantics",
                    str(args.standard_root / "conformance" / "valid" / "observation.json"),
                    "--result",
                    str(scanpy_result),
                ]
            )
            if completed.returncode == 0 and scanpy_result.is_file():
                result = json.loads(scanpy_result.read_text(encoding="utf-8"))
                tracks.append(
                    track(
                        "scanpy-anndata-adapter",
                        result["status"],
                        {"checks": result["checks"], "result_sha256": sha256_file(scanpy_result)},
                    )
                )
            else:
                tracks.append(
                    track(
                        "scanpy-anndata-adapter", "FAIL", {"exit_code": completed.returncode}, completed.stderr[-1000:]
                    )
                )

        seurat_ready = False
        if rscript:
            preflight = run(
                [
                    rscript,
                    "-e",
                    "cat(requireNamespace('jsonlite',quietly=TRUE) && requireNamespace('digest',quietly=TRUE) && requireNamespace('SeuratObject',quietly=TRUE))",
                ],
                timeout=60,
            )
            seurat_ready = preflight.returncode == 0 and preflight.stdout.strip().endswith("TRUE")
        if not seurat_ready:
            tracks.append(
                track("seurat-adapter", "NOT_RUN", {}, "Rscript with jsonlite, digest, and SeuratObject is unavailable")
            )
        else:
            seurat_input = temp / "seurat-input.rds"
            seurat_output = temp / "seurat-output.rds"
            seurat_result = temp / "seurat-result.json"
            create = run(
                [
                    rscript,
                    "-e",
                    (
                        "suppressPackageStartupMessages(library(SeuratObject));"
                        "x<-matrix(as.integer(c(1,0,0,2)),nrow=2,dimnames=list(c('G1','G2'),c('C1','C2')));"
                        f"saveRDS(CreateSeuratObject(counts=x),'{seurat_input.as_posix()}',version=3)"
                    ),
                ]
            )
            completed = (
                run(
                    [
                        rscript,
                        str(INTEROP_ROOT / "seurat" / "bns019_seurat_adapter.R"),
                        "--input",
                        str(seurat_input),
                        "--output",
                        str(seurat_output),
                        "--standard-root",
                        str(args.standard_root),
                        "--semantics",
                        str(args.standard_root / "conformance" / "valid" / "observation.json"),
                        "--result",
                        str(seurat_result),
                    ]
                )
                if create.returncode == 0
                else create
            )
            if completed.returncode == 0 and seurat_result.is_file():
                result = json.loads(seurat_result.read_text(encoding="utf-8"))
                tracks.append(
                    track(
                        "seurat-adapter",
                        result["status"],
                        {"checks": result["checks"], "result_sha256": sha256_file(seurat_result)},
                    )
                )
            else:
                tracks.append(
                    track("seurat-adapter", "FAIL", {"exit_code": completed.returncode}, completed.stderr[-1000:])
                )

        nfcore_record = temp / "nfcore-record.json"
        nfcore_versions = temp / "nfcore-versions.yml"
        core_completed = run(
            [
                sys.executable,
                str(INTEROP_ROOT / "nf-core" / "bin" / "bns019_nfcore_adapter.py"),
                "--validator",
                str(INTEROP_ROOT / "python" / "bns019_validator.py"),
                "--standard-root",
                str(args.standard_root),
                "--record",
                str(Path(__file__).parent / "fixtures" / "workflow-record.json"),
                "--semantics",
                str(args.standard_root / "conformance" / "valid" / "observation.json"),
                "--output",
                str(nfcore_record),
                "--versions",
                str(nfcore_versions),
            ]
        )
        nextflow = shutil.which("nextflow")
        core_evidence = {
            "adapter_core_status": "PASS" if core_completed.returncode == 0 else "FAIL",
            "adapter_core_result_sha256": sha256_file(nfcore_record) if nfcore_record.is_file() else None,
        }
        if not nextflow:
            tracks.append(
                track(
                    "nfcore-nextflow-adapter",
                    "NOT_RUN" if core_completed.returncode == 0 else "FAIL",
                    core_evidence,
                    "Nextflow runtime is unavailable; adapter-core execution is not counted as workflow conformance",
                )
            )
        else:
            nf_results = temp / "nextflow-results"
            completed = run(
                [
                    nextflow,
                    "run",
                    str(INTEROP_ROOT / "nf-core"),
                    "--record",
                    str(Path(__file__).parent / "fixtures" / "workflow-record.json"),
                    "--semantics",
                    str(args.standard_root / "conformance" / "valid" / "observation.json"),
                    "--standard_root",
                    str(args.standard_root),
                    "--outdir",
                    str(nf_results),
                    "-work-dir",
                    str(temp / "nextflow-work"),
                ],
                timeout=300,
            )
            produced = list(nf_results.glob("*.bns019.json"))
            if completed.returncode == 0 and produced:
                core_evidence["nextflow_output_sha256"] = sha256_file(produced[0])
                tracks.append(track("nfcore-nextflow-adapter", "PASS", core_evidence))
            else:
                tracks.append(
                    track(
                        "nfcore-nextflow-adapter",
                        "FAIL",
                        core_evidence | {"exit_code": completed.returncode},
                        completed.stderr[-1000:],
                    )
                )

    compared_validators: list[tuple[str, dict[str, Any]]] = []
    if python_result is not None:
        compared_validators.append(("bns019-python-stdlib", python_result))
    if r_result is not None:
        compared_validators.append(("bns019-r-jsonlite", r_result))
    if ts_result is not None:
        compared_validators.append(("bns019-typescript", ts_result))

    if len(compared_validators) >= 2:
        case_maps = [
            (
                name,
                {
                    case["case_id"]: (case["observed_valid"], case["normalized_attributes"], case["failure_classes"])
                    for case in res["case_results"]
                },
            )
            for name, res in compared_validators
        ]
        first_name, first_map = case_maps[0]
        agreed = all(m == first_map for _, m in case_maps[1:])
        agreement_status = "PASS" if agreed else "FAIL"
        agreement = {
            "status": agreement_status,
            "compared_implementations": [name for name, _ in compared_validators],
            "reason": None if agreement_status == "PASS" else "Normalized results or failure classes differ",
        }
    else:
        agreement = {
            "status": "NOT_RUN",
            "compared_implementations": [name for name, _ in compared_validators],
            "reason": "At least two independent validator results are required",
        }

    statuses = [item["status"] for item in tracks]
    if "FAIL" in statuses or "ERROR" in statuses or agreement["status"] == "FAIL":
        overall = "FAIL"
    elif all(status == "PASS" for status in statuses) and agreement["status"] == "PASS":
        overall = "PASS"
    else:
        overall = "INCOMPLETE"
    result = {
        "schema": "urn:bionexus:bns019-trial-run-result:1",
        "trial_id": TRIAL_ID,
        "run_id": run_id,
        "executed_at": executed_at,
        "environment": {
            "operating_system": platform.platform(),
            "python": sys.version.split()[0],
            "r": command_version(["Rscript", "--version"]),
            "node": command_version(["node", "--version"]),
            "nextflow": command_version(["nextflow", "-version"]),
        },
        "standard": {
            "id": "BNS-019",
            "version": manifest["version"],
            "release_digest_sha256": manifest["release_digest_sha256"],
        },
        "tracks": tracks,
        "cross_implementation_agreement": agreement,
        "overall_status": overall,
        "claim_boundary": (
            "This is a local maintainer self-test of software-contract interoperability. "
            "It is not a public external trial result, badge, certification, endorsement, or biological validation."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if overall == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
