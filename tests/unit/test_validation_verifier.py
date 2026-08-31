"""Unit tests for unified validation artifact verifier (BNS-010, BNS-015).

Tests:
1. Positive: verify_validation_artifacts passes on current repository.
2. Negative Missing: missing h5ad, truth CSV, evidence_files, REPORT.json, STRESS_REPORT.json, CERTIFICATION.json.
3. Negative Tampered: altered data content, altered report checksums.
4. Negative Stale: outdated pipeline.version, project_version, commit_sha.
5. Negative Dirty: git_dirty=True rejected under fail-closed policy.
6. Negative Fake Real / Track Drift: synthetic claiming real track, synthetic claiming public reference or IGT.
7. Negative Certification Drift: certification_level, summary.verdict, summary.satisfied drift.
8. Negative Stress Test Failure: stress report dimension failure or missing dimensions.
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

from bionexus.validation_verifier import compute_validation_source_snapshot, verify_validation_artifacts


def test_validation_source_snapshot_excludes_report_self_reference(tmp_path: Path):
    """Editing a generated report must not change the scientific source identity."""
    (tmp_path / "src" / "bionexus").mkdir(parents=True)
    source = tmp_path / "src" / "bionexus" / "scientific.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    report = tmp_path / "validation" / "pseudobulk" / "REPORT.json"
    report.parent.mkdir(parents=True)
    report.write_text('{"run": 1}\n', encoding="utf-8")

    first = compute_validation_source_snapshot(tmp_path)
    report.write_text('{"run": 2}\n', encoding="utf-8")
    assert compute_validation_source_snapshot(tmp_path) == first

    source.write_text("VALUE = 2\n", encoding="utf-8")
    assert compute_validation_source_snapshot(tmp_path) != first


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
    shutil.copytree(
        data_src,
        data_dst,
        ignore=shutil.ignore_patterns("*.h5ad", "__pycache__", ".zenodo_parts"),
    )

    # Also copy data/pbmc3k_raw.h5ad if present
    pbmc3k_src = _REPO_ROOT / "data" / "pbmc3k_raw.h5ad"
    if pbmc3k_src.is_file():
        (mock_root / "data").mkdir(parents=True, exist_ok=True)
        shutil.copy2(pbmc3k_src, mock_root / "data" / "pbmc3k_raw.h5ad")

    # Also copy real h5ad if present for pseudobulk checksum tests
    real_h5ad = _REPO_ROOT / "data" / "flagship" / "kang2018_pbmc_ifnb" / "pbmc_ifnb_counts.h5ad"
    if real_h5ad.is_file():
        shutil.copy2(real_h5ad, data_dst / "kang2018_pbmc_ifnb" / "pbmc_ifnb_counts.h5ad")

    yield mock_root

    # Clean up mock environment
    shutil.rmtree(mock_root, ignore_errors=True)


class TestValidationVerifierPositive:
    """Positive verification tests."""

    @pytest.mark.flagship_data
    def test_verify_validation_artifacts_passes_on_current_repo(self):
        """Development artifacts must be internally valid even when provenance records a dirty tree.

        Release CI separately runs the verifier in strict mode after regenerating
        artifacts from a clean checkout.
        """
        res = verify_validation_artifacts(repo_root=_REPO_ROOT, allow_dirty=True)
        assert res.passed is True, f"Verification failed with errors: {res.errors}"
        assert len(res.errors) == 0
        assert len(res.checked_files) >= 9


class TestValidationVerifierNegatives:
    """Comprehensive negative tests: Missing, Tampered, Stale, Dirty, Fake Track, Certification Drift."""

    def test_negative_missing_real_h5ad(self, mock_repo_env: Path):
        """Missing pbmc_ifnb_counts.h5ad must cause verification failure."""
        target = mock_repo_env / "data" / "flagship" / "kang2018_pbmc_ifnb" / "pbmc_ifnb_counts.h5ad"
        if target.is_file():
            target.unlink()

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("declared real data file missing" in e and "pbmc_ifnb_counts.h5ad" in e for e in res.errors)

    def test_negative_missing_truth_csv(self, mock_repo_env: Path):
        """Missing published_de_truth.csv must cause verification failure."""
        target = mock_repo_env / "data" / "flagship" / "kang2018_pbmc_ifnb" / "published_de_truth.csv"
        assert target.is_file()
        target.unlink()

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("declared real data file missing" in e and "published_de_truth.csv" in e for e in res.errors)

    def test_negative_missing_evidence_file(self, mock_repo_env: Path):
        """Missing file referenced in evidence_files must cause verification failure."""
        target = mock_repo_env / "validation" / "pseudobulk" / "evidence" / "bionexus_pseudobulk_top100.csv"
        assert target.is_file()
        target.unlink()

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("evidence_files references missing file" in e for e in res.errors)

    def test_negative_tampered_preregistration(self, mock_repo_env: Path):
        """Post-lock edits to a preregistration must fail closed."""
        prereg = (
            mock_repo_env
            / "validation"
            / "annotation"
            / "studies"
            / "BN-ANN-IV-001"
            / "PREREGISTRATION.json"
        )
        prereg.write_text(prereg.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("Preregistration hash mismatch" in error for error in res.errors)

    def test_negative_missing_artifact(self, mock_repo_env: Path):
        """Missing required REPORT.json must cause verification failure."""
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

    def test_negative_missing_stress_report(self, mock_repo_env: Path):
        """Missing INFERENTIAL_STRESS_REPORT.json must cause verification failure."""
        target = mock_repo_env / "validation" / "spatial" / "INFERENTIAL_STRESS_REPORT.json"
        assert target.is_file()
        target.unlink()

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("INFERENTIAL_STRESS_REPORT.json" in e for e in res.errors)

    def test_negative_tampered_data_checksum(self, mock_repo_env: Path):
        """Tampered data file content must cause verification failure."""
        truth_file = mock_repo_env / "data" / "flagship" / "kang2018_pbmc_ifnb" / "published_de_truth.csv"
        assert truth_file.is_file()
        truth_file.write_text("tampered content,gene,padj\nTAMPERED,0.001\n", encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("Checksum mismatch" in e for e in res.errors)

    def test_negative_tampered_report_checksum(self, mock_repo_env: Path):
        """Tampered checksum in REPORT.json must cause verification failure."""
        report_path = mock_repo_env / "validation" / "pseudobulk" / "REPORT.json"
        data = json.loads(report_path.read_text(encoding="utf-8"))
        data["dataset"]["checksum_sha256"]["published_de_truth.csv"] = "0" * 64
        report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("Checksum mismatch" in e for e in res.errors)

    def test_negative_stale_commit(self, mock_repo_env: Path):
        """Stale or mismatched commit SHA must cause verification failure."""
        report_path = mock_repo_env / "validation" / "pseudobulk" / "REPORT.json"
        data = json.loads(report_path.read_text(encoding="utf-8"))
        data["pipeline"]["provenance"]["commit_sha"] = "0000000000000000000000000000000000000000"
        report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env, enforce_commit="68a48740052462b239312d14440906b28ac7cc5b")
        assert res.passed is False
        assert any("commit_sha" in e for e in res.errors)

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

    def test_negative_dirty_provenance(self, mock_repo_env: Path):
        """git_dirty=True must cause verification failure under fail-closed policy."""
        report_path = mock_repo_env / "validation" / "annotation" / "REPORT.json"
        data = json.loads(report_path.read_text(encoding="utf-8"))
        data["pipeline"]["provenance"]["git_dirty"] = True
        report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env, allow_dirty=False)
        assert res.passed is False
        assert any("git_dirty=True" in e for e in res.errors)

    def test_negative_fake_flagship_file_in_data_dir(self, mock_repo_env: Path):
        """Synthetic pretender file in data/flagship must be rejected."""
        fake_file = mock_repo_env / "data" / "flagship" / "citeseq_pbmc_sorted" / "citeseq_pbmc.h5ad"
        fake_file.parent.mkdir(parents=True, exist_ok=True)
        fake_file.write_text("pretend synthetic content", encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("Synthetic file" in e and "masquerading" in e for e in res.errors)

    def test_negative_fake_public_reference_claim_without_dataset(self, mock_repo_env: Path):
        """A capability without a public reference dataset cannot claim one."""
        cert_path = mock_repo_env / "validation" / "spatial" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        for std in data["standards"]:
            if std["standard_id"] == "public_reference_dataset":
                std["satisfied"] = True
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("falsely claims public_reference_dataset=true" in e or "satisfied mismatch" in e for e in res.errors)

    def test_negative_fake_independent_ground_truth_claim(self, mock_repo_env: Path):
        """Synthetic report falsely claiming independent ground truth must be rejected."""
        cert_path = mock_repo_env / "validation" / "spatial" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        for std in data["standards"]:
            if std["standard_id"] == "independent_ground_truth":
                std["satisfied"] = True
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("falsely claims independent_ground_truth=true" in e or "satisfied mismatch" in e for e in res.errors)

    def test_negative_certification_tier_drift(self, mock_repo_env: Path):
        """Mismatched certification_level must cause verification failure."""
        cert_path = mock_repo_env / "validation" / "pseudobulk" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        data["certification_level"] = "CERTIFIED"
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("certification_level 'CERTIFIED' != computed tier" in e for e in res.errors)

    def test_negative_certification_verdict_drift(self, mock_repo_env: Path):
        """Mismatched summary.verdict must cause verification failure."""
        cert_path = mock_repo_env / "validation" / "annotation" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        data["summary"]["verdict"] = "CERTIFIED"
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("summary.verdict (CERTIFIED) != computed tier" in e for e in res.errors)

    def test_negative_certification_summary_count_drift(self, mock_repo_env: Path):
        """Mismatched summary.satisfied count must cause verification failure."""
        cert_path = mock_repo_env / "validation" / "spatial" / "CERTIFICATION.json"
        data = json.loads(cert_path.read_text(encoding="utf-8"))
        data["summary"]["satisfied"] = 99
        cert_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("summary.satisfied (99) !=" in e for e in res.errors)

    def test_negative_stress_report_failed_dimension(self, mock_repo_env: Path):
        """Failed dimension in INFERENTIAL_STRESS_REPORT.json must cause verification failure."""
        stress_path = mock_repo_env / "validation" / "pseudobulk" / "INFERENTIAL_STRESS_REPORT.json"
        data = json.loads(stress_path.read_text(encoding="utf-8"))
        first_dim_key = next(iter(data["dimensions"]))
        data["dimensions"][first_dim_key]["passed"] = False
        stress_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        res = verify_validation_artifacts(repo_root=mock_repo_env)
        assert res.passed is False
        assert any("did not pass" in e for e in res.errors)
