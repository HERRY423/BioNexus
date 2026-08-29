"""Unit tests validating the 3 Golden Collaboration Scenarios (BNS-022 / BNS-019)."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from bionexus.ecosystem_claim import (
    ECOSYSTEM_CLAIM_PACKET_VERSION,
    EcosystemClaimPacket,
    assess_ecosystem_claim,
)
from bionexus.ecosystem_intake import (
    IntakeStatus,
    audit_external_evidence,
)

_FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ecosystem"


def _load_fixture(filename: str) -> dict:
    path = _FIXTURES_DIR / filename
    assert path.is_file(), f"Fixture file not found: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_fixture_1_target_discovery_tp53():
    """Validate Scenario 1: Target Discovery (Literature + Database + Pseudobulk DE)."""
    raw = _load_fixture("target_discovery_tp53.json")
    packet = EcosystemClaimPacket.from_dict(raw)

    assert packet.schema_version == ECOSYSTEM_CLAIM_PACKET_VERSION
    assert packet.claim_id == "CLM-ECO-001-TARGET-TP53"
    assert len(packet.envelopes) == 3
    assert len(packet.adjudications) == 3

    # Check evidence family diversity
    families = {env.family for env in packet.envelopes}
    assert families == {"literature", "database", "analysis"}

    # Every envelope must pass intake audit
    for env in packet.envelopes:
        audit = audit_external_evidence(env)
        assert audit.status == IntakeStatus.VALID.value, f"Envelope {env.evidence_id} failed audit: {audit.errors}"

    # Complete claim packet assessment
    assessment = assess_ecosystem_claim(packet)
    assert assessment.audit.status == "PASS"
    assert len(assessment.audit.errors) == 0
    assert assessment.conclusion_maturity == "SUPPORTED"


def test_fixture_2_spatial_tme_xenium():
    """Validate Scenario 2: Spatial Tumor Microenvironment & Confounder Audit (Slide + Annotation + Null)."""
    raw = _load_fixture("spatial_tme_xenium.json")
    packet = EcosystemClaimPacket.from_dict(raw)

    assert packet.schema_version == ECOSYSTEM_CLAIM_PACKET_VERSION
    assert packet.claim_id == "CLM-ECO-002-SPATIAL-TME-XENIUM"
    assert len(packet.envelopes) == 3
    assert len(packet.adjudications) == 3

    families = {env.family for env in packet.envelopes}
    assert "slide" in families and "analysis" in families

    for env in packet.envelopes:
        audit = audit_external_evidence(env)
        assert audit.status == IntakeStatus.VALID.value, f"Envelope {env.evidence_id} failed audit: {audit.errors}"

    assessment = assess_ecosystem_claim(packet)
    assert assessment.audit.status == "PASS"
    assert len(assessment.audit.errors) == 0
    assert assessment.conclusion_maturity == "SUPPORTED"


def test_fixture_3_drug_mechanism_chembl_alphafold():
    """Validate Scenario 3: Drug Mechanism & Structure-Target Interaction (Structure + Bioactivity + Literature)."""
    raw = _load_fixture("drug_mechanism_chembl_alphafold.json")
    packet = EcosystemClaimPacket.from_dict(raw)

    assert packet.schema_version == ECOSYSTEM_CLAIM_PACKET_VERSION
    assert packet.claim_id == "CLM-ECO-003-DRUG-EGFR-OSIMERTINIB"
    assert len(packet.envelopes) == 3
    assert len(packet.adjudications) == 3

    families = {env.family for env in packet.envelopes}
    assert families == {"structure", "database", "literature"}

    for env in packet.envelopes:
        audit = audit_external_evidence(env)
        assert audit.status == IntakeStatus.VALID.value, f"Envelope {env.evidence_id} failed audit: {audit.errors}"

    assessment = assess_ecosystem_claim(packet)
    assert assessment.audit.status == "PASS"
    assert len(assessment.audit.errors) == 0
    assert assessment.conclusion_maturity in ("SUPPORTED", "PRELIMINARY", "FRAGILE")
