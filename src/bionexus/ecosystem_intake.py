"""Passive intake contract for evidence produced by external science tools.

BioNexus does not select or invoke the producer.  A host supplies an envelope
after a Literature, Database, NGS, Sequence, Structure, or Slide capability has
returned a result.  This module checks content integrity and the minimum
source-specific context needed to interpret that result without silently
promoting retrieval or inspection into scientific validation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

from bionexus.contracts import ConclusionMaturity
from bionexus.ledger import EvidenceRef

EXTERNAL_EVIDENCE_SCHEMA_VERSION = "bionexus.external-evidence-envelope.v1"


class ExternalCapabilityFamily(str, Enum):
    LITERATURE = "literature"
    DATABASE = "database"
    ANALYSIS = "analysis"
    SEQUENCE = "sequence"
    STRUCTURE = "structure"
    SLIDE = "slide"


class IntakeStatus(str, Enum):
    VALID = "VALID"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"


_REQUIRED_SOURCE_CONTEXT: Dict[ExternalCapabilityFamily, Tuple[str, ...]] = {
    ExternalCapabilityFamily.LITERATURE: (
        "source_name",
        "identifiers",
        "publication_status",
        "study_design",
    ),
    ExternalCapabilityFamily.DATABASE: (
        "source_name",
        "record_ids",
        "database_release",
        "identifier_namespace",
        "organism_taxon",
    ),
    ExternalCapabilityFamily.ANALYSIS: (
        "backend_name",
        "backend_version",
        "input_artifact_sha256",
        "parameters_sha256",
        "execution_receipt_sha256",
    ),
    ExternalCapabilityFamily.SEQUENCE: (
        "sequence_accession",
        "sequence_version",
        "sequence_sha256",
        "coordinate_system",
    ),
    ExternalCapabilityFamily.STRUCTURE: (
        "structure_id",
        "structure_source",
        "structure_version",
        "residue_mapping",
        "model_quality_context",
    ),
    ExternalCapabilityFamily.SLIDE: (
        "image_or_dataset_sha256",
        "coordinate_system",
        "coordinate_transform",
        "segmentation_version",
        "biological_replicate_ids",
        "field_of_view_ids",
    ),
}

_PROHIBITED_INFERENCES: Dict[ExternalCapabilityFamily, Tuple[str, ...]] = {
    ExternalCapabilityFamily.LITERATURE: (
        "Do not infer consensus, replication, or absence of evidence from one search result.",
        "Do not treat an author's mechanistic interpretation as independently validated causality.",
    ),
    ExternalCapabilityFamily.DATABASE: (
        "Do not treat database retrieval as independent experimental validation.",
        "Do not infer causality or clinical actionability from a structured record alone.",
    ),
    ExternalCapabilityFamily.ANALYSIS: (
        "Do not infer biological generalization from execution success alone.",
        "Do not infer causality without an identified design and causal assumptions.",
    ),
    ExternalCapabilityFamily.SEQUENCE: (
        "Do not infer molecular function, pathogenicity, or phenotype from sequence position alone.",
    ),
    ExternalCapabilityFamily.STRUCTURE: (
        "Do not infer altered binding affinity or causal drug resistance from geometric proximity alone.",
    ),
    ExternalCapabilityFamily.SLIDE: (
        "Do not infer robust enrichment or attraction mechanisms from visual colocalization alone.",
        "Do not ignore segmentation, density, field, patient, or coordinate-transform effects.",
    ),
}

_CONTEXT_USE: Dict[ExternalCapabilityFamily, str] = {
    ExternalCapabilityFamily.LITERATURE: "source-specific literature report",
    ExternalCapabilityFamily.DATABASE: "versioned database record",
    ExternalCapabilityFamily.ANALYSIS: "content-bound analysis result",
    ExternalCapabilityFamily.SEQUENCE: "sequence-coordinate observation",
    ExternalCapabilityFamily.STRUCTURE: "structure-coordinate observation",
    ExternalCapabilityFamily.SLIDE: "image/spatial observation",
}

_SHA256_CONTEXT_FIELDS = {
    "input_artifact_sha256",
    "parameters_sha256",
    "execution_receipt_sha256",
    "sequence_sha256",
    "image_or_dataset_sha256",
}


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _is_declared(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return value.strip().lower() not in {"", "unknown", "unspecified", "not_provided", "n/a"}
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


@dataclass(frozen=True)
class ExternalProducerIdentity:
    """Declared producer identity; declaration is not authentication."""

    plugin_id: str
    capability: str
    tool_name: str
    plugin_version: Optional[str] = None


@dataclass(frozen=True)
class ExternalEvidenceEnvelope:
    schema_version: str
    evidence_id: str
    family: str
    producer: ExternalProducerIdentity
    captured_at: str
    source_context: Dict[str, Any]
    payload: Any
    payload_sha256: str
    request_sha256: Optional[str] = None
    semantic_envelope: Optional[Dict[str, Any]] = None
    epistemic_lineage: Optional[Dict[str, Any]] = None

    @classmethod
    def create(
        cls,
        *,
        evidence_id: str,
        family: ExternalCapabilityFamily | str,
        producer: ExternalProducerIdentity,
        source_context: Mapping[str, Any],
        payload: Any,
        request: Any = None,
        captured_at: Optional[str] = None,
        semantic_envelope: Optional[Mapping[str, Any]] = None,
        epistemic_lineage: Optional[Mapping[str, Any]] = None,
    ) -> "ExternalEvidenceEnvelope":
        family_value = family.value if isinstance(family, ExternalCapabilityFamily) else str(family)
        return cls(
            schema_version=EXTERNAL_EVIDENCE_SCHEMA_VERSION,
            evidence_id=evidence_id,
            family=family_value,
            producer=producer,
            captured_at=captured_at or datetime.now(timezone.utc).isoformat(),
            source_context=dict(source_context),
            payload=payload,
            payload_sha256=_sha256(payload),
            request_sha256=_sha256(request) if request is not None else None,
            semantic_envelope=dict(semantic_envelope) if semantic_envelope is not None else None,
            epistemic_lineage=dict(epistemic_lineage) if epistemic_lineage is not None else None,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExternalEvidenceEnvelope":
        data = dict(value)
        producer = data.get("producer")
        if not isinstance(producer, Mapping):
            raise ValueError("producer must be an object")
        data["producer"] = ExternalProducerIdentity(**dict(producer))
        data["source_context"] = dict(data.get("source_context") or {})
        if data.get("epistemic_lineage") is not None:
            data["epistemic_lineage"] = dict(data["epistemic_lineage"])
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExternalEvidenceAudit:
    evidence_id: str
    status: str
    integrity_verified: bool
    producer_identity_status: str
    accepted_for_context: bool
    accepted_for_claim_support: bool
    conclusion_maturity: str
    allowed_context_use: str
    missing_context: Tuple[str, ...]
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]
    prohibited_inferences: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def audit_external_evidence(envelope: ExternalEvidenceEnvelope) -> ExternalEvidenceAudit:
    """Validate one host-supplied result without assigning scientific warrant."""

    errors = []
    warnings = []
    missing = []

    if envelope.schema_version != EXTERNAL_EVIDENCE_SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {envelope.schema_version!r}")
    if not _is_declared(envelope.evidence_id):
        errors.append("evidence_id is required")
    try:
        family = ExternalCapabilityFamily(envelope.family)
    except ValueError:
        family = None
        errors.append(f"unsupported capability family: {envelope.family!r}")

    producer_values = {
        "producer.plugin_id": envelope.producer.plugin_id,
        "producer.capability": envelope.producer.capability,
        "producer.tool_name": envelope.producer.tool_name,
    }
    for field, value in producer_values.items():
        if not _is_declared(value):
            errors.append(f"{field} is required")
    if not _is_declared(envelope.producer.plugin_version):
        warnings.append("producer.plugin_version is not declared; producer identity remains version-incomplete")

    try:
        captured = datetime.fromisoformat(envelope.captured_at.replace("Z", "+00:00"))
        if captured.tzinfo is None:
            errors.append("captured_at must include an explicit timezone")
    except (AttributeError, ValueError):
        errors.append("captured_at must be an ISO-8601 timestamp")

    try:
        actual_payload_sha256 = _sha256(envelope.payload)
    except (TypeError, ValueError) as exc:
        actual_payload_sha256 = ""
        errors.append(f"payload is not canonical JSON: {exc}")
    integrity_verified = bool(actual_payload_sha256) and actual_payload_sha256 == envelope.payload_sha256
    if not integrity_verified:
        errors.append("payload_sha256 does not match the canonical payload bytes")

    if family is not None:
        for field in _REQUIRED_SOURCE_CONTEXT[family]:
            value = envelope.source_context.get(field)
            if not _is_declared(value):
                missing.append(field)
            elif field in _SHA256_CONTEXT_FIELDS and not _is_sha256(value):
                errors.append(f"source_context.{field} must be a 64-character SHA-256")

    if envelope.request_sha256 is None:
        warnings.append("request_sha256 is absent; the result is not bound to the originating query/request")
    elif not _is_sha256(envelope.request_sha256):
        errors.append("request_sha256 must be a 64-character SHA-256")

    if envelope.semantic_envelope is not None:
        try:
            from bionexus.scientific_semantics import ScientificSemanticEnvelope

            ScientificSemanticEnvelope.from_dict(envelope.semantic_envelope)
        except Exception as exc:
            errors.append(f"semantic_envelope failed BNS-019 validation: {exc}")

    if errors:
        status = IntakeStatus.INVALID
    elif missing:
        status = IntakeStatus.INCOMPLETE
    else:
        status = IntakeStatus.VALID

    allowed_use = _CONTEXT_USE.get(family, "none")
    prohibited = _PROHIBITED_INFERENCES.get(family, ("Do not use an unknown capability family for claims.",))
    return ExternalEvidenceAudit(
        evidence_id=envelope.evidence_id,
        status=status.value,
        integrity_verified=integrity_verified,
        producer_identity_status="DECLARED_NOT_AUTHENTICATED" if not errors else "UNRESOLVED",
        accepted_for_context=status is IntakeStatus.VALID,
        accepted_for_claim_support=False,
        conclusion_maturity=ConclusionMaturity.UNASSESSED.value,
        allowed_context_use=allowed_use,
        missing_context=tuple(sorted(missing)),
        errors=tuple(errors),
        warnings=tuple(warnings),
        prohibited_inferences=prohibited,
    )


def external_evidence_to_ledger_ref(
    envelope: ExternalEvidenceEnvelope,
    audit: Optional[ExternalEvidenceAudit] = None,
) -> EvidenceRef:
    """Create a context-only ledger node; a separate assessment must promote it."""

    result = audit or audit_external_evidence(envelope)
    if result.status != IntakeStatus.VALID.value:
        raise ValueError(f"external evidence intake is {result.status}: {result.errors or result.missing_context}")
    family = ExternalCapabilityFamily(envelope.family)
    kind = {
        ExternalCapabilityFamily.LITERATURE: "literature",
        ExternalCapabilityFamily.DATABASE: "database",
        ExternalCapabilityFamily.ANALYSIS: "method_run",
        ExternalCapabilityFamily.SEQUENCE: "inspection",
        ExternalCapabilityFamily.STRUCTURE: "inspection",
        ExternalCapabilityFamily.SLIDE: "inspection",
    }[family]
    return EvidenceRef(
        ref_id=envelope.evidence_id,
        kind=kind,
        summary=f"External {family.value} result from {envelope.producer.plugin_id}/{envelope.producer.tool_name}",
        maturity=ConclusionMaturity.UNASSESSED.value,
        provenance={
            "external_evidence_schema": envelope.schema_version,
            "payload_sha256": envelope.payload_sha256,
            "request_sha256": envelope.request_sha256,
            "producer": asdict(envelope.producer),
            "source_context": dict(envelope.source_context),
            "epistemic_lineage": dict(envelope.epistemic_lineage) if envelope.epistemic_lineage else None,
            "intake_status": result.status,
            "identity_status": result.producer_identity_status,
        },
        validation_role="context_only",
    )
