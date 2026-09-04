"""Tests for Evidence Independence Graph and Epistemic Lineage Resolution."""

from __future__ import annotations

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
from bionexus.epistemic_lineage import (
    EpistemicLineage,
    EvidenceIndependenceGraph,
    OriginType,
)

HEX_C = "c" * 64


def _producer(plugin: str, tool: str) -> ExternalProducerIdentity:
    return ExternalProducerIdentity(
        plugin_id=plugin,
        capability="completed_external_result",
        tool_name=tool,
        plugin_version="2026.08",
    )


def test_epistemic_lineage_graph_8_objects_resolve_to_2_primary_studies() -> None:
    """Validate the exact 8-object / 5-connector / 2-primary-study scenario from specification.

    Breakdown:
      2 Primary studies:
        - pubmed: PMID 12345
        - chembl: Assay CHEMBL_999
      4 Derived syntheses:
        - consensus: AI summary of PMID 12345
        - pubcrawl: Literature crawler summary of PMID 12345
        - scholar_sidekick: Assistant summary of PMID 12345
        - bioskepsis: Evaluation synthesizing PMID 12345 and CHEMBL_999
      2 Database mirrors:
        - opentargets: Evidence record mirroring CHEMBL_999
        - secondary_chembl_mirror: Secondary mirror of CHEMBL_999
      5 Connectors:
        - pubmed
        - consensus
        - chembl
        - opentargets
        - bioskepsis
    """
    graph = EvidenceIndependenceGraph()

    # 1. Primary study 1 (PubMed)
    graph.add_evidence(
        evidence_id="OBJ-1-PUBMED",
        lineage=EpistemicLineage(
            origin_id="PMID:12345",
            origin_type=OriginType.PRIMARY_STUDY.value,
        ),
        connector_id="pubmed",
        payload_sha256="1" * 64,
    )
    # 2. Derived synthesis 1 (Consensus)
    graph.add_evidence(
        evidence_id="OBJ-2-CONSENSUS",
        lineage=EpistemicLineage(
            origin_id="consensus:summary:1",
            origin_type=OriginType.DERIVED_SYNTHESIS.value,
            derived_from=("PMID:12345",),
        ),
        connector_id="consensus",
        payload_sha256="2" * 64,
    )
    # 3. Derived synthesis 2 (PubCrawl via pubmed connector)
    graph.add_evidence(
        evidence_id="OBJ-3-PUBCRAWL",
        lineage=EpistemicLineage(
            origin_id="pubcrawl:summary:2",
            origin_type=OriginType.DERIVED_SYNTHESIS.value,
            derived_from=("PMID:12345",),
        ),
        connector_id="pubmed",
        payload_sha256="3" * 64,
    )
    # 4. Derived synthesis 3 (Scholar Sidekick via consensus connector)
    graph.add_evidence(
        evidence_id="OBJ-4-SCHOLAR-SIDEKICK",
        lineage=EpistemicLineage(
            origin_id="sidekick:summary:3",
            origin_type=OriginType.DERIVED_SYNTHESIS.value,
            derived_from=("PMID:12345",),
        ),
        connector_id="consensus",
        payload_sha256="4" * 64,
    )

    # 5. Primary study 2 (ChEMBL)
    graph.add_evidence(
        evidence_id="OBJ-5-CHEMBL",
        lineage=EpistemicLineage(
            origin_id="CHEMBL:CHEMBL999",
            origin_type=OriginType.PRIMARY_STUDY.value,
            assay_identity="CHEMBL_ASSAY:999",
        ),
        connector_id="chembl",
        payload_sha256="5" * 64,
    )
    # 6. Database mirror 1 (Open Targets)
    graph.add_evidence(
        evidence_id="OBJ-6-OPENTARGETS",
        lineage=EpistemicLineage(
            origin_id="OT:EVID:CHEMBL999",
            origin_type=OriginType.DATABASE_MIRROR.value,
            assay_identity="CHEMBL_ASSAY:999",
            derived_from=("CHEMBL:CHEMBL999",),
        ),
        connector_id="opentargets",
        payload_sha256="6" * 64,
    )
    # 7. Derived synthesis 4 (BioSkepsis)
    graph.add_evidence(
        evidence_id="OBJ-7-BIOSKEPSIS",
        lineage=EpistemicLineage(
            origin_id="bioskepsis:synth:1",
            origin_type=OriginType.DERIVED_SYNTHESIS.value,
            derived_from=("PMID:12345",),
            aggregates=("PMID:12345", "CHEMBL:CHEMBL999"),
        ),
        connector_id="bioskepsis",
        payload_sha256="7" * 64,
    )
    # 8. Database mirror 2 (ChEMBL Mirror)
    graph.add_evidence(
        evidence_id="OBJ-8-CHEMBL-MIRROR",
        lineage=EpistemicLineage(
            origin_id="mirror:chembl999",
            origin_type=OriginType.DATABASE_MIRROR.value,
            assay_identity="CHEMBL_ASSAY:999",
        ),
        connector_id="chembl",
        payload_sha256="8" * 64,
    )

    metrics = graph.compute_metrics()
    assert metrics.raw_evidence_count == 8
    assert metrics.connector_count == 5
    assert metrics.primary_studies == 2
    assert metrics.derived_syntheses == 4
    assert metrics.database_mirrors == 2
    assert metrics.independent_origins == 2
    assert "2 declared primary studies" in metrics.summary_statement
    assert metrics.independence_status == "NOT_ESTABLISHED"
    assert len(metrics.lineage_roots["OBJ-7-BIOSKEPSIS"]) == 2


def test_claim_assessment_collapses_non_independent_connectors() -> None:
    """Verify that multiple connectors reporting on the same study do not double-count in supported_by."""
    # 1. PubMed envelope
    pubmed_env = ExternalEvidenceEnvelope.create(
        evidence_id="ENV-PUBMED-1",
        family=ExternalCapabilityFamily.LITERATURE,
        producer=_producer("pubmed-plugin", "search_pubmed"),
        source_context={
            "source_name": "PubMed",
            "identifiers": ["PMID:12345"],
            "publication_status": "peer_reviewed",
            "study_design": "randomized controlled trial",
            "organism_taxon": "NCBI:9606",
        },
        payload={"finding": "Drug X inhibits Target Y with IC50 12nM", "source": "journal"},
        epistemic_lineage={
            "origin_id": "PMID:12345",
            "origin_type": "primary_study",
        },
    )

    # 2. Consensus summary envelope (different payload, but derived from PMID:12345)
    consensus_env = ExternalEvidenceEnvelope.create(
        evidence_id="ENV-CONSENSUS-1",
        family=ExternalCapabilityFamily.LITERATURE,
        producer=_producer("consensus-plugin", "summarize_evidence"),
        source_context={
            "source_name": "Consensus",
            "identifiers": ["PMID:12345"],
            "publication_status": "peer_reviewed",
            "study_design": "ai_summary",
            "organism_taxon": "NCBI:9606",
        },
        payload={"ai_summary": "High agreement that Drug X inhibits Target Y.", "confidence": 0.95},
        epistemic_lineage={
            "origin_id": "consensus:pmid:12345",
            "origin_type": "derived_synthesis",
            "derived_from": ["PMID:12345"],
        },
    )

    # 3. bioRxiv preprint envelope (different payload, but same study as PMID:12345)
    biorxiv_env = ExternalEvidenceEnvelope.create(
        evidence_id="ENV-BIORXIV-1",
        family=ExternalCapabilityFamily.LITERATURE,
        producer=_producer("biorxiv-plugin", "search_biorxiv"),
        source_context={
            "source_name": "bioRxiv",
            "identifiers": ["doi:10.1101/2023.01"],
            "publication_status": "preprint",
            "study_design": "in_vitro_assay",
            "organism_taxon": "NCBI:9606",
        },
        payload={"preprint_text": "Initial preprint manuscript on Drug X and Target Y."},
        epistemic_lineage={
            "origin_id": "doi:10.1101/2023.01",
            "origin_type": "preprint",
            "same_study_as": ["PMID:12345"],
        },
    )

    # 4. Independent orthogonal study (Target Z / Study 2)
    independent_env = ExternalEvidenceEnvelope.create(
        evidence_id="ENV-INDEP-1",
        family=ExternalCapabilityFamily.DATABASE,
        producer=_producer("chembl-plugin", "query_chembl"),
        source_context={
            "source_name": "ChEMBL",
            "record_ids": ["CHEMBL999"],
            "database_release": "33",
            "identifier_namespace": "chembl",
            "organism_taxon": "NCBI:9606",
        },
        payload={"target": "Target Y", "ki_nm": 15},
        epistemic_lineage={
            "origin_id": "CHEMBL:CHEMBL999",
            "origin_type": "primary_study",
            "assay_identity": "ASSAY_999",
        },
    )

    adjudications = (
        EvidenceAdjudication(
            evidence_id=pubmed_env.evidence_id,
            relationship="supports",
            maturity="SUPPORTED",
            rationale="Direct RCT evidence",
            adjudicator_id="reviewer:alice",
            adjudication_receipt_sha256=HEX_C,
        ),
        EvidenceAdjudication(
            evidence_id=consensus_env.evidence_id,
            relationship="supports",
            maturity="SUPPORTED",
            rationale="AI summary corroboration",
            adjudicator_id="reviewer:alice",
            adjudication_receipt_sha256=HEX_C,
        ),
        EvidenceAdjudication(
            evidence_id=biorxiv_env.evidence_id,
            relationship="supports",
            maturity="SUPPORTED",
            rationale="Preprint version of study",
            adjudicator_id="reviewer:alice",
            adjudication_receipt_sha256=HEX_C,
        ),
        EvidenceAdjudication(
            evidence_id=independent_env.evidence_id,
            relationship="supports",
            maturity="SUPPORTED",
            rationale="Orthogonal biochemical assay",
            adjudicator_id="reviewer:alice",
            adjudication_receipt_sha256=HEX_C,
        ),
    )

    packet = EcosystemClaimPacket(
        schema_version=ECOSYSTEM_CLAIM_PACKET_VERSION,
        claim_id="CLAIM-DRUG-X",
        statement="Drug X inhibits Target Y.",
        decision_owner="researcher:dr-smith",
        envelopes=(pubmed_env, consensus_env, biorxiv_env, independent_env),
        adjudications=adjudications,
        claim_context={"organism_taxon": "NCBI:9606"},
    )

    assessment = assess_ecosystem_claim(packet)
    assert assessment.audit.status == "PASS"

    claim = assessment.ledger["claims"]["CLAIM-DRUG-X"]
    # All 4 objects claimed to support, but ENV-CONSENSUS-1 and ENV-BIORXIV-1 resolve to Study 1 (PMID:12345).
    # Thus only 2 independent study representatives should be in supported_by!
    assert len(claim["supported_by"]) == 2
    assert "ENV-PUBMED-1" in claim["supported_by"]
    assert "ENV-INDEP-1" in claim["supported_by"]

    # The derived consensus summary and preprint are demoted to depends_on to prevent double counting:
    assert "ENV-CONSENSUS-1" in claim["depends_on"]
    assert "ENV-BIORXIV-1" in claim["depends_on"]

    # Audit and EvidenceCard verify the resolution
    metrics = assessment.audit.epistemic_lineage_metrics
    assert metrics["raw_evidence_count"] == 4
    assert metrics["primary_studies"] == 2
    assert "2 declared primary studies" in assessment.audit.epistemic_resolution_summary
    assert (
        "2 declared primary studies"
        in assessment.evidence_card["details"]["epistemic_resolution_summary"]
    )
    assert any("Epistemic double counting prevented" in w for w in assessment.audit.warnings)


def _primary(graph, eid, **kwargs):
    graph.add_evidence(
        evidence_id=eid,
        lineage=EpistemicLineage(origin_id=f"study:{eid}", origin_type="primary_study", **kwargs),
    )


def test_missing_lineage_and_orphan_syntheses_do_not_invent_primary_studies():
    graph = EvidenceIndependenceGraph()
    graph.add_evidence(evidence_id="unknown")
    graph.add_evidence(evidence_id="summary", lineage=EpistemicLineage(
        origin_id="summary:1", origin_type="derived_synthesis"))
    graph.add_evidence(evidence_id="mirror", lineage=EpistemicLineage(
        origin_id="mirror:1", origin_type="database_mirror"))
    metrics = graph.compute_metrics()
    assert metrics.primary_studies == metrics.independent_origins == 0
    assert metrics.connector_count == 0
    assert metrics.unresolved_evidence_ids == ["mirror", "summary", "unknown"]
    assert metrics.independence_status == "NOT_ESTABLISHED"
    selected, excluded = graph.get_independent_support_set(["unknown", "nonexistent"])
    assert selected == []
    assert set(excluded) == {"unknown", "nonexistent"}


def test_multi_source_synthesis_preserves_two_roots_and_prefers_primary_support():
    from itertools import permutations

    entries = {
        "a-summary": EpistemicLineage(origin_id="synthesis:1", origin_type="meta_analysis",
                                     aggregates=("study:one", "study:two")),
        "one": EpistemicLineage(origin_id="study:one", origin_type="primary_study"),
        "two": EpistemicLineage(origin_id="study:two", origin_type="primary_study"),
    }
    snapshots = []
    for order in permutations(entries):
        graph = EvidenceIndependenceGraph()
        for eid in order:
            graph.add_evidence(evidence_id=eid, lineage=entries[eid])
        metrics = graph.compute_metrics()
        assert metrics.primary_studies == 2
        assert metrics.lineage_roots["a-summary"] == ["origin:study:one", "origin:study:two"]
        assert graph.get_independent_support_set(order) == (["one", "two"], ["a-summary"])
        snapshots.append(metrics.to_dict())
    assert all(snapshot == snapshots[0] for snapshot in snapshots)


def test_derived_from_multiple_studies_does_not_union_them():
    graph = EvidenceIndependenceGraph()
    _primary(graph, "one")
    _primary(graph, "two")
    graph.add_evidence(evidence_id="summary", lineage=EpistemicLineage(
        origin_type="derived_synthesis", derived_from=("study:one", "study:two")))
    metrics = graph.compute_metrics()
    assert metrics.primary_studies == 2
    assert len(metrics.lineage_roots["summary"]) == 2
    assert len(metrics.study_clusters) == 2


def test_cycles_and_dangling_sources_remain_unresolved_without_recursion():
    graph = EvidenceIndependenceGraph()
    _primary(graph, "one")
    graph.add_evidence(evidence_id="a", lineage=EpistemicLineage(
        origin_id="A", origin_type="derived_synthesis", derived_from=("B", "study:one")))
    graph.add_evidence(evidence_id="b", lineage=EpistemicLineage(
        origin_id="B", origin_type="derived_synthesis", derived_from=("A",)))
    graph.add_evidence(evidence_id="dangling", lineage=EpistemicLineage(
        origin_type="derived_synthesis", primary_source_ids=("missing:source",)))
    metrics = graph.compute_metrics()
    assert metrics.primary_studies == 1
    assert metrics.unresolved_evidence_ids == ["a", "b", "dangling"]
    assert graph.get_independent_support_set(["a", "b", "dangling", "one"])[0] == ["one"]


def test_shared_dataset_blocks_replication_without_merging_study_identity():
    graph = EvidenceIndependenceGraph()
    _primary(graph, "one", dataset_identity="cohort:TCGA")
    _primary(graph, "two", dataset_identity="cohort:TCGA")
    metrics = graph.compute_metrics()
    assert metrics.primary_studies == 2
    assert metrics.lineage_roots["one"] != metrics.lineage_roots["two"]
    assert graph.get_independent_support_set(["two", "one"]) == (["one"], ["two"])


def test_common_citation_is_not_same_study_or_derived_support():
    graph = EvidenceIndependenceGraph()
    _primary(graph, "one", cites=("methods:paper",))
    _primary(graph, "two", cites=("methods:paper",))
    assert graph.get_independent_support_set(["two", "one"]) == (["one", "two"], [])


def test_same_study_alias_and_payload_duplicates_are_collapsed():
    graph = EvidenceIndependenceGraph()
    graph.add_evidence(evidence_id="journal", payload_sha256="a" * 64,
                       lineage=EpistemicLineage(origin_id="PMID:1", origin_type="primary_study"))
    graph.add_evidence(evidence_id="preprint", lineage=EpistemicLineage(
        origin_id="doi:preprint", origin_type="preprint", same_study_as=("PMID:1",)))
    graph.add_evidence(evidence_id="mirror", payload_sha256="a" * 64)
    assert graph.compute_metrics().primary_studies == 1
    assert graph.get_independent_support_set(["mirror", "preprint", "journal"]) == (
        ["journal"], ["preprint", "mirror"])


def test_malformed_lineage_identifiers_do_not_become_source_ids():
    lineage = EpistemicLineage.from_dict({
        "origin_id": {"not": "an identifier"}, "origin_type": "made_up",
        "derived_from": 123, "primary_source_ids": [True, {}, "unknown"],
    })
    assert lineage.origin_id is None
    assert lineage.origin_type == "unknown"
    assert lineage.derived_from == lineage.primary_source_ids == ()


def test_local_evidence_references_resolve_and_propagate_shared_resources():
    graph = EvidenceIndependenceGraph()
    _primary(graph, "one", model_identity="model:v1")
    _primary(graph, "two", model_identity="model:v1")
    graph.add_evidence(evidence_id="summary", lineage=EpistemicLineage(
        origin_type="derived_synthesis", derived_from=("one",)))
    assert graph.compute_metrics().lineage_roots["summary"] == ["origin:study:one"]
    assert graph.get_independent_support_set(["two", "summary"])[0] == ["two"]


def test_reviewed_summary_does_not_displace_primary_in_claim_assessment():
    from dataclasses import replace

    def envelope(eid, lineage):
        return ExternalEvidenceEnvelope.create(
            evidence_id=eid, family=ExternalCapabilityFamily.LITERATURE,
            producer=_producer("literature", "retrieve"),
            source_context={"source_name": "PubMed", "identifiers": [eid],
                            "publication_status": "peer_reviewed", "study_design": "declared",
                            "organism_taxon": "NCBI:9606"},
            payload={"id": eid}, epistemic_lineage=lineage,
        )

    summary = envelope("a-summary", {"origin_type": "derived_synthesis", "aggregates": ["S1", "S2"]})
    first = envelope("study-1", {"origin_id": "S1", "origin_type": "primary_study"})
    second = envelope("study-2", {"origin_id": "S2", "origin_type": "primary_study"})
    adjudications = tuple(EvidenceAdjudication(
        evidence_id=e.evidence_id, relationship="supports", maturity="SUPPORTED",
        rationale="Reviewed within scope.", adjudicator_id="reviewer:alice",
        adjudication_receipt_sha256=HEX_C,
    ) for e in (summary, first, second))
    packet = EcosystemClaimPacket(
        schema_version=ECOSYSTEM_CLAIM_PACKET_VERSION, claim_id="CLAIM-LINEAGE",
        statement="An association is reported.", decision_owner="researcher:alice",
        envelopes=(summary, second, first), adjudications=adjudications,
    )
    for envelopes in ((summary, second, first), (first, summary, second)):
        result = assess_ecosystem_claim(replace(packet, envelopes=envelopes))
        claim = result.ledger["claims"]["CLAIM-LINEAGE"]
        assert result.audit.status == "PASS"
        assert claim["supported_by"] == ["study-1", "study-2"]
        assert claim["depends_on"] == ["a-summary"]
        assert result.audit.epistemic_lineage_metrics["independence_status"] == "NOT_ESTABLISHED"
        assert result.final_decision == "PENDING_HUMAN_DECISION"

    # Peer review status by itself must not fabricate primary-study identity.
    result = assess_ecosystem_claim(replace(packet, envelopes=tuple(
        replace(e, epistemic_lineage=None) for e in packet.envelopes)))
    assert result.audit.epistemic_lineage_metrics["primary_studies"] == 0


def test_lineage_fallback_preserves_multiple_citations_without_inventing_study_type():
    from bionexus.ecosystem_claim import _extract_lineage

    envelope = ExternalEvidenceEnvelope.create(
        evidence_id="retrieval", family=ExternalCapabilityFamily.LITERATURE,
        producer=_producer("papers", "search"), payload={},
        source_context={"identifiers": ["PMID:1", "PMID:2"],
                        "publication_status": "peer_reviewed"},
    )
    lineage = _extract_lineage(envelope)
    assert lineage.origin_id is None
    assert lineage.origin_type == "unknown"
    assert lineage.primary_source_ids == ("PMID:1", "PMID:2")


def test_shared_analysis_backend_does_not_invent_shared_fitted_model():
    from bionexus.ecosystem_claim import _extract_lineage

    graph = EvidenceIndependenceGraph()
    for eid in ("one", "two"):
        envelope = ExternalEvidenceEnvelope.create(
            evidence_id=eid, family=ExternalCapabilityFamily.ANALYSIS,
            producer=_producer("analysis", "de"), payload={"id": eid},
            source_context={"dataset_id": eid, "backend_name": "pydeseq2"},
        )
        lineage = _extract_lineage(envelope)
        assert lineage.model_identity is None
        graph.add_evidence(evidence_id=eid, lineage=lineage)
    assert graph.get_independent_support_set(["one", "two"], require_resolved=False)[0] == ["one", "two"]
