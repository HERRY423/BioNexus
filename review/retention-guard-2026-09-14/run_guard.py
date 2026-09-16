"""Run the frozen 54-case retention/safety guard against an exact source snapshot."""
from __future__ import annotations

import csv
import hashlib
import importlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
CASES = REPO / "review" / "methods-experiments-2026-09-08" / "run-01" / "challenge" / "cases"
SNAPSHOT = HERE / "candidate-source"
OUT = HERE / "run-01"
EXPECTED_CASES = 54
EXPECTED_VALID = 12
EXPECTED_INVALID = 42


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_path(path: Path) -> str:
    return digest_bytes(path.read_bytes())


def write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False, default=str) + "\n",
        encoding="utf-8",
    )


def snapshot_candidate() -> dict:
    if SNAPSHOT.exists():
        raise FileExistsError(f"Refusing to overwrite {SNAPSHOT}")
    source = REPO / "src" / "bionexus"
    hashes = {}
    for path in sorted(source.rglob("*.py")):
        rel = path.relative_to(REPO / "src")
        dest = SNAPSHOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        hashes[rel.as_posix()] = digest_path(dest)
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    diff = subprocess.check_output(
        ["git", "diff", "--binary", "--", "src/bionexus/de_audit.py", "src/bionexus/claim_semantics.py",
         "tests/unit/test_rc6_p0_boundaries.py", "docs/rc6-p0-closure.md"],
        cwd=REPO,
    )
    (HERE / "candidate.patch").write_bytes(diff)
    return {
        "study_id": "BN-DE-RETENTION-GUARD-20260914",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "workspace_head": head,
        "registration": "POST_OUTCOME_ENGINEERING_REGRESSION_NOT_INDEPENDENT_STUDY",
        "source_file_count": len(hashes),
        "source_tree_sha256": digest_bytes(
            "\n".join(f"{name} {hashes[name]}" for name in sorted(hashes)).encode("utf-8")
        ),
        "candidate_patch_sha256": digest_bytes(diff),
        "source_hashes": hashes,
        "protocol_sha256": digest_path(HERE / "PROTOCOL.md"),
        "runner_sha256": digest_path(Path(__file__)),
        "python": sys.version,
        "platform": platform.platform(),
        "scientific_authorization": "NONE",
    }


def input_manifest(case_dirs: list[Path]) -> dict:
    files = {}
    for case_dir in case_dirs:
        for name in ("case.json", "receipt.json", "metadata.csv", "design.csv", "de.csv"):
            path = case_dir / name
            if not path.is_file():
                raise FileNotFoundError(path)
            files[path.relative_to(REPO).as_posix()] = digest_path(path)
    aggregate = digest_bytes(
        "\n".join(f"{name} {files[name]}" for name in sorted(files)).encode("utf-8")
    )
    return {"file_count": len(files), "aggregate_sha256": aggregate, "files": files}


def load_candidate():
    snapshot_path = str(SNAPSHOT)
    sys.path.insert(0, snapshot_path)
    for name in [key for key in sys.modules if key == "bionexus" or key.startswith("bionexus.")]:
        del sys.modules[name]
    module = importlib.import_module("bionexus.de_audit")
    expected = (SNAPSHOT / "bionexus" / "de_audit.py").resolve()
    if Path(module.__file__).resolve() != expected:
        raise RuntimeError(f"Imported {module.__file__}, expected {expected}")
    return module.audit_differential_expression


def severity_value(finding) -> str:
    severity = getattr(finding, "severity", None)
    return str(getattr(severity, "value", severity))


def main() -> None:
    if OUT.exists():
        raise FileExistsError(f"Refusing to overwrite {OUT}")
    case_dirs = sorted(path for path in CASES.iterdir() if path.is_dir())
    if len(case_dirs) != EXPECTED_CASES:
        raise RuntimeError(f"Expected {EXPECTED_CASES} cases, found {len(case_dirs)}")

    identity = snapshot_candidate()
    manifest = input_manifest(case_dirs)
    write_json(HERE / "IDENTITY.json", identity)
    write_json(HERE / "INPUT_MANIFEST.json", manifest)
    audit = load_candidate()
    OUT.mkdir(parents=True, exist_ok=False)
    case_out = OUT / "cases"
    case_out.mkdir()
    rows = []
    started = time.perf_counter()

    for index, case_dir in enumerate(case_dirs, start=1):
        definition = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
        receipt = json.loads((case_dir / "receipt.json").read_text(encoding="utf-8"))
        result = audit(
            de_table=case_dir / "de.csv",
            sample_metadata=case_dir / "metadata.csv",
            execution_record=receipt,
            claim_text=definition["claim"],
            donor_col="donor",
            condition_col="condition",
        )
        payload = result.to_dict()
        write_json(case_out / f"{definition['case_id']}.json", payload)
        severities = [severity_value(finding) for finding in result.findings]
        rule_ids = [finding.rule_id for finding in result.findings]
        binding = next((check for check in result.checks if check.check_id == "analysis_execution_binding"), None)
        rows.append({
            "case_id": definition["case_id"],
            "family": definition["family"],
            "invalid": bool(definition["invalid"]),
            "status": result.overall_status,
            "accepted": bool(result.passed),
            "high_or_blocker": any(value in {"HIGH_IMPACT", "BLOCKER"} for value in severities),
            "finding_rule_ids": ",".join(rule_ids),
            "finding_severities": ",".join(severities),
            "binding_status": str(getattr(getattr(binding, "status", None), "value", "")),
            "binding_summary": str(getattr(binding, "summary", "")),
        })
        print(f"{index}/{EXPECTED_CASES} {definition['case_id']} {result.overall_status}", flush=True)

    with (OUT / "case-outcomes.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    valid = [row for row in rows if not row["invalid"]]
    invalid = [row for row in rows if row["invalid"]]
    family_rows = []
    for family in sorted({row["family"] for row in rows}):
        group = [row for row in rows if row["family"] == family]
        family_rows.append({
            "family": family,
            "invalid": group[0]["invalid"],
            "n": len(group),
            "accepted": sum(row["accepted"] for row in group),
            "high_or_blocker": sum(row["high_or_blocker"] for row in group),
            "statuses": sorted({row["status"] for row in group}),
            "rule_ids": sorted({rid for row in group for rid in row["finding_rule_ids"].split(",") if rid}),
        })
    summary = {
        "status": "PASS" if (
            len(valid) == EXPECTED_VALID
            and len(invalid) == EXPECTED_INVALID
            and sum(row["accepted"] for row in valid) == EXPECTED_VALID
            and sum(row["accepted"] for row in invalid) == 0
            and sum(row["high_or_blocker"] for row in invalid) == EXPECTED_INVALID
        ) else "FAIL",
        "study_id": identity["study_id"],
        "candidate_source_tree_sha256": identity["source_tree_sha256"],
        "input_manifest_sha256": manifest["aggregate_sha256"],
        "n_cases": len(rows),
        "valid_total": len(valid),
        "valid_retained": sum(row["accepted"] for row in valid),
        "invalid_total": len(invalid),
        "invalid_accepted": sum(row["accepted"] for row in invalid),
        "invalid_high_or_blocker": sum(row["high_or_blocker"] for row in invalid),
        "predefined_gate": {
            "valid_retained_required": EXPECTED_VALID,
            "invalid_accepted_max": 0,
            "invalid_high_or_blocker_required": EXPECTED_INVALID,
        },
        "families": family_rows,
        "elapsed_seconds": time.perf_counter() - started,
        "evidence_ceiling": "LOCAL_DEVELOPER_LABELLED_REGRESSION_ONLY",
        "scientific_authorization": "NONE",
    }
    write_json(OUT / "summary.json", summary)
    write_json(OUT / "execution-end.json", {
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "status": summary["status"],
        "summary_sha256": digest_path(OUT / "summary.json"),
    })
    if summary["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
