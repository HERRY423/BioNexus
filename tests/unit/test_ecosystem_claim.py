"""Contract tests for passive multi-source claim assessment."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

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

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


def _producer(plugin: str, tool: str) -> ExternalProducerIdentity:
    return ExternalProducerIdentity(
        plugin_id=plugin,
        capability="completed_external_result",
        tool_name=tool,
        plugin_version="2026.08",
    )


def _database(evidence_id: str, payload: object | None = None) -> ExternalEvidenceEnvelope:
    return ExternalEvidenceEnvelope.create(
        evidence_id=evidence_id,
        family=ExternalCapabilityFamily.DATABASE,
        producer=_producer("life-sciences-databases", "query_uniprot"),
        source_context={
            "source_name": "UniProt",
            "record_ids": ["P04637"],
            "database_release": "2026_03",
            "identifier_namespace": "UniProtKB",
            "organism_taxon": "NCBI:9606",
        },
        payload=payload if payload is not None else {"gene": "TP53"},
        request={"accession": "P04637"},
    )


def _literature(evidence_id: str) -> ExternalEvidenceEnvelope:
    return ExternalEvidenceEnvelope.create(
        evidence_id=evidence_id,
        family=ExternalCapabilityFamily.LITERATURE,
        producer=_producer("life-sciences-literature", "search_pubmed"),
        source_context={
            "source_name": "PubMed",
            "identifiers": ["PMID:123"],
            "publication_status": "peer_reviewed",
            "study_design": "observational cohort",
            "organism_taxon": "NCBI:9606",
        },
        payload={"reported_association": "TP53 and DNA damage response"},
        request={"query": "TP53 DNA damage"},
    )


def _adjudication(evidence_id: str, relationship: str = "supports") -> EvidenceAdjudication:
    return EvidenceAdjudication(
        evidence_id=evidence_id,
        relationship=relationship,
        maturity="SUPPORTED" if relationship != "context" else "UNASSESSED",
        rationale="Reviewed against the declared claim scope and source limitations.",
        adjudicator_id="reviewer:alice",
        adjudication_receipt_sha256=HEX_C,
        validation_role="supporting" if relationship != "context" else "context_only",
    )


def _packet(
    envelopes: tuple[ExternalEvidenceEnvelope, ...],
    adjudications: tuple[EvidenceAdjudication, ...],
    *,
    claim_context: dict | None = None,
) -> EcosystemClaimPacket:
    return EcosystemClaimPacket(
        schema_version=ECOSYSTEM_CLAIM_PACKET_VERSION,
        claim_id="CLAIM-TP53-1",
        statement="TP53 is associated with the DNA damage response.",
        decision_owner="researcher:principal-investigator",
        envelopes=envelopes,
        adjudications=adjudications,
        claim_context=claim_context or {"organism_taxon": "NCBI:9606"},
    )


def test_review_bound_sources_produce_warrant_audit_card_and_pending_decision() -> None:
    database = _database("EXT-DB-1")
    literature = _literature("EXT-LIT-1")

    result = assess_ecosystem_claim(
        _packet(
            (database, literature),
            (_adjudication(database.evidence_id), _adjudication(literature.evidence_id)),
        )
    )

    claim = result.ledger["claims"]["CLAIM-TP53-1"]
    assert result.audit.status == "PASS"
    assert set(claim["supported_by"]) == {"EXT-DB-1", "EXT-LIT-1"}
    assert result.ledger["evidence"]["EXT-DB-1"]["provenance"]["support_tier"] == "corroboration"
    assert result.warrant
    assert result.evidence_card["details"]["claim_conclusion_maturity"] == result.conclusion_maturity
    assert result.final_decision == "PENDING_HUMAN_DECISION"
    assert result.decision_owner == "researcher:principal-investigator"


def test_context_conflict_blocks_all_claim_bearing_edges() -> None:
    database = _database("EXT-DB-2")

    result = assess_ecosystem_claim(
        _packet(
            (database,),
            (_adjudication(database.evidence_id),),
            claim_context={"organism_taxon": "NCBI:10090"},
        )
    )

    claim = result.ledger["claims"]["CLAIM-TP53-1"]
    assert result.audit.status == "BLOCKED"
    assert result.audit.context_conflicts[0]["field"] == "organism_taxon"
    assert claim["supported_by"] == []
    assert result.conclusion_maturity == "ABSTAIN"


def test_missing_adjudication_fails_closed() -> None:
    database = _database("EXT-DB-3")

    result = assess_ecosystem_claim(_packet((database,), ()))

    assert result.audit.status == "BLOCKED"
    assert result.audit.missing_adjudications == ("EXT-DB-3",)
    assert result.final_decision == "PENDING_HUMAN_DECISION"


def test_duplicate_payload_is_not_double_counted() -> None:
    first = _database("EXT-DB-4", payload={"gene": "TP53", "record": 1})
    second = _database("EXT-DB-5", payload={"gene": "TP53", "record": 1})

    result = assess_ecosystem_claim(
        _packet(
            (first, second),
            (_adjudication(first.evidence_id), _adjudication(second.evidence_id)),
        )
    )

    claim = result.ledger["claims"]["CLAIM-TP53-1"]
    assert result.audit.status == "PASS"
    assert result.audit.duplicate_payload_groups == (("EXT-DB-4", "EXT-DB-5"),)
    assert claim["supported_by"] == ["EXT-DB-4"]
    assert claim["depends_on"] == ["EXT-DB-5"]


def test_explicit_reviewed_contradiction_yields_conflicted_not_consensus() -> None:
    database = _database("EXT-DB-6")
    literature = _literature("EXT-LIT-2")

    result = assess_ecosystem_claim(
        _packet(
            (database, literature),
            (
                _adjudication(database.evidence_id),
                _adjudication(literature.evidence_id, relationship="contradicts"),
            ),
        )
    )

    assert result.audit.status == "CONFLICTED"
    assert result.conclusion_maturity == "CONFLICTED"
    assert result.evidence_card["cross_method_concordance"] == "CONFLICTED"


def test_claim_bearing_relationship_requires_named_receipted_review() -> None:
    database = _database("EXT-DB-7")
    unreviewed = EvidenceAdjudication(
        evidence_id=database.evidence_id,
        relationship="supports",
        maturity="SUPPORTED",
    )

    result = assess_ecosystem_claim(_packet((database,), (unreviewed,)))

    assert result.audit.status == "BLOCKED"
    assert any("adjudicator_id" in error for error in result.audit.errors)
    assert result.conclusion_maturity == "ABSTAIN"


def test_context_only_packet_is_admissible_but_cannot_support_the_claim() -> None:
    database = _database("EXT-DB-8")

    result = assess_ecosystem_claim(
        _packet((database,), (_adjudication(database.evidence_id, relationship="context"),))
    )

    claim = result.ledger["claims"]["CLAIM-TP53-1"]
    assert result.audit.status == "PASS"
    assert claim["supported_by"] == []
    assert claim["depends_on"] == ["EXT-DB-8"]
    assert result.conclusion_maturity == "ABSTAIN"
    assert result.warrant["tier_verdicts"]["association_claim"]["status"] == "NOT_WARRANTED"
    assert result.ledger["evidence"]["EXT-DB-8"]["provenance"]["support_tier"] == "context_only"


def test_intermediate_support_tier_is_visible_without_becoming_external_validation() -> None:
    database = _database("EXT-DB-TRIANGULATION")
    adjudication = EvidenceAdjudication(
        evidence_id=database.evidence_id,
        relationship="supports",
        maturity="PRELIMINARY",
        rationale="Alternative analytical approach agrees within the declared scope.",
        adjudicator_id="reviewer:alice",
        adjudication_receipt_sha256=HEX_C,
        validation_role="supporting",
        qualification={"support_basis": "methodological_triangulation"},
    )

    result = assess_ecosystem_claim(_packet((database,), (adjudication,)))

    ref = result.ledger["evidence"][database.evidence_id]
    assert ref["provenance"]["support_tier"] == "methodological_triangulation"
    assert ref["validation_role"] == "supporting"


def test_claim_assessment_cli_writes_reusable_artifact(tmp_path: Path) -> None:
    database = _database("EXT-DB-CLI")
    packet = _packet((database,), (_adjudication(database.evidence_id),))
    packet_path = tmp_path / "claim-packet.json"
    output_path = tmp_path / "assessment.json"
    packet_path.write_text(json.dumps(packet.to_dict()), encoding="utf-8")
    repo_root = Path(__file__).resolve().parents[2]
    script = repo_root / "skills" / "external-evidence-audit" / "scripts" / "assess_ecosystem_claim.py"

    completed = subprocess.run(
        [sys.executable, str(script), str(packet_path), "--out", str(output_path)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    artifact = json.loads(output_path.read_text(encoding="utf-8"))
    assert artifact["schema_version"] == "bionexus.ecosystem-claim-assessment.v1"
    assert artifact["audit"]["status"] == "PASS"
    assert artifact["final_decision"] == "PENDING_HUMAN_DECISION"
