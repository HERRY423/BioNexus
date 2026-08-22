"""Contract tests for the BioNexus Scientific Semantic Conventions.

These tests establish software interoperability behavior only. They do not
constitute empirical calibration or evidence of external ecosystem adoption.
"""

from __future__ import annotations

import copy
import hashlib
import json

import pytest

from bionexus.contracts import ConclusionMaturity
from bionexus.scientific_semantics import (
    ScientificSemanticEnvelope,
    ScientificSemanticError,
    ScientificSemanticRegistry,
    SemanticValidationMode,
    default_scientific_semantic_registry,
    matrix_state_from_legacy,
    warrant_semantics_from_maturity,
)


def _observation_attributes() -> dict[str, object]:
    return {
        "biological.unit": "cell",
        "matrix.state": "log_normalized",
        "claim.type": "associative",
        "evidence.type": ["computational_result"],
        "confound.type": ["segmentation", "transcript_leakage"],
        "warrant.level": "fragile",
        "warrant.status": "assessed",
    }


def _fingerprint(payload_without_fingerprint: dict[str, object]) -> str:
    raw = json.dumps(payload_without_fingerprint, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(raw).hexdigest()


def test_registry_has_versioned_groups_and_orthogonal_warrant_status() -> None:
    registry = default_scientific_semantic_registry()
    inventory = registry.inventory()

    assert inventory["schema_version"] == "0.1.0"
    assert inventory["stability"] == "development"
    assert inventory["groups"] == ["scientific.claim", "scientific.dataset", "scientific.observation"]
    assert "warrant.level" in inventory["attributes"]
    assert "warrant.status" in inventory["attributes"]
    assert len(inventory["registry_sha256"]) == 64


def test_producer_normalizes_safe_aliases_and_fingerprint_is_deterministic() -> None:
    attributes = _observation_attributes()
    attributes.pop("biological.unit")
    attributes["biological_unit"] = "cell"
    attributes["claim.type"] = "association"
    attributes["confound.type"] = ["transcript_leakage", "segmentation", "segmentation"]

    first = ScientificSemanticEnvelope.create(
        "scientific.observation", "test.producer", attributes, record_id="record-1"
    )
    second = ScientificSemanticEnvelope.create(
        "scientific.observation", "test.producer", dict(reversed(list(attributes.items()))), record_id="record-1"
    )

    assert first.attributes["biological.unit"] == "cell"
    assert first.attributes["claim.type"] == "associative"
    assert first.attributes["confound.type"] == ["segmentation", "transcript_leakage"]
    assert first.semantic_fingerprint_sha256 == second.semantic_fingerprint_sha256


def test_producer_rejects_unknown_values_but_consumer_preserves_future_value() -> None:
    registry = default_scientific_semantic_registry()
    attributes = _observation_attributes()
    attributes["claim.type"] = "future_claim_family"

    producer = registry.validate_attributes("scientific.observation", attributes, mode=SemanticValidationMode.PRODUCER)
    consumer = registry.validate_attributes("scientific.observation", attributes, mode=SemanticValidationMode.CONSUMER)

    assert not producer.valid
    assert any("unknown value" in error for error in producer.errors)
    assert consumer.valid
    assert consumer.normalized_attributes["claim.type"] == "future_claim_family"
    assert any("future value" in warning for warning in consumer.warnings)


def test_extension_namespace_is_bounded() -> None:
    registry = default_scientific_semantic_registry()
    attributes = _observation_attributes()
    attributes["x.acme.assay_panel"] = "panel-v2"
    accepted = registry.validate_attributes("scientific.observation", attributes)
    assert accepted.valid
    assert accepted.normalized_attributes["x.acme.assay_panel"] == "panel-v2"

    attributes["acme.assay_panel"] = "unowned-name"
    rejected = registry.validate_attributes("scientific.observation", attributes)
    assert not rejected.valid
    assert any("x.<vendor>" in error for error in rejected.errors)


def test_ambiguous_matrix_state_and_conflicting_alias_fail_closed() -> None:
    registry = default_scientific_semantic_registry()
    attributes = _observation_attributes()
    attributes["matrix.state"] = "normalized_expression"
    report = registry.validate_attributes("scientific.observation", attributes)
    assert not report.valid
    assert any("ambiguous" in error.lower() for error in report.errors)

    attributes = _observation_attributes()
    attributes["biological_unit"] = "spot"
    report = registry.validate_attributes("scientific.observation", attributes)
    assert not report.valid
    assert any("conflicting values" in error for error in report.errors)

    with pytest.raises(ScientificSemanticError, match="ambiguous"):
        matrix_state_from_legacy("normalized_expression")


def test_required_is_error_and_recommended_is_warning() -> None:
    registry = default_scientific_semantic_registry()
    report = registry.validate_attributes(
        "scientific.claim",
        {
            "claim.type": "descriptive",
            "evidence.type": ["literature_support"],
            "warrant.level": "preliminary",
            "warrant.status": "assessed",
        },
    )

    assert report.valid
    assert "missing recommended attribute: biological.unit" in report.warnings
    assert "missing recommended attribute: confound.type" in report.warnings

    missing = registry.validate_attributes("scientific.claim", {"claim.type": "descriptive"})
    assert not missing.valid
    assert "missing required attribute: evidence.type" in missing.errors


@pytest.mark.parametrize(
    ("maturity", "expected"),
    [
        (ConclusionMaturity.ABSTAIN, ("unassessed", "abstained")),
        (ConclusionMaturity.CONFLICTED, ("fragile", "conflicted")),
        (ConclusionMaturity.ROBUST, ("robust", "assessed")),
    ],
)
def test_warrant_mapping_does_not_collapse_status_into_strength(
    maturity: ConclusionMaturity, expected: tuple[str, str]
) -> None:
    assert warrant_semantics_from_maturity(maturity) == expected


def test_registry_compatibility_allows_additions_and_detects_breaking_changes() -> None:
    previous = default_scientific_semantic_registry()
    additive_document = copy.deepcopy(previous.document)
    additive_document["schema_version"] = "0.2.0"
    additive_document["schema_url"] = "urn:bionexus:scientific-semantic-conventions:0.2.0"
    additive_document["attributes"]["claim.type"]["values"].append("prognostic")
    additive = ScientificSemanticRegistry(additive_document)

    additive_report = additive.compare_to(previous)
    assert additive_report.compatible
    assert "added value claim.type=prognostic" in additive_report.additions

    breaking_document = copy.deepcopy(additive_document)
    breaking_document["schema_version"] = "0.3.0"
    breaking_document["schema_url"] = "urn:bionexus:scientific-semantic-conventions:0.3.0"
    breaking_document["attributes"]["claim.type"]["values"].remove("causal")
    breaking_document["groups"]["scientific.dataset"]["attributes"]["matrix.state"] = "required"
    breaking = ScientificSemanticRegistry(breaking_document)

    breaking_report = breaking.compare_to(previous)
    assert not breaking_report.compatible
    assert "removed value claim.type=causal" in breaking_report.breaking_changes
    assert "made scientific.dataset.matrix.state required" in breaking_report.breaking_changes


def test_envelope_schema_and_content_fingerprint_are_verified() -> None:
    envelope = ScientificSemanticEnvelope.create(
        "scientific.observation", "test.producer", _observation_attributes(), record_id="record-2"
    )
    restored, report = ScientificSemanticEnvelope.from_dict(envelope.to_dict())
    assert report.valid
    assert restored == envelope

    tampered = envelope.to_dict()
    tampered["attributes"]["warrant.level"] = "robust"
    with pytest.raises(ScientificSemanticError, match="fingerprint"):
        ScientificSemanticEnvelope.from_dict(tampered)


def test_consumer_envelope_can_preserve_unknown_enum_with_valid_fingerprint() -> None:
    envelope = ScientificSemanticEnvelope.create(
        "scientific.observation", "test.producer", _observation_attributes(), record_id="record-3"
    ).to_dict()
    envelope["attributes"]["claim.type"] = "future_claim_family"
    payload = {key: value for key, value in envelope.items() if key != "semantic_fingerprint_sha256"}
    envelope["semantic_fingerprint_sha256"] = _fingerprint(payload)

    restored, report = ScientificSemanticEnvelope.from_dict(envelope)
    assert restored.attributes["claim.type"] == "future_claim_family"
    assert any("future value" in warning for warning in report.warnings)
