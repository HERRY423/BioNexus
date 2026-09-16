"""Post-run check that each frozen family triggered its intended mechanism."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "attempt-02" / "run-01" / "cases"
OUTPUT = ROOT / "attempt-02" / "DIAGNOSTIC_MAPPING.json"

EXPECTED_RULE = {
    "absent_gene": "BFA-014",
    "causal_overclaim": "BFA-008",
    "changed_result": "BFA-013a",
    "clinical_overclaim": "BFA-008",
    "failed_fit": "BFA-013b",
    "false_global_null": "BFA-015c",
    "false_negative": "BFA-015b",
    "false_significance": "BFA-015a",
    "invalid_probability": "BFA-003c",
    "missing_fdr": "BFA-003",
    "wrong_design": "BFA-013c",
    "wrong_direction": "BFA-015d",
    "wrong_result_hash": "BFA-013a",
}
VALID_FAMILIES = {"valid_limited", "valid_negative", "valid_positive", "valid_table_presence"}


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")
    records = []
    for path in sorted(CASES.glob("*.json")):
        family = path.stem.rsplit("-", 1)[0]
        payload = json.loads(path.read_text(encoding="utf-8"))
        rules = {finding["rule_id"] for finding in payload["findings"]}
        severe = {
            finding["rule_id"]
            for finding in payload["findings"]
            if finding["severity"] in {"HIGH_IMPACT", "BLOCKER"}
        }
        checks = {check["check_id"]: check["status"] for check in payload["checks"]}
        if family in EXPECTED_RULE:
            expected = EXPECTED_RULE[family]
            passed = expected in severe and payload["overall_status"] != "ROBUST_PASS"
            mechanism = f"severe finding {expected}"
        elif family == "missing_receipt":
            passed = (
                checks.get("analysis_execution_binding") == "MISSING_EVIDENCE"
                and payload["overall_status"] != "ROBUST_PASS"
            )
            mechanism = "analysis_execution_binding=MISSING_EVIDENCE"
        elif family in VALID_FAMILIES:
            passed = payload["overall_status"] == "ROBUST_PASS" and not severe
            mechanism = "ROBUST_PASS with no HIGH_IMPACT/BLOCKER finding"
        else:
            passed = False
            mechanism = "unregistered family"
        records.append({
            "case_id": path.stem,
            "family": family,
            "passed": passed,
            "expected_mechanism": mechanism,
            "observed_rules": sorted(rules),
            "observed_status": payload["overall_status"],
        })
    result = {
        "status": "PASS" if len(records) == 54 and all(record["passed"] for record in records) else "FAIL",
        "scope": "POST_OUTCOME_DESCRIPTIVE_MECHANISM_CHECK",
        "cases_checked": len(records),
        "cases_matching_expected_mechanism": sum(record["passed"] for record in records),
        "records": records,
        "evidence_ceiling": "LOCAL_DEVELOPER_LABELLED_REGRESSION_ONLY",
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2, ensure_ascii=False))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
