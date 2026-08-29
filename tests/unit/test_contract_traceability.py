import hashlib
import json
from pathlib import Path

from bionexus.contract_traceability import (
    EvidenceDeclaration,
    EvidenceKind,
    EvidenceState,
    ExecutionReceipt,
    audit_traceability,
    discover_requirements,
)


def _write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    spec = tmp_path / "spec"
    tests = tmp_path / "tests"
    source = tmp_path / "src"
    spec.mkdir()
    tests.mkdir()
    source.mkdir()
    (spec / "BNS-099-fixture.md").write_text(
        "# Fixture\n\n"
        "- **BNS-RC-004** The implementation MUST retain the base rule.\n"
        "- **BNS-RC-004A** The implementation MUST retain the suffixed rule.\n"
        "- **BNS-RC-005** The behavior SHOULD be tested.\n"
        "- **BNS-RC-006** The gap MUST be recorded.\n",
        encoding="utf-8",
    )
    (source / "feature.py").write_text("def feature():\n    return True\n", encoding="utf-8")
    (tests / "test_feature.py").write_text("def test_feature():\n    assert True\n", encoding="utf-8")
    return spec, tests / "test_feature.py"


def test_discovery_preserves_base_and_suffixed_ids(tmp_path):
    spec, _ = _write_fixture(tmp_path)
    requirements, duplicates = discover_requirements(spec)
    assert [item.requirement_id for item in requirements] == [
        "BNS-RC-004",
        "BNS-RC-004A",
        "BNS-RC-005",
        "BNS-RC-006",
    ]
    assert duplicates == []


def test_declared_test_is_not_reported_as_executed_without_receipt(tmp_path):
    spec, _ = _write_fixture(tmp_path)
    report = audit_traceability(
        repo_root=tmp_path,
        spec_dir=spec,
        manifest={
            "BNS-RC-004": [EvidenceDeclaration(EvidenceKind.IMPLEMENTATION, "src/feature.py::feature")],
            "BNS-RC-005": [EvidenceDeclaration(EvidenceKind.TEST, "tests/test_feature.py::test_feature")],
        },
    )
    states = {trace.requirement.requirement_id: trace.state for trace in report.traces}
    assert states["BNS-RC-004"] == EvidenceState.IMPLEMENTATION_BOUND
    assert states["BNS-RC-005"] == EvidenceState.DECLARED_UNVERIFIED
    assert report.coverage()["executed_test_coverage"] == 0.0
    assert report.coverage()["implementation_reference_coverage"] == 0.25


def test_receipt_must_bind_exact_target_and_current_file_hash(tmp_path):
    spec, test_file = _write_fixture(tmp_path)
    target = "tests/test_feature.py::test_feature"
    declaration = EvidenceDeclaration(EvidenceKind.TEST, target)
    receipt = ExecutionReceipt(
        receipt_id="receipt-1",
        evidence_kind=EvidenceKind.TEST,
        command="pytest tests/test_feature.py::test_feature",
        passed_targets=(target,),
        artifact_sha256={"tests/test_feature.py": hashlib.sha256(test_file.read_bytes()).hexdigest()},
    )
    report = audit_traceability(
        repo_root=tmp_path,
        spec_dir=spec,
        manifest={"BNS-RC-005": [declaration]},
        receipts=[receipt],
    )
    trace = next(item for item in report.traces if item.requirement.requirement_id == "BNS-RC-005")
    assert trace.state == EvidenceState.TESTED
    assert report.coverage()["implementation_reference_coverage"] == 0.0

    test_file.write_text("def test_feature():\n    assert False\n", encoding="utf-8")
    stale = audit_traceability(
        repo_root=tmp_path,
        spec_dir=spec,
        manifest={"BNS-RC-005": [declaration]},
        receipts=[receipt],
    )
    stale_trace = next(item for item in stale.traces if item.requirement.requirement_id == "BNS-RC-005")
    assert stale_trace.state == EvidenceState.DECLARED_UNVERIFIED


def test_invalid_reference_and_gap_are_separate_states(tmp_path):
    spec, _ = _write_fixture(tmp_path)
    report = audit_traceability(
        repo_root=tmp_path,
        spec_dir=spec,
        manifest={
            "BNS-RC-004A": [EvidenceDeclaration(EvidenceKind.IMPLEMENTATION, "src/missing.py")],
            "BNS-RC-006": [EvidenceDeclaration(EvidenceKind.GAP, "not-yet-implemented", "planned")],
            "BNS-UNKNOWN-999": [],
        },
    )
    states = {trace.requirement.requirement_id: trace.state for trace in report.traces}
    assert states["BNS-RC-004A"] == EvidenceState.INVALID_REFERENCE
    assert states["BNS-RC-006"] == EvidenceState.ACKNOWLEDGED_GAP
    assert report.unknown_manifest_ids == ("BNS-UNKNOWN-999",)


def test_report_is_machine_serializable(tmp_path):
    spec, _ = _write_fixture(tmp_path)
    report = audit_traceability(repo_root=tmp_path, spec_dir=spec, manifest={})
    encoded = json.dumps(report.to_dict(), sort_keys=True)
    assert "documented_only" in encoded


def test_definition_without_rfc2119_word_is_visible_not_silently_dropped(tmp_path):
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "BNS-099-fixture.md").write_text(
        "- **BNS-X-001** Stable identifiers are never reused.\n",
        encoding="utf-8",
    )
    report = audit_traceability(repo_root=tmp_path, spec_dir=spec, manifest={})
    assert report.total_requirements == 1
    assert report.traces[0].requirement.normative_level == "UNSPECIFIED"
    assert report.coverage()["unspecified_normative_levels"] == 1
