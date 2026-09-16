"""Execute the named compatibility controls against the frozen candidate."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SNAPSHOT = HERE / "attempt-02/candidate-source"
CASES = REPO / "review/methods-experiments-2026-09-08/run-01/challenge/cases"
OUTPUT = HERE / "attempt-02/CONTROL_RESULTS.json"


def load_auditor():
    sys.path.insert(0, str(SNAPSHOT))
    for name in [n for n in sys.modules if n == "bionexus" or n.startswith("bionexus.")]:
        del sys.modules[name]
    return importlib.import_module("bionexus.de_audit").audit_differential_expression


def audit_case(audit, case_id: str, *, receipt_change=None, metadata_in_memory=False):
    folder = CASES / case_id
    definition = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
    if receipt_change:
        receipt_change(receipt, folder)
    metadata = pd.read_csv(folder / "metadata.csv") if metadata_in_memory else folder / "metadata.csv"
    return audit(
        de_table=folder / "de.csv", sample_metadata=metadata, execution_record=receipt,
        claim_text=definition["claim"], donor_col="donor", condition_col="condition",
    )


def rule(result, rule_id: str) -> bool:
    return any(finding.rule_id == rule_id for finding in result.findings)


def binding(result) -> str:
    check = next(c for c in result.checks if c.check_id == "analysis_execution_binding")
    return str(getattr(check.status, "value", check.status))


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite {OUTPUT}")
    audit = load_auditor()
    results = []

    def record(control_id, category, expected, result, passed):
        results.append({
            "control_id": control_id, "category": category, "expected": expected,
            "observed_status": result.overall_status, "observed_passed": bool(result.passed),
            "binding_status": binding(result),
            "rule_ids": [finding.rule_id for finding in result.findings],
            "control_passed": bool(passed),
        })

    def explicit(receipt, folder):
        metadata = pd.read_csv(folder / "metadata.csv")
        receipt["donor_ids"] = sorted(metadata["donor"].astype(str).unique())

    outcome = audit_case(audit, "valid_positive-0", receipt_change=explicit)
    record("LEGIT-001", "legitimate_positive", "ROBUST_PASS", outcome, outcome.passed)
    outcome = audit_case(audit, "valid_negative-0")
    record("LEGIT-002", "legitimate_nonsignificant_conclusion", "ROBUST_PASS", outcome, outcome.passed)
    outcome = audit_case(audit, "valid_limited-0")
    record("LEGIT-003", "legitimate_limitation", "ROBUST_PASS", outcome, outcome.passed)

    outcome = audit_case(audit, "valid_positive-0", metadata_in_memory=True)
    record("NEG-001", "negative_control", "MISSING_EVIDENCE", outcome,
           not outcome.passed and binding(outcome) == "MISSING_EVIDENCE")

    variants = []
    for bad in ("0" * 64, "not-a-digest", "f" * 64):
        def bad_hash(receipt, _folder, value=bad):
            receipt["sample_metadata_sha256"] = value
        variant = audit_case(audit, "valid_positive-0", receipt_change=bad_hash)
        variants.append(variant)
    exemplar = variants[-1]
    record("NEG-002", "negative_control", "BFA-013e BLOCKER for zero/malformed/mismatch", exemplar,
           all(not item.passed and item.overall_status == "BLOCKER_DETECTED" and rule(item, "BFA-013e")
               for item in variants))

    def malformed_ids(receipt, _folder):
        receipt["donor_ids"] = ["duplicate", "duplicate"]
    outcome = audit_case(audit, "valid_positive-0", receipt_change=malformed_ids)
    record("NEG-003", "negative_control", "reject malformed donor_ids without legacy fallback", outcome,
           not outcome.passed and binding(outcome) == "ISSUE_FOUND")

    for control_id, case_id, rule_id in (
        ("NEG-004", "failed_fit-0", "BFA-013b"),
        ("NEG-005", "wrong_design-0", "BFA-013c"),
        ("NEG-006", "false_global_null-0", "BFA-015c"),
        ("NEG-007", "causal_overclaim-0", "BFA-008"),
    ):
        outcome = audit_case(audit, case_id)
        record(control_id, "negative_control", f"reject through {rule_id}", outcome,
               not outcome.passed and rule(outcome, rule_id))

    payload = {
        "schema": "bionexus.de-compatibility-control-results.v1",
        "status": "PASS" if len(results) == 10 and all(row["control_passed"] for row in results) else "FAIL",
        "candidate_source": "attempt-02/candidate-source",
        "controls": results,
        "evidence_ceiling": "LOCAL_CONTRACT_AND_DEVELOPER_REGRESSION_CONTROLS",
        "scientific_authorization": "NONE",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
