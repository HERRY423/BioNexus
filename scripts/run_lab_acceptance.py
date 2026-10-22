#!/usr/bin/env python3
"""Run fixture-backed lab import/export acceptance for every matrix product."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bionexus.lab_exchange import accept_lab_roundtrip  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "lab_exchange"
SOURCES = {
    "cellranger": FIXTURES / "cellranger" / "outs",
    "seurat": FIXTURES / "seurat",
    "scanpy": FIXTURES / "scanpy",
    "deseq2": FIXTURES / "deseq2" / "results.csv",
    "edger": FIXTURES / "edger" / "results.tsv",
    "nf-core": FIXTURES / "nfcore",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="New output directory for durable fixture receipts")
    args = parser.parse_args()
    dest_root = args.output_dir or ROOT / ".artifacts" / "lab-acceptance" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if dest_root.exists() and any(dest_root.iterdir()):
        parser.error(f"output directory is not empty: {dest_root}")
    dest_root.mkdir(parents=True, exist_ok=True)
    failed = 0
    reports = []
    for product, source in SOURCES.items():
        report = accept_lab_roundtrip(source, dest_root / product, data_classification="PUBLIC_BENCHMARK")
        reports.append(report.to_dict())
        status = "PASS" if report.passed else "FAIL"
        print(f"[{status}] {product}: {report.receipt_path}")
        if not report.passed:
            failed += 1
            print(json.dumps(report.to_dict(), indent=2))
    (dest_root / "summary.json").write_text(json.dumps({
        "scope": "COMMITTED_FIXTURES_ONLY_NOT_LAB_VALIDATION",
        "passed": not failed, "reports": reports,
    }, indent=2) + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
