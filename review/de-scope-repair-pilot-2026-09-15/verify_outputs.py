"""Recompute hashes and gates for the local run and external launch bundle."""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path

from bionexus.de_external_study import digest, validate_plan

HERE = Path(__file__).resolve().parent
ATTEMPT = HERE / "attempt-02"
PILOT = HERE / "external-pilot/attempt-03"
OUTPUT = ATTEMPT / "VERIFICATION-ATTEMPT-02.json"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"refusing to overwrite {OUTPUT}")
    identity = json.loads((ATTEMPT / "IDENTITY.json").read_text(encoding="utf-8"))
    summary = json.loads((ATTEMPT / "SUMMARY.json").read_text(encoding="utf-8"))
    controls = json.loads((ATTEMPT / "CONTROL_RESULTS.json").read_text(encoding="utf-8"))
    with (ATTEMPT / "CAUSE_ANALYSIS_54.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    source_hashes = {
        path.relative_to(ATTEMPT / "candidate-source").as_posix(): sha_file(path)
        for path in sorted((ATTEMPT / "candidate-source").rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts and path.suffix not in {".pyc", ".pyo"}
    }
    source_tree = hashlib.sha256(
        "\n".join(f"{k} {source_hashes[k]}" for k in sorted(source_hashes)).encode()
    ).hexdigest()
    plan = json.loads((PILOT / "PLAN_TEMPLATE.json").read_text(encoding="utf-8"))
    validate_plan(plan)
    status = json.loads((PILOT / "PILOT_STATUS.json").read_text(encoding="utf-8"))
    manifest = json.loads((PILOT / "SHA256SUMS.json").read_text(encoding="utf-8"))
    checks = {
        "source_tree_hash_matches": source_tree == identity["source_tree_sha256"] == summary["source_tree_sha256"],
        "fifty_four_rows": len(rows) == 54,
        "fifty_four_case_payloads": len(list((ATTEMPT / "run-01/cases").glob("*.json"))) == 54,
        "local_gate_pass": summary["status"] == "PASS",
        "valid_retention": summary["candidate_valid_retained"] == 12,
        "invalid_acceptance": summary["candidate_invalid_accepted"] == 0,
        "mechanism_mapping": summary["mechanism_matches"] == 54,
        "control_gate_pass": controls["status"] == "PASS" and len(controls["controls"]) == 10,
        "external_plan_valid_zero_case_template": len(plan["cases"]) == 0,
        "development_overlap_hashes_are_individual": len(plan["development_dataset_sha256"]) >= 1
            and summary["input_manifest_sha256"] not in plan["development_dataset_sha256"],
        "external_plan_hash_matches": digest(plan) == status["plan_template_sha256"],
        "external_status_honest_zero": status["pilot_executed"] is False
            and status["actual_external_tasks"] == status["actual_external_sites"] == 0,
        "external_validation_not_established": status["external_validation"] == "NOT_ESTABLISHED",
        "external_manifest_matches": all(sha_file(PILOT / name) == value for name, value in manifest["files"].items()),
    }
    with zipfile.ZipFile(PILOT / "external-pilot-launch.zip") as archive:
        checks["external_zip_members_match"] = set(archive.namelist()) == {
            *manifest["files"], "SHA256SUMS.json", "PROVENANCE.json"
        }
    payload = {
        "schema": "bionexus.de-remediation-verification.v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "scientific_authorization": "NONE",
        "external_validation": "NOT_ESTABLISHED",
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
