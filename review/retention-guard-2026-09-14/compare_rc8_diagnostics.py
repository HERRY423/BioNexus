"""Compare family-specific mechanism hits between frozen rc.8 and candidate outputs."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
OLD = REPO / "review" / "rc8-challenge-rerun-2026-09-14" / "run-01" / "cases"
NEW = ROOT / "attempt-02" / "run-01" / "cases"
OUTPUT = ROOT / "attempt-02" / "RC8_DIAGNOSTIC_COMPARISON.json"

EXPECTED = {
    "absent_gene": "BFA-014", "causal_overclaim": "BFA-008", "changed_result": "BFA-013a",
    "clinical_overclaim": "BFA-008", "failed_fit": "BFA-013b", "false_global_null": "BFA-015c",
    "false_negative": "BFA-015b", "false_significance": "BFA-015a", "invalid_probability": "BFA-003c",
    "missing_fdr": "BFA-003", "wrong_design": "BFA-013c", "wrong_direction": "BFA-015d",
    "wrong_result_hash": "BFA-013a",
}


def evaluate(old: bool) -> list[dict]:
    records = []
    base = OLD if old else NEW
    for case_path in sorted(base.iterdir() if old else base.glob("*.json")):
        if old:
            definition = json.loads((case_path / "case.json").read_text(encoding="utf-8"))
            if not definition["invalid"]:
                continue
            payload = json.loads((case_path / "bionexus_full.json").read_text(encoding="utf-8"))
            case_id = definition["case_id"]
            family = definition["family"]
        else:
            case_id = case_path.stem
            family = case_id.rsplit("-", 1)[0]
            if family.startswith("valid_"):
                continue
            payload = json.loads(case_path.read_text(encoding="utf-8"))
        severe = {f["rule_id"] for f in payload["findings"] if f["severity"] in {"HIGH_IMPACT", "BLOCKER"}}
        checks = {c["check_id"]: c["status"] for c in payload["checks"]}
        if family == "missing_receipt":
            match = checks.get("analysis_execution_binding") == "MISSING_EVIDENCE"
            expected = "analysis_execution_binding=MISSING_EVIDENCE"
        else:
            expected = EXPECTED[family]
            match = expected in severe
        records.append({"case_id": case_id, "family": family, "expected": expected, "match": match})
    return records


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUTPUT}")
    old = evaluate(True)
    new = evaluate(False)
    result = {
        "status": "PASS" if len(old) == len(new) == 42 and sum(r["match"] for r in new) == 42 else "FAIL",
        "scope": "POST_OUTCOME_DESCRIPTIVE_MECHANISM_COMPARISON",
        "rc8_matches": sum(r["match"] for r in old),
        "rc8_total": len(old),
        "candidate_matches": sum(r["match"] for r in new),
        "candidate_total": len(new),
        "rc8_misses": [r for r in old if not r["match"]],
        "candidate_misses": [r for r in new if not r["match"]],
    }
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
