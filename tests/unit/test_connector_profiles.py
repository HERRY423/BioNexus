"""Tests for Community Connector Profiles and Scientific Contracts."""

from __future__ import annotations

import json

import jsonschema

from bionexus.connector_profile import (
    DEFAULT_PROFILES_DIR,
    audit_envelope_against_profile,
    list_connector_profiles,
    load_connector_profile,
)
from bionexus.ecosystem_intake import (
    ExternalCapabilityFamily,
    ExternalEvidenceEnvelope,
    ExternalProducerIdentity,
)


def test_all_connector_profiles_conform_to_schema() -> None:
    schema_path = (
        DEFAULT_PROFILES_DIR.parent / "schemas" / "connector-profile.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))

    profiles = list_connector_profiles()
    assert len(profiles) >= 7

    for name, profile in profiles.items():
        # Validate against JSON schema
        jsonschema.validate(instance=profile.to_dict(), schema=schema)


def test_enrichr_profile_scientific_contract() -> None:
    enrichr = load_connector_profile("enrichr")
    assert enrichr.connector == "enrichr"
    assert enrichr.tool == "enrich_gene_set"
    assert enrichr.production_mode == "computational_inference"
    assert enrichr.default_evidence_role == "supporting"
    assert enrichr.maximum_default_claim == "pathway_association"
    assert "causal_mechanism" in enrichr.forbidden_claims
    assert "pathway_activation_proven" in enrichr.forbidden_claims
    assert "clinical_actionability" in enrichr.forbidden_claims


def test_enrichr_audit_rejects_forbidden_claims() -> None:
    enrichr = load_connector_profile("enrichr")

    envelope = ExternalEvidenceEnvelope.create(
        evidence_id="ENV-ENRICHR-1",
        family=ExternalCapabilityFamily.ANALYSIS,
        producer=ExternalProducerIdentity(
            plugin_id="enrichr-plugin",
            capability="gene_set_enrichment",
            tool_name="enrich_gene_set",
        ),
        source_context={
            "library": "KEGG_2021_Human",
            "library_version": "2021",
            "input_gene_set_sha256": "a" * 64,
            "background_definition": "whole_genome",
            "multiple_testing_method": "benjamini_hochberg",
        },
        payload={"enriched_terms": [{"term": "p53 signaling", "p_value": 1e-5}]},
    )

    # Valid associative claim
    valid_res = audit_envelope_against_profile(
        envelope, enrichr, asserted_claim="pathway_association with p53 signaling"
    )
    assert valid_res.valid is True
    assert valid_res.errors == ()
    assert valid_res.derived_semantic_profile["claim.type"] == "associative"
    assert "computational_result" in valid_res.derived_semantic_profile["evidence.type"]

    # Forbidden causal claim
    invalid_res = audit_envelope_against_profile(
        envelope, enrichr, asserted_claim="causal_mechanism of p53 activation"
    )
    assert invalid_res.valid is False
    assert any("Forbidden claim violation" in err for err in invalid_res.errors)


def test_audit_detects_missing_required_context() -> None:
    chembl = load_connector_profile("chembl")

    # Missing database_release and identifier_namespace
    envelope = ExternalEvidenceEnvelope.create(
        evidence_id="ENV-CHEMBL-INCOMPLETE",
        family=ExternalCapabilityFamily.DATABASE,
        producer=ExternalProducerIdentity(
            plugin_id="chembl-plugin",
            capability="bioactivity_lookup",
            tool_name="query_chembl",
        ),
        source_context={
            "source_name": "ChEMBL",
            "record_ids": ["CHEMBL123"],
            "organism_taxon": "NCBI:9606",
        },
        payload={"ki": 10},
    )

    result = audit_envelope_against_profile(envelope, chembl)
    assert result.valid is False
    assert any("database_release" in err for err in result.errors)
    assert any("identifier_namespace" in err for err in result.errors)
