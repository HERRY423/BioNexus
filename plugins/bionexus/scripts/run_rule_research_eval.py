"""Run developer-case rule rehearsals; no independent scientific calibration.

Default execution is read-only. New output is written only to --output-dir.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
for root in (_REPO_ROOT, _REPO_ROOT / "src"):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from bionexus.rules.holdout_evaluator import RuleHoldoutEvaluator
from bionexus.rules.ladder_comparison import run_ladder_vs_static_comparison


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", type=Path, default=_REPO_ROOT / "validation/rules/frozen_holdout_benchmark.json")
    parser.add_argument("--output-dir", type=Path, help="new, empty directory for developer-case reports")
    args = parser.parse_args()
    evaluator = RuleHoldoutEvaluator(args.benchmark)
    result = evaluator.run_evaluation()
    comparison = run_ladder_vs_static_comparison(args.benchmark)
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        evaluator.write_calibration_card(result, args.output_dir)
        with (args.output_dir / "LADDER_VS_STATIC_REPORT.json").open("x", encoding="utf-8") as handle:
            json.dump(comparison.to_dict(), handle, indent=2, allow_nan=False)
            handle.write("\n")
    print(json.dumps({"execution_status": "COMPLETED_DEVELOPER_REHEARSAL",
                      "evidence_kind": "DEVELOPER_CASE_FIXTURE", "scientific_authorization": "NONE",
                      "independent_calibration": "NOT_ESTABLISHED",
                      "overall_metrics": result.overall_metrics.to_dict(),
                      "comparison": comparison.to_dict()}, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
