"""
Tests for Cross-Host Execution Evidence Framework (BNS-HC-007).

Validates that:
- CrossHostExecutionRecord serialization works correctly
- generate_host_report produces complete JSON
- generate_comparison_report correctly compares two hosts
- validate_cross_host_schema detects missing fields
- Single-host runs do not evaluate consistency (matching compute_cross_host_consistency)
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from evals.cross_host_report import (
    CrossHostExecutionRecord,
    compute_input_hash,
    generate_comparison_report,
    generate_host_report,
    validate_cross_host_schema,
)


def _make_record(
    host_name: str = "codex",
    trap_id: str = "BF-001",
    expected_status: str = "ABSTAIN",
    observed_status: str = "ABSTAIN",
    refusal_correct: bool = True,
) -> CrossHostExecutionRecord:
    """Helper to create a test record."""
    return CrossHostExecutionRecord(
        host_name=host_name,
        host_version="1.0.0",
        capability_id="scrna.pseudobulk_de",
        input_hash="sha256:abc123",
        trap_id=trap_id,
        expected_status=expected_status,
        observed_status=observed_status,
        refusal_correct=refusal_correct,
        warrant_text="Test warrant text",
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata={"test": True},
    )


class TestCrossHostExecutionRecord:
    """Test CrossHostExecutionRecord dataclass."""

    def test_serialization_roundtrip(self):
        """Record should serialize to dict and deserialize back."""
        record = _make_record()
        data = record.to_dict()

        assert data["host_name"] == "codex"
        assert data["trap_id"] == "BF-001"
        assert data["refusal_correct"] is True

        restored = CrossHostExecutionRecord.from_dict(data)
        assert restored.host_name == record.host_name
        assert restored.trap_id == record.trap_id
        assert restored.refusal_correct == record.refusal_correct

    def test_to_dict_contains_all_fields(self):
        """to_dict should include all required fields."""
        record = _make_record()
        data = record.to_dict()

        required_fields = [
            "host_name",
            "host_version",
            "capability_id",
            "input_hash",
            "trap_id",
            "expected_status",
            "observed_status",
            "refusal_correct",
            "warrant_text",
            "timestamp",
            "metadata",
        ]
        for field_name in required_fields:
            assert field_name in data, f"Missing field: {field_name}"

    def test_from_dict_with_missing_metadata(self):
        """from_dict should default metadata to empty dict."""
        data = {
            "host_name": "codex",
            "host_version": "1.0.0",
            "capability_id": "scrna.pseudobulk_de",
            "input_hash": "sha256:abc123",
            "trap_id": "BF-001",
            "expected_status": "ABSTAIN",
            "observed_status": "ABSTAIN",
            "refusal_correct": True,
            "warrant_text": "Test",
            "timestamp": "2024-01-01T00:00:00Z",
        }
        record = CrossHostExecutionRecord.from_dict(data)
        assert record.metadata == {}


class TestComputeInputHash:
    """Test compute_input_hash function."""

    def test_hash_is_deterministic(self):
        """Same input should produce same hash."""
        hash1 = compute_input_hash("test prompt", {"key": "value"})
        hash2 = compute_input_hash("test prompt", {"key": "value"})
        assert hash1 == hash2

    def test_hash_differs_for_different_inputs(self):
        """Different inputs should produce different hashes."""
        hash1 = compute_input_hash("prompt A", {})
        hash2 = compute_input_hash("prompt B", {})
        assert hash1 != hash2

    def test_hash_format(self):
        """Hash should start with 'sha256:' prefix."""
        hash_val = compute_input_hash("test", {})
        assert hash_val.startswith("sha256:")
        assert len(hash_val) == 71  # "sha256:" + 64 hex chars


class TestGenerateHostReport:
    """Test generate_host_report function."""

    def test_empty_records(self):
        """Empty records should produce valid empty report."""
        report = generate_host_report([], host_name="codex")

        assert report["host"] == "codex"
        assert report["records"] == []
        assert report["summary"]["total_traps"] == 0
        assert report["summary"]["agreement_rate"] is None

    def test_report_with_records(self):
        """Report should include all records and correct summary."""
        records = [
            _make_record(trap_id="BF-001", refusal_correct=True),
            _make_record(trap_id="BF-002", refusal_correct=True),
            _make_record(trap_id="BF-003", refusal_correct=False),
        ]
        report = generate_host_report(records, host_name="codex", host_version="1.0.0")

        assert report["host"] == "codex"
        assert report["host_version"] == "1.0.0"
        assert len(report["records"]) == 3
        assert report["summary"]["total_traps"] == 3
        assert report["summary"]["correct_refusals"] == 2  # BF-001, BF-002
        assert report["summary"]["incorrect_refusals"] == 1  # BF-003
        assert report["summary"]["agreement_rate"] == pytest.approx(0.6667, rel=1e-3)

    def test_report_schema_valid(self):
        """Generated report should pass schema validation."""
        records = [_make_record()]
        report = generate_host_report(records, host_name="codex")
        errors = validate_cross_host_schema(report, report_type="host")
        assert errors == []

    def test_multiple_hosts_raises_error(self):
        """Records with multiple hosts should raise ValueError."""
        records = [
            _make_record(host_name="codex"),
            _make_record(host_name="claude-code"),
        ]
        with pytest.raises(ValueError, match="multiple hosts"):
            generate_host_report(records, host_name="codex")

    def test_false_positives_counted(self):
        """False positives (incorrect non-refusals) should be counted."""
        records = [
            _make_record(trap_id="BF-024", expected_status="PERMITTED", observed_status="ABSTAIN", refusal_correct=False),
        ]
        report = generate_host_report(records, host_name="codex")
        assert report["summary"]["false_positives"] == 1


class TestGenerateComparisonReport:
    """Test generate_comparison_report function."""

    def test_empty_reports(self):
        """Empty reports should produce valid empty comparison."""
        codex_report = generate_host_report([], host_name="codex")
        claude_report = generate_host_report([], host_name="claude-code")
        comparison = generate_comparison_report(codex_report, claude_report)

        assert comparison["traps_compared"] == 0
        assert comparison["per_trap"] == []
        assert comparison["overall"]["agreement_rate"] is None
        assert comparison["overall"]["conformance_verdict"] == "not_evaluated"

    def test_perfect_agreement(self):
        """Identical host behavior should yield 100% agreement."""
        records_codex = [
            _make_record(host_name="codex", trap_id="BF-001", observed_status="ABSTAIN"),
            _make_record(host_name="codex", trap_id="BF-002", observed_status="PERMITTED"),
        ]
        records_claude = [
            _make_record(host_name="claude-code", trap_id="BF-001", observed_status="ABSTAIN"),
            _make_record(host_name="claude-code", trap_id="BF-002", observed_status="PERMITTED"),
        ]
        codex_report = generate_host_report(records_codex, host_name="codex")
        claude_report = generate_host_report(records_claude, host_name="claude-code")
        comparison = generate_comparison_report(codex_report, claude_report)

        assert comparison["traps_compared"] == 2
        assert comparison["overall"]["consistent_traps"] == 2
        assert comparison["overall"]["inconsistent_traps"] == 0
        assert comparison["overall"]["agreement_rate"] == 1.0
        assert comparison["overall"]["conformance_verdict"] == "pass"

    def test_partial_agreement(self):
        """Partial agreement should be correctly computed."""
        records_codex = [
            _make_record(host_name="codex", trap_id="BF-001", observed_status="ABSTAIN"),
            _make_record(host_name="codex", trap_id="BF-002", observed_status="ABSTAIN"),
        ]
        records_claude = [
            _make_record(host_name="claude-code", trap_id="BF-001", observed_status="ABSTAIN"),
            _make_record(host_name="claude-code", trap_id="BF-002", observed_status="PERMITTED"),
        ]
        codex_report = generate_host_report(records_codex, host_name="codex")
        claude_report = generate_host_report(records_claude, host_name="claude-code")
        comparison = generate_comparison_report(codex_report, claude_report)

        assert comparison["traps_compared"] == 2
        assert comparison["overall"]["consistent_traps"] == 1
        assert comparison["overall"]["inconsistent_traps"] == 1
        assert comparison["overall"]["agreement_rate"] == 0.5
        assert comparison["overall"]["conformance_verdict"] == "fail"

    def test_comparison_schema_valid(self):
        """Generated comparison should pass schema validation."""
        records_codex = [_make_record(host_name="codex", trap_id="BF-001")]
        records_claude = [_make_record(host_name="claude-code", trap_id="BF-001")]
        codex_report = generate_host_report(records_codex, host_name="codex")
        claude_report = generate_host_report(records_claude, host_name="claude-code")
        comparison = generate_comparison_report(codex_report, claude_report)

        errors = validate_cross_host_schema(comparison, report_type="comparison")
        assert errors == []


class TestValidateCrossHostSchema:
    """Test validate_cross_host_schema function."""

    def test_valid_host_report(self):
        """Valid host report should have no errors."""
        report = {
            "host": "codex",
            "host_version": "1.0.0",
            "execution_date": "2024-01-01T00:00:00Z",
            "plugin_version": "0.10.0",
            "records": [
                {
                    "trap_id": "BF-001",
                    "capability_id": "scrna.pseudobulk_de",
                    "input_hash": "sha256:abc",
                    "expected_status": "ABSTAIN",
                    "observed_status": "ABSTAIN",
                    "refusal_correct": True,
                    "warrant_text": "Test",
                    "timestamp": "2024-01-01T00:00:00Z",
                }
            ],
            "summary": {
                "total_traps": 1,
                "correct_refusals": 1,
                "incorrect_refusals": 0,
                "false_positives": 0,
                "agreement_rate": 1.0,
            },
        }
        errors = validate_cross_host_schema(report, report_type="host")
        assert errors == []

    def test_missing_host_field(self):
        """Missing host field should be detected."""
        report = {
            "host_version": "1.0.0",
            "execution_date": "2024-01-01T00:00:00Z",
            "plugin_version": "0.10.0",
            "records": [],
            "summary": {
                "total_traps": 0,
                "correct_refusals": 0,
                "incorrect_refusals": 0,
                "false_positives": 0,
                "agreement_rate": None,
            },
        }
        errors = validate_cross_host_schema(report, report_type="host")
        assert any("host" in e for e in errors)

    def test_missing_record_field(self):
        """Missing record field should be detected."""
        report = {
            "host": "codex",
            "host_version": "1.0.0",
            "execution_date": "2024-01-01T00:00:00Z",
            "plugin_version": "0.10.0",
            "records": [{"trap_id": "BF-001"}],  # missing other fields
            "summary": {
                "total_traps": 1,
                "correct_refusals": 0,
                "incorrect_refusals": 0,
                "false_positives": 0,
                "agreement_rate": None,
            },
        }
        errors = validate_cross_host_schema(report, report_type="host")
        assert len(errors) > 0

    def test_missing_summary_field(self):
        """Missing summary field should be detected."""
        report = {
            "host": "codex",
            "host_version": "1.0.0",
            "execution_date": "2024-01-01T00:00:00Z",
            "plugin_version": "0.10.0",
            "records": [],
            "summary": {"total_traps": 0},  # missing other fields
        }
        errors = validate_cross_host_schema(report, report_type="host")
        assert len(errors) > 0

    def test_valid_comparison_report(self):
        """Valid comparison report should have no errors."""
        report = {
            "comparison_date": "2024-01-01T00:00:00Z",
            "hosts": ["codex", "claude-code"],
            "plugin_version": "0.10.0",
            "traps_compared": 1,
            "per_trap": [
                {
                    "trap_id": "BF-001",
                    "codex_status": "ABSTAIN",
                    "claude_code_status": "ABSTAIN",
                    "consistent": True,
                    "notes": "",
                }
            ],
            "overall": {
                "consistent_traps": 1,
                "inconsistent_traps": 0,
                "agreement_rate": 1.0,
                "conformance_verdict": "pass",
            },
        }
        errors = validate_cross_host_schema(report, report_type="comparison")
        assert errors == []

    def test_missing_comparison_field(self):
        """Missing comparison field should be detected."""
        report = {
            "hosts": ["codex", "claude-code"],
            "plugin_version": "0.10.0",
            "traps_compared": 0,
            "per_trap": [],
            "overall": {
                "consistent_traps": 0,
                "inconsistent_traps": 0,
                "agreement_rate": None,
                "conformance_verdict": "not_evaluated",
            },
        }
        errors = validate_cross_host_schema(report, report_type="comparison")
        assert any("comparison_date" in e for e in errors)

    def test_invalid_report_type(self):
        """Invalid report type should produce error."""
        errors = validate_cross_host_schema({}, report_type="invalid")
        assert any("Unknown report_type" in e for e in errors)


class TestSingleHostNoConsistency:
    """
    Test that single-host runs do not evaluate consistency.

    This matches the behavior of compute_cross_host_consistency in metrics.py,
    which returns evaluated=False for single-host runs.
    """

    def test_single_host_comparison_not_evaluated(self):
        """Comparing a host with itself (no second host) should not evaluate."""
        records = [_make_record(host_name="codex", trap_id="BF-001")]
        codex_report = generate_host_report(records, host_name="codex")
        empty_report = generate_host_report([], host_name="claude-code")

        comparison = generate_comparison_report(codex_report, empty_report)
        # No common traps means no comparison possible
        assert comparison["traps_compared"] == 0
        assert comparison["overall"]["agreement_rate"] is None
        assert comparison["overall"]["conformance_verdict"] == "not_evaluated"
