from __future__ import annotations

import json
from pathlib import Path

from bionexus.attestation_authority import TRUST_ANCHORS

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_default_or_legacy_trust_anchor_is_packaged():
    registry = json.loads((REPO_ROOT / "src/bionexus/data/trust_registry.json").read_text(encoding="utf-8"))
    assert registry["status"] == "DEVELOPMENT_NO_TRUST_ANCHORS"
    assert registry["keys"] == []
    assert registry["revocations"] == []
    assert TRUST_ANCHORS == {}


def test_production_rule_registry_has_no_evidence_like_endorsements():
    registry = json.loads((REPO_ROOT / "src/bionexus/data/rule_registry.json").read_text(encoding="utf-8"))
    assert registry["registry_status"] == "DEVELOPMENT_UNVERIFIED"
    assert registry["external_validation_claimed"] is False
    assert registry["challenges"] == {}
    for rule in registry["rules"].values():
        assert rule["dataset_calibrations"] == []
        assert rule["platform_calibrations"] == []
        assert rule["sensitivity_analysis"] == []
        assert rule["reviewers"] == []
        assert rule["metadata"]["attestation_ids"] == []


def test_former_named_study_reviews_are_withdrawn():
    for study_id in ("BN-PB-IV-004", "BN-PB-IV-005"):
        study_dir = REPO_ROOT / "validation/pseudobulk/studies" / study_id
        review = json.loads(
            (study_dir / "INDEPENDENT_BIOSTATISTICIAN_ATTESTATION.json").read_text(encoding="utf-8")
        )
        assert review["status"] == "WITHDRAWN_UNVERIFIABLE"
        assert review["trust_decision"] == "NOT_ASSESSED"
        assert review["reviewer"] is None
        assert review["signature"] is None
