"""Unit tests for BioNexus Universal Connector Profile Engine (BNS-025)."""

from __future__ import annotations

from bionexus.connector_profile import (
    EvidenceProductionMode,
    ScientificDomain,
    audit_connector_claim,
    get_connector_profile,
    list_connector_profiles,
)


def test_taxonomy_domains_and_modes():
    """Verify that domain and mode dimensions are decoupled and cover BNS-025 scope."""
    # Check domain coverage
    domains = {d.value for d in ScientificDomain}
    expected_domains = {
        "literature",
        "chemistry",
        "genomics",
        "functional_genomics",
        "transcriptomics",
        "pathology",
        "clinical",
        "regulatory",
        "lab_record",
        "structure",
        "communication",
    }
    assert expected_domains.issubset(domains)

    # Check mode coverage
    modes = {m.value for m in EvidenceProductionMode}
    expected_modes = {
        "retrieval",
        "observation",
        "experiment",
        "statistical_analysis",
        "computational_inference",
        "model_prediction",
        "generative_model",
        "workflow_execution",
        "human_annotation",
        "synthesis",
    }
    assert expected_modes.issubset(modes)


def test_canonical_connector_profiles_registered():
    """Verify that all canonical connectors from the BNS-025 specification are registered."""
    profiles = list_connector_profiles()
    assert len(profiles) >= 13

    # 1. PubMed
    pubmed = get_connector_profile("pubmed")
    assert pubmed is not None
    assert pubmed.domain == ScientificDomain.LITERATURE
    assert pubmed.production_mode == EvidenceProductionMode.RETRIEVAL
    assert pubmed.default_max_claim_maturity == "PRELIMINARY"

    # 2. Consensus
    consensus = get_connector_profile("consensus")
    assert consensus is not None
    assert consensus.domain == ScientificDomain.LITERATURE
    assert consensus.production_mode == EvidenceProductionMode.SYNTHESIS

    # 3. ChEMBL
    chembl = get_connector_profile("chembl")
    assert chembl is not None
    assert chembl.domain == ScientificDomain.CHEMISTRY
    assert chembl.production_mode == EvidenceProductionMode.EXPERIMENT
    assert chembl.default_max_claim_maturity == "SUPPORTED"

    # 4. Enrichr
    enrichr = get_connector_profile("enrichr")
    assert enrichr is not None
    assert enrichr.domain == ScientificDomain.FUNCTIONAL_GENOMICS
    assert enrichr.production_mode == EvidenceProductionMode.COMPUTATIONAL_INFERENCE

    # 5. Owkin
    owkin = get_connector_profile("owkin")
    assert owkin is not None
    assert owkin.domain == ScientificDomain.PATHOLOGY
    assert owkin.production_mode == EvidenceProductionMode.STATISTICAL_ANALYSIS
    assert owkin.default_max_claim_maturity == "SUPPORTED"

    # 6. Synthesize Bio
    syn_bio = get_connector_profile("synthesize_bio")
    assert syn_bio is not None
    assert syn_bio.domain == ScientificDomain.TRANSCRIPTOMICS
    assert syn_bio.production_mode == EvidenceProductionMode.MODEL_PREDICTION
    assert syn_bio.default_max_claim_maturity == "PRELIMINARY"

    # 7. EDEN
    eden = get_connector_profile("eden")
    assert eden is not None
    assert eden.domain == ScientificDomain.CHEMISTRY
    assert eden.production_mode == EvidenceProductionMode.GENERATIVE_MODEL

    # 8. Inductive Bio
    inductive = get_connector_profile("inductive_bio")
    assert inductive is not None
    assert inductive.domain == ScientificDomain.CHEMISTRY
    assert inductive.production_mode == EvidenceProductionMode.MODEL_PREDICTION

    # 9. LatchBio
    latch = get_connector_profile("latchbio")
    assert latch is not None
    assert latch.domain == ScientificDomain.GENOMICS
    assert latch.production_mode == EvidenceProductionMode.WORKFLOW_EXECUTION

    # 10. Scispot & Revvity
    scispot = get_connector_profile("scispot")
    assert scispot is not None
    assert scispot.domain == ScientificDomain.LAB_RECORD
    assert scispot.production_mode == EvidenceProductionMode.OBSERVATION

    # 11. Dalea
    dalea = get_connector_profile("dalea")
    assert dalea is not None
    assert dalea.domain == ScientificDomain.LAB_RECORD
    assert dalea.production_mode == EvidenceProductionMode.HUMAN_ANNOTATION

    # 12. Cortellis
    cortellis = get_connector_profile("cortellis")
    assert cortellis is not None
    assert cortellis.domain == ScientificDomain.REGULATORY
    assert cortellis.production_mode == EvidenceProductionMode.RETRIEVAL

    # 13. BioRender
    biorender = get_connector_profile("biorender")
    assert biorender is not None
    assert biorender.domain == ScientificDomain.COMMUNICATION
    assert biorender.allows_scientific_evidence is False


def test_biorender_strictly_prohibited_from_scientific_claims():
    """BioRender produces communication illustrations and cannot serve as scientific evidence."""
    profile = get_connector_profile("biorender")
    assert profile is not None

    w_ok, adj_mat, reasons = audit_connector_claim(
        profile,
        target_claim_statement="The pathway diagram illustrates activation of mTORC1.",
        claimed_maturity="PRELIMINARY",
    )
    assert w_ok is False
    assert adj_mat == "UNASSESSED"
    assert any("communication artifacts only" in r for r in reasons)


def test_synthesize_bio_in_silico_ceiling_enforced():
    """Predictive models cannot claim in-vivo validation or exceed PRELIMINARY."""
    profile = get_connector_profile("synthesize_bio")
    assert profile is not None

    # 1. Attempting to claim SUPPORTED without empirical replication -> capped at PRELIMINARY
    w_ok, adj_mat, reasons = audit_connector_claim(
        profile,
        target_claim_statement="Perturbation of gene X predicts downregulation of pathway Y.",
        claimed_maturity="SUPPORTED",
    )
    assert w_ok is False
    assert adj_mat == "PRELIMINARY"
    assert any("exceeds connector 'synthesize_bio' epistemic ceiling" in r for r in reasons)

    # 2. Attempting to claim in-vivo validation -> capped at FRAGILE
    w_ok_invivo, adj_mat_invivo, reasons_invivo = audit_connector_claim(
        profile,
        target_claim_statement="We have proven in vivo validation of the compound efficacy.",
        claimed_maturity="PRELIMINARY",
    )
    assert w_ok_invivo is False
    assert adj_mat_invivo == "FRAGILE"
    assert any("prohibited inference" in r for r in reasons_invivo)


def test_owkin_prohibits_mechanistic_causality():
    """Cohort prognostic associations cannot claim direct mechanistic causality without perturbation."""
    profile = get_connector_profile("owkin")
    assert profile is not None

    w_ok, adj_mat, reasons = audit_connector_claim(
        profile,
        target_claim_statement="The tissue feature directly causes patient relapse.",
        claimed_maturity="SUPPORTED",
    )
    assert w_ok is False
    assert adj_mat == "FRAGILE"
    assert any("mechanistic_causality" in r for r in reasons)
