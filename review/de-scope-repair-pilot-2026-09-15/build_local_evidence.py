"""Freeze and run the 54-case local DE remediation evidence package.

This is a post-outcome developer regression. It deliberately refuses to
overwrite an existing artifacts directory.
"""
from __future__ import annotations

import csv
import hashlib
import importlib
import json
import platform
import shutil
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CASES = REPO / "review/methods-experiments-2026-09-08/run-01/challenge/cases"
RC8 = REPO / "review/rc8-challenge-rerun-2026-09-14/run-01/cases"
ARTIFACTS = HERE / "attempt-02"
SNAPSHOT = ARTIFACTS / "candidate-source"
RUN = ARTIFACTS / "run-01"
EXPECTED = {
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
    "missing_receipt": "analysis_execution_binding=MISSING_EVIDENCE",
    "wrong_design": "BFA-013c",
    "wrong_direction": "BFA-015d",
    "wrong_result_hash": "BFA-013a",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    return sha(path.read_bytes())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _json_default(value: object) -> object:
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def copy_source() -> dict:
    hashes = {}
    for source in sorted(p for p in (REPO / "src/bionexus").rglob("*") if p.is_file()):
        if "__pycache__" in source.parts or source.suffix in {".pyc", ".pyo"}:
            continue
        relative = source.relative_to(REPO / "src")
        target = SNAPSHOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        hashes[relative.as_posix()] = sha_file(target)
    return hashes


def load_auditor():
    sys.path.insert(0, str(SNAPSHOT))
    for name in [n for n in sys.modules if n == "bionexus" or n.startswith("bionexus.")]:
        del sys.modules[name]
    module = importlib.import_module("bionexus.de_audit")
    expected = (SNAPSHOT / "bionexus/de_audit.py").resolve()
    if Path(module.__file__).resolve() != expected:
        raise RuntimeError(f"wrong source imported: {module.__file__}")
    return module.audit_differential_expression


def binding(payload: dict) -> dict:
    return next(check for check in payload["checks"] if check["check_id"] == "analysis_execution_binding")


def expected_hit(family: str, payload: dict) -> bool:
    expected = EXPECTED.get(family)
    if expected is None:
        return payload["passed"] and not any(
            finding["severity"] in {"HIGH_IMPACT", "BLOCKER"} for finding in payload["findings"]
        )
    if expected.startswith("analysis_execution_binding"):
        return binding(payload)["status"] == expected.split("=", 1)[1]
    return any(
        finding["rule_id"] == expected and finding["severity"] in {"HIGH_IMPACT", "BLOCKER"}
        for finding in payload["findings"]
    )


def cause_for(family: str, invalid: bool) -> tuple[str, str]:
    if not invalid:
        extra = " The reporting-prefix parser also preserves the scoped limitation." if family == "valid_limited" else ""
        return (
            "rc.8 treated fit_status=COMPLETE as unconfirmed and could not use the receipt's hash-bound original metadata when donor_ids was absent."
            + extra,
            "Accept the documented COMPLETE synonym; derive donor identity only from an original metadata file whose SHA-256 exactly matches the receipt.",
        )
    labels = {
        "absent_gene": "Claim names a gene absent from the supplied DE table.",
        "causal_overclaim": "Associational DE evidence is promoted to a causal claim.",
        "changed_result": "The supplied result bytes no longer match the receipt hash.",
        "clinical_overclaim": "DE evidence is promoted to a clinical efficacy claim.",
        "failed_fit": "The receipt records a failed model fit.",
        "false_global_null": "The claim says no genes are significant although the table contains significant genes.",
        "false_negative": "A gene-level nonsignificance claim conflicts with the table.",
        "false_significance": "A significance claim conflicts with the adjusted p value.",
        "invalid_probability": "The result contains invalid probability values and changed bytes.",
        "missing_fdr": "The result lacks an adjusted-p/FDR field and changed bytes.",
        "missing_receipt": "No execution receipt binds the statistical unit, design, fit, and result.",
        "wrong_design": "The claimed formula conflicts with design-matrix columns.",
        "wrong_direction": "The claimed effect direction conflicts with the result.",
        "wrong_result_hash": "The receipt result digest is malformed or all-zero.",
    }
    return labels[family], f"Fail closed through {EXPECTED[family]}."


def main() -> None:
    if ARTIFACTS.exists():
        raise FileExistsError(f"refusing to overwrite {ARTIFACTS}")
    ARTIFACTS.mkdir()
    source_hashes = copy_source()
    case_dirs = sorted(p for p in CASES.iterdir() if p.is_dir())
    if len(case_dirs) != 54:
        raise RuntimeError(f"expected 54 cases, found {len(case_dirs)}")
    input_hashes = {}
    for folder in case_dirs:
        for name in ("case.json", "receipt.json", "metadata.csv", "design.csv", "de.csv"):
            path = folder / name
            input_hashes[path.relative_to(REPO).as_posix()] = sha_file(path)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    identity = {
        "schema": "bionexus.de-local-remediation-identity.v1",
        "study_id": "BN-DE-LOCAL-REMEDIATION-20260915",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "workspace_head": head,
        "workspace_dirty": True,
        "source_file_count": len(source_hashes),
        "source_tree_sha256": sha("\n".join(f"{k} {source_hashes[k]}" for k in sorted(source_hashes)).encode()),
        "source_hashes": source_hashes,
        "input_file_count": len(input_hashes),
        "input_manifest_sha256": sha("\n".join(f"{k} {input_hashes[k]}" for k in sorted(input_hashes)).encode()),
        "input_hashes": input_hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "registration": "POST_OUTCOME_DEVELOPER_REGRESSION",
        "evidence_ceiling": "LOCAL_DEVELOPER_LABELLED_REGRESSION_ONLY",
        "scientific_authorization": "NONE",
    }
    write_json(ARTIFACTS / "IDENTITY.json", identity)
    auditor = load_auditor()
    (RUN / "cases").mkdir(parents=True)
    rows = []
    started = time.perf_counter()
    for folder in case_dirs:
        definition = json.loads((folder / "case.json").read_text(encoding="utf-8"))
        receipt = json.loads((folder / "receipt.json").read_text(encoding="utf-8"))
        result = auditor(
            de_table=folder / "de.csv",
            sample_metadata=folder / "metadata.csv",
            execution_record=receipt,
            claim_text=definition["claim"],
            donor_col="donor",
            condition_col="condition",
        )
        payload = result.to_dict()
        write_json(RUN / "cases" / f"{definition['case_id']}.json", payload)
        old = json.loads((RC8 / definition["case_id"] / "bionexus_full.json").read_text(encoding="utf-8"))
        root_cause, action = cause_for(definition["family"], definition["invalid"])
        new_binding, old_binding = binding(payload), binding(old)
        row = {
            "case_id": definition["case_id"],
            "family": definition["family"],
            "paraphrase": definition["paraphrase"],
            "developer_label": "INVALID" if definition["invalid"] else "VALID",
            "claim": definition["claim"],
            "rc8_status": old["overall_status"],
            "rc8_accepted": old["passed"],
            "rc8_binding_status": old_binding["status"],
            "rc8_rule_ids": ",".join(f["rule_id"] for f in old["findings"]),
            "candidate_status": payload["overall_status"],
            "candidate_accepted": payload["passed"],
            "candidate_binding_status": new_binding["status"],
            "candidate_rule_ids": ",".join(f["rule_id"] for f in payload["findings"]),
            "root_cause": root_cause,
            "compatibility_or_control_action": action,
            "expected_mechanism": EXPECTED.get(definition["family"], "valid_without_high_or_blocker"),
            "mechanism_match": expected_hit(definition["family"], payload),
            "case_definition_sha256": sha_file(folder / "case.json"),
            "receipt_sha256": sha_file(folder / "receipt.json"),
            "metadata_sha256": sha_file(folder / "metadata.csv"),
            "result_sha256": sha_file(folder / "de.csv"),
        }
        rows.append(row)
        print(definition["case_id"], payload["overall_status"], flush=True)
    with (ARTIFACTS / "CAUSE_ANALYSIS_54.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_json(ARTIFACTS / "CAUSE_ANALYSIS_54.json", rows)
    families = []
    for family in sorted({row["family"] for row in rows}):
        group = [row for row in rows if row["family"] == family]
        families.append({
            "family": family,
            "developer_label": group[0]["developer_label"],
            "related_paraphrases": len(group),
            "rc8_accepted": sum(bool(row["rc8_accepted"]) for row in group),
            "candidate_accepted": sum(bool(row["candidate_accepted"]) for row in group),
            "mechanism_matches": sum(bool(row["mechanism_match"]) for row in group),
            "root_cause": group[0]["root_cause"],
            "action": group[0]["compatibility_or_control_action"],
        })
    write_json(ARTIFACTS / "FAMILY_CAUSE_SUMMARY.json", families)
    valid = [row for row in rows if row["developer_label"] == "VALID"]
    invalid = [row for row in rows if row["developer_label"] == "INVALID"]
    summary = {
        "schema": "bionexus.de-local-remediation-summary.v1",
        "status": "PASS" if (
            len(valid) == 12 and sum(row["candidate_accepted"] for row in valid) == 12
            and len(invalid) == 42 and sum(row["candidate_accepted"] for row in invalid) == 0
            and all(row["mechanism_match"] for row in rows)
        ) else "FAIL",
        "study_id": identity["study_id"],
        "source_tree_sha256": identity["source_tree_sha256"],
        "input_manifest_sha256": identity["input_manifest_sha256"],
        "n_cases": len(rows),
        "independent_studies": 0,
        "case_families": len(families),
        "related_paraphrases_per_family": dict(Counter(str(row["family"]) for row in rows)),
        "valid_total": len(valid),
        "rc8_valid_retained": sum(row["rc8_accepted"] for row in valid),
        "candidate_valid_retained": sum(row["candidate_accepted"] for row in valid),
        "invalid_total": len(invalid),
        "rc8_invalid_accepted": sum(row["rc8_accepted"] for row in invalid),
        "candidate_invalid_accepted": sum(row["candidate_accepted"] for row in invalid),
        "mechanism_matches": sum(row["mechanism_match"] for row in rows),
        "elapsed_seconds": time.perf_counter() - started,
        "evidence_ceiling": identity["evidence_ceiling"],
        "scientific_authorization": "NONE",
    }
    write_json(ARTIFACTS / "SUMMARY.json", summary)
    if summary["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
