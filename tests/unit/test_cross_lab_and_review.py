"""
Unit tests for BioNexus Cross-Host Multi-Lab Protocol & Independent Scientific Review.
Validates:
1. Host environment fingerprinting & tamper-evident record generation (BNS-HC-007)
2. Multi-host execution concordance and Standard 13 satisfaction
3. Independent non-author scientific review dossier, COI disclosure, and Standard 14 satisfaction
"""

import json

import pytest

from bionexus.cross_lab_protocol import (
    HostEnvironmentFingerprint,
    MultiLabCertificationDossier,
    build_cross_host_dossier,
    capture_host_fingerprint,
)
from bionexus.scientific_review_dossier import (
    ScientificReviewDossier,
    generate_certified_scientific_review,
)


def test_capture_host_fingerprint(tmp_path):
    """Test host environment fingerprint captures valid runtime telemetry."""
    fingerprint = capture_host_fingerprint("test-host-01", tmp_path, execution_mode="test_mode")
    assert isinstance(fingerprint, HostEnvironmentFingerprint)
    assert fingerprint.host_id == "test-host-01"
    assert fingerprint.execution_mode == "test_mode"
    assert len(fingerprint.platform_system) > 0
    assert len(fingerprint.python_version) > 0
    assert len(fingerprint.timestamp) > 0


def test_build_cross_host_dossier(tmp_path):
    """Test multi-host execution dossier compares report outputs across environments."""
    rep_a = tmp_path / "study_a.json"
    rep_a.write_text(json.dumps({"result": "pass_sample_1"}), encoding="utf-8")

    studies = [
        ("scrna.pseudobulk_de", "BN-PB-IV-006", rep_a),
    ]

    dossier = build_cross_host_dossier(repo_root=tmp_path, studies_to_compare=studies)
    assert isinstance(dossier, MultiLabCertificationDossier)
    assert len(dossier.participating_hosts) == 1
    assert len(dossier.comparisons) == 1
    assert dossier.overall_agreement_rate is None
    assert dossier.standard_13_satisfied is False
    assert dossier.status == "PENDING_EXTERNAL_REPLICATION"
    assert dossier.comparisons[0].replication_checksum == ""
    assert dossier.comparisons[0].verified is False


def test_review_template_requires_actual_external_submission(tmp_path):
    """Empty directories must not invent reviewers, COI declarations or approval."""
    dossier = generate_certified_scientific_review(repo_root=tmp_path, write=True)
    assert isinstance(dossier, ScientificReviewDossier)
    assert dossier.reviewers == []
    assert dossier.case_reviews == []
    assert dossier.overall_verdict == "PENDING_EXTERNAL_REVIEW"
    assert dossier.standard_14_satisfied is False
    assert len(dossier.dossier_sha256) == 64
    out_file = tmp_path / "review" / "SCIENTIFIC_REVIEW.json"
    saved = json.loads(out_file.read_text(encoding="utf-8"))
    assert saved["status"] == "PENDING_EXTERNAL_REVIEW"
    assert saved["scientific_authorization"] == "NONE"
    before = out_file.read_bytes()
    with pytest.raises(FileExistsError):
        generate_certified_scientific_review(repo_root=tmp_path, write=True)
    assert out_file.read_bytes() == before
