from __future__ import annotations

from dataclasses import replace

from bionexus.ecosystem_claim import (
    ECOSYSTEM_CLAIM_PACKET_VERSION,
    EcosystemClaimPacket,
    EvidenceAdjudication,
    assess_ecosystem_claim,
)
from bionexus.ecosystem_intake import (
    ExternalCapabilityFamily,
    ExternalEvidenceEnvelope,
    ExternalProducerIdentity,
)
from bionexus.human_adjudication import (
    HumanScientificAdjudication,
    HumanScientificDecision,
    adjudicate_ecosystem_claim,
    assessment_sha256,
)

HEX_C = "c" * 64


def _assessment(*, relationship: str = "supports", context_conflict: bool = False):
    envelope = ExternalEvidenceEnvelope.create(
        evidence_id="EVID-1",
        family=ExternalCapabilityFamily.DATABASE,
        producer=ExternalProducerIdentity(
            plugin_id="life-sciences-databases",
            capability="completed_external_result",
            tool_name="query_uniprot",
            plugin_version="2026.08",
        ),
        source_context={
            "source_name": "UniProt",
            "record_ids": ["P04637"],
            "database_release": "2026_03",
            "identifier_namespace": "UniProtKB",
            "organism_taxon": "NCBI:9606",
        },
        payload={"gene": "TP53"},
        request={"accession": "P04637"},
    )
    adjudication = EvidenceAdjudication(
        evidence_id=envelope.evidence_id,
        relationship=relationship,
        maturity="PRELIMINARY",
        rationale="Reviewed in the declared scope.",
        adjudicator_id="reviewer:alice",
        adjudication_receipt_sha256=HEX_C,
        validation_role="supporting",
    )
    return assess_ecosystem_claim(
        EcosystemClaimPacket(
            schema_version=ECOSYSTEM_CLAIM_PACKET_VERSION,
            claim_id="CLAIM-1",
            statement="TP53 is associated with the DNA damage response.",
            decision_owner="researcher:principal-investigator",
            envelopes=(envelope,),
            adjudications=(adjudication,),
            claim_context={
                "organism_taxon": "NCBI:10090" if context_conflict else "NCBI:9606"
            },
        )
    )


def _human_record(assessment, decision: HumanScientificDecision, **overrides):
    values = {
        "claim_id": assessment.claim_id,
        "decision": decision.value,
        "decision_owner_id": assessment.decision_owner,
        "adjudicator_id": "scientist:dr-chen",
        "decided_at": "2026-08-29T10:30:00-07:00",
        "rationale": "The signal is useful for bounded hypothesis generation.",
        "intended_use": "prioritize candidates for an independent follow-up experiment",
        "assessment_sha256": assessment_sha256(assessment),
        "human_attestation": True,
        "acknowledges_evidence_limits": True,
    }
    values.update(overrides)
    return HumanScientificAdjudication.create(**values)


def test_valid_human_decision_preserves_machine_warrant_exactly() -> None:
    assessment = _assessment()
    record = _human_record(assessment, HumanScientificDecision.ACCEPT_FOR_EXPLORATION)

    result = adjudicate_ecosystem_claim(assessment, record)

    assert result.status == "VALID"
    assert result.final_decision == "ACCEPT_FOR_EXPLORATION"
    assert result.human_decision_required is False
    assert result.preserved_conclusion_maturity == assessment.conclusion_maturity
    assert result.preserved_warrant == assessment.warrant


def test_changed_assessment_or_record_fails_closed_to_pending() -> None:
    assessment = _assessment()
    record = _human_record(
        assessment,
        HumanScientificDecision.ACCEPT_WITH_LIMITS,
        conditions=("Do not use as confirmatory evidence.",),
    )
    tampered = replace(record, rationale="Different rationale after receipt.")

    result = adjudicate_ecosystem_claim(assessment, tampered)

    assert result.status == "INVALID"
    assert result.final_decision == "PENDING_HUMAN_DECISION"
    assert any("decision_receipt_sha256" in error for error in result.errors)


def test_accept_with_limits_requires_explicit_human_conditions() -> None:
    assessment = _assessment()
    record = _human_record(assessment, HumanScientificDecision.ACCEPT_WITH_LIMITS)

    result = adjudicate_ecosystem_claim(assessment, record)

    assert result.status == "INVALID"
    assert any("explicit condition" in error for error in result.errors)


def test_blocked_assessment_cannot_be_human_overridden_into_acceptance() -> None:
    assessment = _assessment(context_conflict=True)
    record = _human_record(
        assessment,
        HumanScientificDecision.ACCEPT_WITH_LIMITS,
        conditions=("Restrict interpretation to the declared organism context.",),
    )

    result = adjudicate_ecosystem_claim(assessment, record)

    assert result.status == "INVALID"
    assert any("structurally BLOCKED" in error for error in result.errors)


def test_conflicted_acceptance_requires_every_contradiction_to_be_addressed() -> None:
    assessment = _assessment(relationship="contradicts")
    incomplete = _human_record(assessment, HumanScientificDecision.ACCEPT_FOR_EXPLORATION)
    rejected = adjudicate_ecosystem_claim(assessment, incomplete)
    complete = _human_record(
        assessment,
        HumanScientificDecision.ACCEPT_FOR_EXPLORATION,
        addressed_contradiction_ids=("EVID-1",),
    )
    accepted = adjudicate_ecosystem_claim(assessment, complete)

    assert rejected.status == "INVALID"
    assert any("contradicted evidence" in error for error in rejected.errors)
    assert accepted.status == "VALID"


def test_ai_identity_cannot_serve_as_human_scientific_owner() -> None:
    assessment = _assessment()
    snapshot = assessment.to_dict()
    snapshot["decision_owner"] = "agent:gpt"
    record = HumanScientificAdjudication.create(
        claim_id=assessment.claim_id,
        decision=HumanScientificDecision.DEFER_PENDING_EVIDENCE.value,
        decision_owner_id="agent:gpt",
        adjudicator_id="model:reviewer",
        decided_at="2026-08-29T10:30:00-07:00",
        rationale="Await more evidence.",
        intended_use="",
        assessment_sha256=assessment_sha256(snapshot),
        human_attestation=True,
        acknowledges_evidence_limits=True,
    )

    result = adjudicate_ecosystem_claim(snapshot, record)

    assert result.status == "INVALID"
    assert any("AI/model identity" in error for error in result.errors)
