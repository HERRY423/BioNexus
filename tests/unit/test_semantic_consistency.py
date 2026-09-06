"""Unit tests for semantic consistency between reports, comparisons, and certifications."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

from bionexus.semantic_consistency import (
    verify_cross_host_consistency,
    verify_semantic_consistency,
    verify_study_endpoints_consistency,
)


@pytest.fixture
def mock_semantic_repo(tmp_path: Path) -> Path:
    """Create a minimal mock repository for semantic consistency tests."""
    mock_root = tmp_path / "bionexus"
    mock_root.mkdir(parents=True, exist_ok=True)

    # Copy cross-host directory
    shutil.copytree(_REPO_ROOT / "cross-host", mock_root / "cross-host")

    # Copy validation directory (excluding large data / cache)
    shutil.copytree(
        _REPO_ROOT / "validation",
        mock_root / "validation",
        ignore=shutil.ignore_patterns("*.h5ad", "*.zip", "*.gz", "__pycache__"),
    )

    yield mock_root
    shutil.rmtree(mock_root, ignore_errors=True)


class TestSemanticConsistencyPositive:
    """Current repository should pass all semantic consistency checks."""

    def test_current_repository_is_semantically_consistent(self):
        errors = verify_semantic_consistency(_REPO_ROOT)
        assert len(errors) == 0, f"Unexpected semantic errors: {errors}"


class TestSemanticConsistencyNegatives:
    """Negative tests: discrepancies must be caught deterministically."""

    def test_stale_zero_traps_claim_is_rejected(self, mock_semantic_repo: Path):
        """If COMPARISON.json has 6 traps, claiming '0 traps compared' must fail."""
        cert_path = mock_semantic_repo / "validation" / "pseudobulk" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        for s in data["standards"]:
            if s["standard_id"] == "cross_host_test":
                s["evidence"] = "cross-host/COMPARISON.json (framework created, 0 traps compared)"
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        errors = verify_cross_host_consistency(mock_semantic_repo)
        assert len(errors) > 0
        assert any("0 traps compared" in e for e in errors)

    def test_trap_count_mismatch_is_rejected(self, mock_semantic_repo: Path):
        """Asserting wrong number of traps compared must fail."""
        cert_path = mock_semantic_repo / "validation" / "spatial" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        for s in data["standards"]:
            if s["standard_id"] == "cross_host_test":
                s["evidence"] = "cross-host/COMPARISON.json (hosts: claude-code + antigravity; 12 traps compared)"
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        errors = verify_cross_host_consistency(mock_semantic_repo)
        assert len(errors) > 0
        assert any("asserts 12 traps compared" in e for e in errors)

    def test_headless_trap_cannot_be_mechanically_promoted_to_satisfied(self, mock_semantic_repo: Path):
        """Setting cross_host_test=true based solely on headless traps must be rejected."""
        cert_path = mock_semantic_repo / "validation" / "annotation" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        for s in data["standards"]:
            if s["standard_id"] == "cross_host_test":
                s["satisfied"] = True
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        errors = verify_cross_host_consistency(mock_semantic_repo)
        assert len(errors) > 0
        assert any("falsely marked satisfied" in e and "headless trap comparison" in e for e in errors)

    def test_contradictory_endpoint_failure_claim_is_rejected(self, mock_semantic_repo: Path):
        """Claiming cell-size-bias failed when BN-SP-IV-001 recorded passed must fail."""
        cert_path = mock_semantic_repo / "validation" / "spatial" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        for s in data["standards"]:
            if s["standard_id"] == "independent_ground_truth":
                s["notes"] = "No independent pathology ground truth; one locked cell-size-bias endpoint failed"
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        errors = verify_study_endpoints_consistency(mock_semantic_repo)
        assert len(errors) > 0
        assert any("cell-size-bias endpoint failed" in e for e in errors)

    def test_fake_independent_ground_truth_rejected(self, mock_semantic_repo: Path):
        """Claiming independent_ground_truth=true on technical acceptance alone must fail."""
        cert_path = mock_semantic_repo / "validation" / "spatial" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        for s in data["standards"]:
            if s["standard_id"] == "independent_ground_truth":
                s["satisfied"] = True
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        errors = verify_study_endpoints_consistency(mock_semantic_repo)
        assert len(errors) > 0
        assert any("falsely claims independent_ground_truth=true" in e for e in errors)
