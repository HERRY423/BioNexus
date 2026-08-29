"""Contract tests for passive cross-plugin scientific evidence intake."""

from __future__ import annotations

from dataclasses import replace

import pytest

from bionexus.ecosystem_intake import (
    ExternalCapabilityFamily,
    ExternalEvidenceEnvelope,
    ExternalProducerIdentity,
    audit_external_evidence,
    external_evidence_to_ledger_ref,
)

HEX_A = "a" * 64
HEX_B = "b" * 64
HEX_C = "c" * 64


def _producer() -> ExternalProducerIdentity:
    return ExternalProducerIdentity(
        plugin_id="life-sciences-databases",
        capability="structured_database_lookup",
        tool_name="query_uniprot",
        plugin_version="2026.08",
    )


@pytest.mark.parametrize(
    ("family", "context"),
    [
        (
            ExternalCapabilityFamily.LITERATURE,
            {
                "source_name": "PubMed",
                "identifiers": ["PMID:123"],
                "publication_status": "peer_reviewed",
                "study_design": "observational cohort",
            },
        ),
        (
            ExternalCapabilityFamily.DATABASE,
            {
                "source_name": "UniProt",
                "record_ids": ["P04637"],
                "database_release": "2026_03",
                "identifier_namespace": "UniProtKB",
                "organism_taxon": "NCBI:9606",
            },
        ),
        (
            ExternalCapabilityFamily.ANALYSIS,
            {
                "backend_name": "nf-core/rnaseq",
                "backend_version": "3.20.0",
                "input_artifact_sha256": HEX_A,
                "parameters_sha256": HEX_B,
                "execution_receipt_sha256": HEX_C,
            },
        ),
        (
            ExternalCapabilityFamily.SEQUENCE,
            {
                "sequence_accession": "NP_000537",
                "sequence_version": "3",
                "sequence_sha256": HEX_A,
                "coordinate_system": "1-based protein residues",
            },
        ),
        (
            ExternalCapabilityFamily.STRUCTURE,
            {
                "structure_id": "PDB:8ABC",
                "structure_source": "RCSB PDB",
                "structure_version": "2026-08-01",
                "residue_mapping": {"TP53:R175": "chain A:175"},
                "model_quality_context": {"method": "X-ray", "resolution_angstrom": 2.1},
            },
        ),
        (
            ExternalCapabilityFamily.SLIDE,
            {
                "image_or_dataset_sha256": HEX_A,
                "coordinate_system": "micrometers from image origin",
                "coordinate_transform": {"name": "identity", "matrix": [[1, 0, 0], [0, 1, 0]]},
                "segmentation_version": "cellpose-3.1/model-x",
                "biological_replicate_ids": ["patient-01"],
                "field_of_view_ids": ["fov-01"],
            },
        ),
    ],
)
def test_each_external_family_requires_context_but_never_mints_warrant(family, context) -> None:
    envelope = ExternalEvidenceEnvelope.create(
        evidence_id=f"EXT-{family.value}",
        family=family,
        producer=_producer(),
        source_context=context,
        payload={"result": [1, 2, 3]},
        request={"query": "TP53"},
    )

    audit = audit_external_evidence(envelope)

    assert audit.status == "VALID"
    assert audit.integrity_verified is True
    assert audit.producer_identity_status == "DECLARED_NOT_AUTHENTICATED"
    assert audit.accepted_for_context is True
    assert audit.accepted_for_claim_support is False
    assert audit.conclusion_maturity == "UNASSESSED"
    assert audit.prohibited_inferences


def test_tampered_payload_is_invalid() -> None:
    envelope = ExternalEvidenceEnvelope.create(
        evidence_id="EXT-DB-1",
        family="database",
        producer=_producer(),
        source_context={
            "source_name": "UniProt",
            "record_ids": ["P04637"],
            "database_release": "2026_03",
            "identifier_namespace": "UniProtKB",
            "organism_taxon": "NCBI:9606",
        },
        payload={"gene": "TP53"},
        request={"query": "TP53"},
    )
    tampered = replace(envelope, payload={"gene": "EGFR"})

    audit = audit_external_evidence(tampered)

    assert audit.status == "INVALID"
    assert audit.integrity_verified is False
    assert any("payload_sha256" in error for error in audit.errors)


def test_missing_family_context_fails_closed() -> None:
    envelope = ExternalEvidenceEnvelope.create(
        evidence_id="EXT-STRUCTURE-1",
        family="structure",
        producer=_producer(),
        source_context={"structure_id": "PDB:8ABC", "structure_source": "RCSB PDB"},
        payload={"distance_angstrom": 4.2},
        request={"residue": "R175"},
    )

    audit = audit_external_evidence(envelope)

    assert audit.status == "INCOMPLETE"
    assert audit.accepted_for_context is False
    assert set(audit.missing_context) == {"structure_version", "residue_mapping", "model_quality_context"}
    assert "altered binding affinity" in " ".join(audit.prohibited_inferences)
    with pytest.raises(ValueError, match="INCOMPLETE"):
        external_evidence_to_ledger_ref(envelope, audit)


def test_valid_external_result_enters_ledger_as_context_only_unassessed() -> None:
    envelope = ExternalEvidenceEnvelope.create(
        evidence_id="EXT-DB-2",
        family="database",
        producer=_producer(),
        source_context={
            "source_name": "UniProt",
            "record_ids": ["P04637"],
            "database_release": "2026_03",
            "identifier_namespace": "UniProtKB",
            "organism_taxon": "NCBI:9606",
        },
        payload={"function": "DNA-binding transcription factor"},
        request={"accession": "P04637"},
    )

    ref = external_evidence_to_ledger_ref(envelope)

    assert ref.kind == "database"
    assert ref.validation_role == "context_only"
    assert ref.maturity == "UNASSESSED"
    assert ref.qualifies_as_external_validation is False
    assert ref.provenance["payload_sha256"] == envelope.payload_sha256


def test_timestamp_and_optional_semantic_envelope_are_validated() -> None:
    envelope = ExternalEvidenceEnvelope.create(
        evidence_id="EXT-DB-3",
        family="database",
        producer=_producer(),
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

    naive_time = replace(envelope, captured_at="2026-08-28T12:00:00")
    assert audit_external_evidence(naive_time).status == "INVALID"

    malformed_semantics = replace(envelope, semantic_envelope={"schema_url": "tampered"})
    result = audit_external_evidence(malformed_semantics)
    assert result.status == "INVALID"
    assert any("BNS-019" in error for error in result.errors)
