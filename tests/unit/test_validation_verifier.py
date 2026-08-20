"""Unit tests for unified validation artifact verifier (BNS-010, BNS-015).

Tests:
1. Positive: verify_validation_artifacts passes on current repository.
2. Negative 1 (Missing): missing REPORT.json, INFERENTIAL_STRESS_REPORT.json, or CERTIFICATION.json.
3. Negative 2 (Tampered): altered file content or tampered checksum.
4. Negative 3 (Stale): outdated pipeline.version or project_version.
5. Negative 4 (Fake Real Label): synthetic report claiming real accession or fake flagship files.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from bionexus.validation_verifier import verify_validation_artifacts


@pytest.fixture
def mock_repo_env(tmp_path: Path) -> Path:
    """Create a minimal mock repository environment for negative testing."""
    mock_root = tmp_path / "repo"
    mock_root.mkdir(parents=True, exist_ok=True)

    val_src = _REPO_ROOT / "validation"
    val_dst = mock_root / "validation"
    shutil.copytree(val_src, val_dst, ignore=shutil.ignore_patterns("*.h5ad", "__pycache__"))

    data_src = _REPO_ROOT / "data" / "flagship"
    data_dst = mock_root / "data" / "flagship"
    shutil.copytree(data_src, data_dst, ignore=shutil.ignore_patterns("*.h5ad", "__pycache__"))

    # Also copy real h5ad if present for pseudobulk checksum tests
    real_h5ad = _REPO_ROOT / "data" / "flagship" / "kang2018_pbmc_ifnb" / "pbmc_ifnb_counts.h5ad"
    if real_h5ad.is_file():
        shutil.copy2(real_h5ad, data_dst / "kang2018_pbmc_ifnb" / "pbmc_ifnb_counts.h5ad")

    yield mock_root

    # Clean up mock environment
    shutil.rmtree(mock_root, ignore_errors=True)


class TestValidationVerifierPositive:
    """Positive verification tests."""

    def test_verify_validation_artifacts_passes_on_current_repo(self):
        """Current repository validation artifacts must be 100% compliant."""
        res = verify_validation_artifacts(repo_root=_REPO_ROOT)
        assert res.passed is True, f"Verification failed with errors: {res.errors}"
        assert len(res.errors) == 0
        assert len(res.checked_files) >= 9


class TestValidationVerifierNegatives:
    """Four classes of negative tests: Missing, Tampered, Stale, Fake Real Label."""

    def test_negative_missing_artifact(self, mock_repo_env: Path):
        """Missing required artifact must cause verification failure."""
        target = mock_repo_env / "validation" / "pseudobulk" / "REPORT.json"
        assert target.is_file()
        target.unlink()

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("Missing required artifact" in e and "pseudobulk" in e for e in res.errors)

    def test_negative_missing_certification(self, mock_repo_env: Path):
        """Missing CERTIFICATION.json must cause verification failure."""
        target = mock_repo_env / "validation" / "annotation" / "CERTIFICATION.json"
        assert target.is_file()
        target.unlink()

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("Missing required artifact" in e and "annotation" in e for e in res.errors)

    def test_negative_tampered_checksum(self, mock_repo_env: Path):
        """Tampered data file or hash mismatch must cause verification failure."""
        truth_file = mock_repo_env / "data" / "flagship" / "kang2018_pbmc_ifnb" / "published_de_truth.csv"
        assert truth_file.is_file()
        truth_file.write_text("tampered content,gene,padj\nTAMPERED,0.001\n", encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("Checksum mismatch" in e for e in res.errors)

    def test_negative_stale_version(self, mock_repo_env: Path):
        """Stale pipeline or project version must cause verification failure."""
        report_path = mock_repo_env / "validation" / "spatial" / "REPORT.json"
        data = json.loads(report_path.read_text(encoding="utf-8"))
        data["pipeline"]["version"] = "0.0.1-stale"
        report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("pipeline.version '0.0.1-stale' != expected" in e for e in res.errors)

    def test_negative_stale_certification_version(self, mock_repo_env: Path):
        """Stale certification project_version must cause verification failure."""
        cert_path = mock_repo_env / "validation" / "pseudobulk" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        data["project_version"] = "0.0.1-stale"
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("CERTIFICATION.json project_version '0.0.1-stale' != expected" in e for e in res.errors)

    def test_negative_fake_flagship_file_in_data_dir(self, mock_repo_env: Path):
        """Synthetic pretender file in data/flagship must be rejected."""
        fake_file = mock_repo_env / "data" / "flagship" / "citeseq_pbmc_sorted" / "citeseq_pbmc.h5ad"
        fake_file.parent.mkdir(parents=True, exist_ok=True)
        fake_file.write_text("pretend synthetic content", encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("Synthetic file" in e and "masquerading" in e for e in res.errors)

    def test_negative_fake_public_reference_claim_in_synthetic_track(self, mock_repo_env: Path):
        """Synthetic report falsely claiming real reference dataset must be rejected."""
        cert_path = mock_repo_env / "validation" / "annotation" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        for std in data["standards"]:
            if std["standard_id"] == "public_reference_dataset":
                std["satisfied"] = True
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("falsely claims public_reference_dataset=true" in e or "satisfied mismatch" in e for e in res.errors)

