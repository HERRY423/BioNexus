"""Validate or execute the bounded DE requirement profile; no certification.

Default: resolve declarations only. --run: execute exact mapped tests and emit
local receipts bound to this source snapshot. An old receipt cannot be supplied
to upgrade a new checkout. Missing, skipped or failed tests are never passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import yaml

from bionexus.contract_traceability import (
    EvidenceKind,
    ExecutionReceipt,
    audit_traceability,
    load_manifest,
)


class TestOutcomes:
    def __init__(self) -> None:
        self.phases: dict[str, dict[str, str]] = {}

    def pytest_runtest_logreport(self, report: Any) -> None:
        self.phases.setdefault(report.nodeid, {})[report.when] = report.outcome

    def passed(self, target: str) -> bool:
        matching = [phases for node, phases in self.phases.items()
                    if node.replace("\\", "/").split("[", 1)[0] == target]
        return bool(matching) and all(
            all(phases.get(phase) == "passed" for phase in ("setup", "call", "teardown"))
            for phases in matching
        )


def source_hashes(root: Path, manifest_path: Path, targets: list[str]) -> dict[str, str]:
    paths = {*root.glob("src/bionexus/**/*.py"), *root.glob("spec/BNS-*.md"), manifest_path,
             root / "scripts/check_de_traceability.py", root / "tests/conftest.py"}
    paths.update(root / target.split("::", 1)[0] for target in targets)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def validate_profile(root: Path, manifest_path: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = load_manifest(manifest_path)
    report = audit_traceability(repo_root=root, spec_dir=root / "spec", manifest=manifest)
    errors = [f"Unknown requirement: {rid}" for rid in report.unknown_manifest_ids]
    errors += [f"Duplicate requirement: {rid}" for rid in report.duplicate_requirement_ids]
    targets: set[str] = set()
    for trace in report.traces:
        rid = trace.requirement.requirement_id
        if rid not in manifest:
            continue
        for item in trace.evidence:
            if not item.reference_valid:
                errors.append(f"{rid}: {item.reason}: {item.declaration.target}")
        entry = raw["requirements"][rid]
        if any(e.kind == EvidenceKind.GAP for e in manifest[rid]):
            if not entry.get("limitation"):
                errors.append(f"{rid}: acknowledged gap needs a limitation")
            continue
        impl = [e for e in manifest[rid] if e.kind == EvidenceKind.IMPLEMENTATION]
        declared_tests = {e.target for e in manifest[rid] if e.kind == EvidenceKind.TEST}
        if not impl:
            errors.append(f"{rid}: missing implementation reference")
        for role in ("positive_tests", "negative_tests"):
            cases = entry.get(role, [])
            if not cases or not set(cases) <= declared_tests:
                errors.append(f"{rid}: {role} must resolve to declared tests")
        targets.update(declared_tests)
    if not targets:
        errors.append("Profile contains no executable tests")
    return raw, sorted(targets), errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    args = parser.parse_args(argv)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    path = ROOT / "spec/de-audit-traceability.yaml"
    raw, targets, errors = validate_profile(ROOT, path)
    before = source_hashes(ROOT, path, targets)
    receipts: list[ExecutionReceipt] = []
    outcomes = TestOutcomes()
    exit_code: int | None = None
    command = [*targets, "-q", "-p", "no:cacheprovider", "--basetemp", str(output / "tmp"),
               f"--junitxml={output / 'tests.xml'}"]
    if args.run and not errors:
        os.environ.setdefault("NUMBA_CACHE_DIR", str(ROOT / ".numba-cache"))
        os.chdir(ROOT)
        import pytest

        exit_code = int(pytest.main(command, plugins=[outcomes]))
        after = source_hashes(ROOT, path, targets)
        if before != after:
            errors.append("Source or tests changed during execution; receipt withheld")
        elif exit_code == 0:
            passed = tuple(t for t in targets if outcomes.passed(t))
            if set(passed) != set(targets):
                errors.append("Mapped tests were missing, skipped, or incomplete")
            receipts.append(ExecutionReceipt(
                receipt_id="local-de-requirement-test-run", evidence_kind=EvidenceKind.TEST,
                command="python scripts/check_de_traceability.py --run", passed_targets=passed,
                artifact_sha256=before,
            ))
        else:
            errors.append(f"Mapped tests failed with pytest exit code {exit_code}")
    report = audit_traceability(repo_root=ROOT, spec_dir=ROOT / "spec",
                               manifest=load_manifest(path), receipts=receipts).to_dict()
    selected = [t for t in report["traces"] if t["requirement"]["requirement_id"] in raw["requirements"]]
    for trace in selected:
        declaration = raw["requirements"][trace["requirement"]["requirement_id"]]
        trace["profile_scope_note"] = declaration.get("scope_note")
        trace["acknowledged_limitation"] = declaration.get("limitation")
        trace["positive_tests"] = declaration.get("positive_tests", [])
        trace["negative_tests"] = declaration.get("negative_tests", [])
    payload = {"scope": raw["scope"], "scientific_authorization": "NONE",
               "receipt_trust": "LOCAL_SELF_RECORDED_NOT_INDEPENDENT_ATTESTATION",
               "test_execution": "NOT_RUN" if exit_code is None else "PASSED" if not errors else "FAILED_OR_INCOMPLETE",
               "pytest_exit_code": exit_code, "errors": errors, "source_sha256": before,
               "pytest_arguments": command, "test_outcomes": outcomes.phases,
               "requirements": selected,
               "outside_profile_requirements": report["summary"]["requirements"] - len(selected)}
    (output / "report.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (output / "receipts.json").write_text(json.dumps({"receipts": [
        {"receipt_id": r.receipt_id, "evidence_kind": r.evidence_kind.value, "command": r.command,
         "passed_targets": r.passed_targets, "artifact_sha256": dict(r.artifact_sha256), "outcome": r.outcome}
        for r in receipts]}, indent=2), encoding="utf-8")
    print(json.dumps({"test_execution": payload["test_execution"], "errors": errors,
                      "requirements": len(selected), "scientific_authorization": "NONE"}))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
