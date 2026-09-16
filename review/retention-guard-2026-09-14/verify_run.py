"""Independently recompute retention-guard identity, input, and outcome checks."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ATTEMPT = ROOT / "attempt-02"
RUN = ATTEMPT / "run-01"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate(items: dict[str, str]) -> str:
    return hashlib.sha256(
        "\n".join(f"{name} {items[name]}" for name in sorted(items)).encode("utf-8")
    ).hexdigest()


def main() -> None:
    identity = json.loads((ATTEMPT / "IDENTITY.json").read_text(encoding="utf-8"))
    manifest = json.loads((ATTEMPT / "INPUT_MANIFEST.json").read_text(encoding="utf-8"))
    summary = json.loads((RUN / "summary.json").read_text(encoding="utf-8"))
    end = json.loads((RUN / "execution-end.json").read_text(encoding="utf-8"))

    source_hashes = {}
    for path in sorted(item for item in (ATTEMPT / "candidate-source").rglob("*") if item.is_file()):
        if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
            continue
        rel = path.relative_to(ATTEMPT / "candidate-source").as_posix()
        source_hashes[rel] = sha(path)
    input_hashes = {}
    repo = ROOT.parents[1]
    for rel in manifest["files"]:
        input_hashes[rel] = sha(repo / rel)

    with (RUN / "case-outcomes.csv").open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    valid = [row for row in rows if row["invalid"].lower() == "false"]
    invalid = [row for row in rows if row["invalid"].lower() == "true"]
    def accepted(row: dict[str, str]) -> bool:
        return row["accepted"].lower() == "true"

    def high(row: dict[str, str]) -> bool:
        return row["high_or_blocker"].lower() == "true"
    case_files = sorted((RUN / "cases").glob("*.json"))
    case_payloads_match = True
    for row in rows:
        payload = json.loads((RUN / "cases" / f"{row['case_id']}.json").read_text(encoding="utf-8"))
        severities = {finding["severity"] for finding in payload["findings"]}
        if payload["overall_status"] != row["status"]:
            case_payloads_match = False
        if (payload["overall_status"] == "ROBUST_PASS") != accepted(row):
            case_payloads_match = False
        if bool(severities & {"HIGH_IMPACT", "BLOCKER"}) != high(row):
            case_payloads_match = False

    checks = {
        "source_file_hashes_match_identity": source_hashes == identity["source_hashes"],
        "source_tree_hash_matches_identity": aggregate(source_hashes) == identity["source_tree_sha256"],
        "candidate_patch_hash_matches_identity": sha(ATTEMPT / "candidate.patch") == identity["candidate_patch_sha256"],
        "protocol_hash_matches_identity": sha(ATTEMPT / "PROTOCOL.md") == identity["protocol_sha256"],
        "runner_hash_matches_identity": sha(ROOT / "run_guard_v2.py") == identity["runner_sha256"],
        "all_frozen_input_hashes_match_manifest": input_hashes == manifest["files"],
        "input_aggregate_matches_manifest": aggregate(input_hashes) == manifest["aggregate_sha256"],
        "case_row_count_is_54": len(rows) == 54,
        "case_output_count_is_54": len(case_files) == 54,
        "case_payloads_match_outcome_rows": case_payloads_match,
        "valid_retained_is_12_of_12": len(valid) == 12 and sum(map(accepted, valid)) == 12,
        "invalid_accepted_is_0_of_42": len(invalid) == 42 and sum(map(accepted, invalid)) == 0,
        "invalid_high_or_blocker_is_42_of_42": len(invalid) == 42 and sum(map(high, invalid)) == 42,
        "summary_counts_match_recomputation": (
            summary["n_cases"] == len(rows)
            and summary["valid_total"] == len(valid)
            and summary["valid_retained"] == sum(map(accepted, valid))
            and summary["invalid_total"] == len(invalid)
            and summary["invalid_accepted"] == sum(map(accepted, invalid))
            and summary["invalid_high_or_blocker"] == sum(map(high, invalid))
        ),
        "execution_end_binds_summary": end["summary_sha256"] == sha(RUN / "summary.json"),
        "summary_and_execution_end_report_pass": summary["status"] == "PASS" and end["status"] == "PASS",
        "evidence_ceiling_is_bounded": (
            summary["evidence_ceiling"] == "LOCAL_DEVELOPER_LABELLED_REGRESSION_ONLY"
            and summary["scientific_authorization"] == "NONE"
            and identity["scientific_authorization"] == "NONE"
        ),
    }
    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "recomputed": {
            "valid_retained": sum(map(accepted, valid)),
            "valid_total": len(valid),
            "invalid_accepted": sum(map(accepted, invalid)),
            "invalid_total": len(invalid),
            "invalid_high_or_blocker": sum(map(high, invalid)),
        },
    }
    output = ATTEMPT / "VERIFICATION-ATTEMPT-02.json"
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite {output}")
    output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
