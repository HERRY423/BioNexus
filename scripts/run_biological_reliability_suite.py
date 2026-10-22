"""Run descriptive reference checks and report missing external evidence.

Default execution is read-only. --output-dir writes new rehearsal reports only;
this script never reattests registries, preregistrations, or scientific authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for root in (REPO_ROOT, REPO_ROOT / "src"):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from bionexus.cross_lab_protocol import build_cross_host_dossier
from bionexus.scientific_review_dossier import generate_certified_scientific_review
from evals.annotation_hard_truth_validation import run_benchmark as run_ann_benchmark
from evals.de_hard_truth_benchmark import run_benchmark as run_de_benchmark
from evals.spatial_biological_validity import run_benchmark as run_sp_benchmark


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, help="new, empty output directory for rehearsal artifacts")
    args = parser.parse_args()
    if args.output_dir is not None:
        # Exclusive creation prevents replacing previously frozen evidence.
        args.output_dir.mkdir(parents=True, exist_ok=False)
    reports = []
    for runner in (run_de_benchmark, run_ann_benchmark, run_sp_benchmark):
        reports.append(runner(write=False))
    studies = []
    if args.output_dir is not None:
        for report in reports:
            path = args.output_dir / (report["study_id"] + ".json")
            with path.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
            studies.append((report["capability_id"], report["study_id"], path))
    cross = build_cross_host_dossier(repo_root=REPO_ROOT, studies_to_compare=studies).to_dict()
    review = generate_certified_scientific_review(REPO_ROOT, write=False).to_dict()
    summary = {
        "execution_status": "COMPLETED_DESCRIPTIVE_CHECKS",
        "scientific_authorization": "NONE", "independent_validation_status": "NOT_ESTABLISHED",
        "reports": [{"study_id": r["study_id"], "status": r["status"], "evidence_kind": r["evidence_kind"]} for r in reports],
        "cross_host_status": cross["status"], "review_status": review["status"],
    }
    if args.output_dir is not None:
        for name, payload in (("MULTI_LAB_DOSSIER.json", cross), ("SCIENTIFIC_REVIEW.json", review), ("SUMMARY.json", summary)):
            with (args.output_dir / name).open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary, indent=2))
    return 0  # Successful computation, explicitly not a scientific validation pass.


if __name__ == "__main__":
    raise SystemExit(main())
