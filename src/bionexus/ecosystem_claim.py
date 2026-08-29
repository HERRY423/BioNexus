"""Passive multi-source claim assessment for host-orchestrated science tools.

The host chooses and invokes upstream capabilities.  BioNexus receives their
completed evidence envelopes plus explicit, review-bound adjudications.  It
does not infer whether a payload supports a claim, and it never makes the
final scientific decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from bionexus.contracts import (
    ConclusionMaturity,
    DimensionGrade,
    EvidenceCard,
    ExecutionState,
)
from bionexus.ecosystem_intake import (
    ExternalEvidenceEnvelope,
    IntakeStatus,
    audit_external_evidence,
    external_evidence_to_ledger_ref,
)
from bionexus.ledger import MATURITY_RANKS, ClaimLedger, ClaimRecord, EvidenceRef

ECOSYSTEM_CLAIM_PACKET_VERSION = "bionexus.ecosystem-claim-packet.v1"
ECOSYSTEM_CLAIM_ASSESSMENT_VERSION = "bionexus.ecosystem-claim-assessment.v1"


class EvidenceRelationship(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    CONTEXT = "context"
    DEPENDS_ON = "depends_on"


class ClaimAuditStatus(str, Enum):
    PASS = "PASS"
    CONFLICTED = "CONFLICTED"
    BLOCKED = "BLOCKED"


def _is_declared(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() not in {
        "",
        "unknown",
        "unspecified",
        "not_provided",
        "n/a",
    }


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _same_value(left: Any, right: Any) -> bool:
    """Compare JSON-compatible context values without lossy string coercion."""

    return left == right


@dataclass(frozen=True)
class EvidenceAdjudication:
    """A human/review-process assertion about one evidence-to-claim edge.

    This object is a declaration bound to a receipt, not proof that the
    declared relationship is scientifically correct.
    """

    evidence_id: str
    relationship: str
    maturity: str = ConclusionMaturity.UNASSESSED.value
    rationale: str = ""
    adjudicator_id: str = ""
    adjudication_receipt_sha256: str = ""
    validation_role: str = "supporting"
    qualification: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceAdjudication":
        data = dict(value)
        data["qualification"] = dict(data.get("qualification") or {})
        return cls(**data)


@dataclass(frozen=True)
class EcosystemClaimPacket:
    schema_version: str
    claim_id: str
    statement: str
    decision_owner: str
    envelopes: Tuple[ExternalEvidenceEnvelope, ...]
    adjudications: Tuple[EvidenceAdjudication, ...]
    capability_id: Optional[str] = None
    claim_context: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EcosystemClaimPacket":
        data = dict(value)
        data["envelopes"] = tuple(
            ExternalEvidenceEnvelope.from_dict(item) for item in data.get("envelopes", ())
        )
        data["adjudications"] = tuple(
            EvidenceAdjudication.from_dict(item) for item in data.get("adjudications", ())
        )
        data["claim_context"] = dict(data.get("claim_context") or {})
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EcosystemClaimAudit:
    status: str
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]
    envelope_audits: Tuple[Dict[str, Any], ...]
    missing_adjudications: Tuple[str, ...]
    duplicate_payload_groups: Tuple[Tuple[str, ...], ...]
    context_conflicts: Tuple[Dict[str, Any], ...]
    human_decision_required: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EcosystemClaimAssessment:
    schema_version: str
    claim_id: str
    conclusion_maturity: str
    warrant: Dict[str, Any]
    audit: EcosystemClaimAudit
    evidence_card: Dict[str, Any]
    ledger: Dict[str, Any]
    decision_owner: str
    final_decision: str = "PENDING_HUMAN_DECISION"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["audit"] = self.audit.to_dict()
        return data


def _validate_adjudication(adjudication: EvidenceAdjudication) -> List[str]:
    errors: List[str] = []
    try:
        relationship = EvidenceRelationship(adjudication.relationship)
    except ValueError:
        errors.append(
            f"evidence {adjudication.evidence_id!r} has unsupported relationship "
            f"{adjudication.relationship!r}"
        )
        return errors

    if adjudication.maturity not in MATURITY_RANKS:
        errors.append(
            f"evidence {adjudication.evidence_id!r} has unknown maturity {adjudication.maturity!r}"
        )
    if relationship in {EvidenceRelationship.CONTEXT, EvidenceRelationship.DEPENDS_ON}:
        if adjudication.maturity != ConclusionMaturity.UNASSESSED.value:
            errors.append(
                f"{relationship.value} evidence {adjudication.evidence_id!r} must remain UNASSESSED"
            )
        if adjudication.validation_role != "context_only":
            errors.append(
                f"{relationship.value} evidence {adjudication.evidence_id!r} must use context_only"
            )
        return errors

    if adjudication.maturity in {
        ConclusionMaturity.UNASSESSED.value,
        ConclusionMaturity.ABSTAIN.value,
        ConclusionMaturity.CONFLICTED.value,
    }:
        errors.append(
            f"claim-bearing evidence {adjudication.evidence_id!r} requires an assessed, "
            "non-conflicted maturity"
        )
    if not _is_declared(adjudication.rationale):
        errors.append(f"claim-bearing evidence {adjudication.evidence_id!r} requires a rationale")
    if not _is_declared(adjudication.adjudicator_id):
        errors.append(f"claim-bearing evidence {adjudication.evidence_id!r} requires adjudicator_id")
    if not _is_sha256(adjudication.adjudication_receipt_sha256):
        errors.append(
            f"claim-bearing evidence {adjudication.evidence_id!r} requires adjudication_receipt_sha256"
        )
    if adjudication.validation_role == "context_only":
        errors.append(
            f"claim-bearing evidence {adjudication.evidence_id!r} cannot use context_only"
        )
    return errors


def _promote_ref(
    envelope: ExternalEvidenceEnvelope,
    adjudication: EvidenceAdjudication,
) -> EvidenceRef:
    base = external_evidence_to_ledger_ref(envelope)
    relationship = EvidenceRelationship(adjudication.relationship)
    role = (
        "context_only"
        if relationship in {EvidenceRelationship.CONTEXT, EvidenceRelationship.DEPENDS_ON}
        else adjudication.validation_role
    )
    provenance = dict(base.provenance)
    provenance.update(adjudication.qualification)
    provenance["adjudication"] = {
        "relationship": relationship.value,
        "rationale": adjudication.rationale,
        "adjudicator_id": adjudication.adjudicator_id,
        "adjudication_receipt_sha256": adjudication.adjudication_receipt_sha256,
        "status": "DECLARED_REVIEW_BOUND_NOT_INDEPENDENTLY_VERIFIED",
    }
    return EvidenceRef(
        ref_id=base.ref_id,
        kind=base.kind,
        summary=base.summary,
        maturity=adjudication.maturity,
        provenance=provenance,
        validation_role=role,
    )


def _make_evidence_card(
    *,
    audit_status: ClaimAuditStatus,
    maturity: str,
    duplicate_groups: Sequence[Tuple[str, ...]],
    context_conflicts: Sequence[Dict[str, Any]],
    errors: Sequence[str],
) -> EvidenceCard:
    if audit_status is ClaimAuditStatus.BLOCKED:
        execution_state = ExecutionState.REFUSED.value
        input_integrity = DimensionGrade.INSUFFICIENT.value
    else:
        execution_state = ExecutionState.EXECUTED.value
        input_integrity = DimensionGrade.GRADE_A.value
    concordance = (
        DimensionGrade.CONFLICTED.value
        if audit_status is ClaimAuditStatus.CONFLICTED
        else DimensionGrade.UNTESTED.value
    )
    return EvidenceCard(
        execution_state=execution_state,
        input_integrity=input_integrity,
        assumption_validity=DimensionGrade.UNTESTED.value,
        statistical_support=DimensionGrade.UNTESTED.value,
        parameter_robustness=DimensionGrade.UNTESTED.value,
        cross_method_concordance=concordance,
        external_validation=DimensionGrade.UNTESTED.value,
        evidence_ceiling=maturity,
        blocked_claims=list(errors),
        residual_limitations=[
            "Evidence-to-claim relationships are declared adjudications, not autonomous BioNexus inferences.",
            "Final scientific acceptance requires the named human decision owner.",
        ],
        details={
            "assessment_contract": ECOSYSTEM_CLAIM_ASSESSMENT_VERSION,
            "claim_conclusion_maturity": maturity,
            "duplicate_payload_groups": [list(group) for group in duplicate_groups],
            "context_conflicts": list(context_conflicts),
            "statistical_notes": "Inherited from reviewed evidence; not recomputed by this intake assessment.",
            "validation_notes": "External validation requires explicit ledger qualification.",
        },
    )


def assess_ecosystem_claim(packet: EcosystemClaimPacket) -> EcosystemClaimAssessment:
    """Build Warrant + Audit + EvidenceCard without making the final decision."""

    errors: List[str] = []
    warnings: List[str] = []
    context_conflicts: List[Dict[str, Any]] = []

    if packet.schema_version != ECOSYSTEM_CLAIM_PACKET_VERSION:
        errors.append(f"unsupported schema_version: {packet.schema_version!r}")
    if not _is_declared(packet.claim_id):
        errors.append("claim_id is required")
    if not _is_declared(packet.statement):
        errors.append("statement is required")
    if not _is_declared(packet.decision_owner):
        errors.append("a named decision_owner is required")
    if not packet.claim_context:
        warnings.append("claim_context is empty; cross-source scope alignment cannot be fully checked")
    if not packet.envelopes:
        errors.append("at least one external evidence envelope is required")

    envelope_audits = [audit_external_evidence(envelope) for envelope in packet.envelopes]
    errors.extend(
        f"evidence {result.evidence_id!r} intake is {result.status}: "
        f"{list(result.errors or result.missing_context)}"
        for result in envelope_audits
        if result.status != IntakeStatus.VALID.value
    )

    envelope_ids = [envelope.evidence_id for envelope in packet.envelopes]
    duplicate_ids = sorted({eid for eid in envelope_ids if envelope_ids.count(eid) > 1})
    if duplicate_ids:
        errors.append(f"duplicate evidence_id values: {duplicate_ids}")

    adjudication_ids = [item.evidence_id for item in packet.adjudications]
    duplicate_adjudications = sorted(
        {eid for eid in adjudication_ids if adjudication_ids.count(eid) > 1}
    )
    if duplicate_adjudications:
        errors.append(f"multiple adjudications for evidence: {duplicate_adjudications}")

    missing_adjudications = tuple(sorted(set(envelope_ids) - set(adjudication_ids)))
    if missing_adjudications:
        errors.append(f"missing explicit adjudications for evidence: {list(missing_adjudications)}")
    unknown_adjudications = sorted(set(adjudication_ids) - set(envelope_ids))
    if unknown_adjudications:
        errors.append(f"adjudications reference unknown evidence: {unknown_adjudications}")
    for adjudication in packet.adjudications:
        errors.extend(_validate_adjudication(adjudication))

    payload_groups: Dict[str, List[str]] = {}
    for envelope in packet.envelopes:
        payload_groups.setdefault(envelope.payload_sha256, []).append(envelope.evidence_id)
    duplicate_payload_groups = tuple(
        tuple(ids) for ids in payload_groups.values() if len(ids) > 1
    )
    if duplicate_payload_groups:
        warnings.append(
            "duplicate payloads are retained for provenance but count only once toward claim relationships"
        )

    for envelope in packet.envelopes:
        for key, expected in packet.claim_context.items():
            if key not in envelope.source_context:
                continue
            observed = envelope.source_context[key]
            if not _same_value(observed, expected):
                context_conflicts.append(
                    {
                        "evidence_id": envelope.evidence_id,
                        "field": key,
                        "claim_value": expected,
                        "evidence_value": observed,
                    }
                )
    if context_conflicts:
        errors.append("evidence source context conflicts with the declared claim_context")

    adjudication_by_id = {item.evidence_id: item for item in packet.adjudications}
    for group in duplicate_payload_groups:
        relationships = {
            adjudication_by_id[eid].relationship
            for eid in group
            if eid in adjudication_by_id
        }
        if EvidenceRelationship.SUPPORTS.value in relationships and EvidenceRelationship.CONTRADICTS.value in relationships:
            errors.append(f"identical payload has conflicting adjudications: {list(group)}")

    ledger = ClaimLedger()
    supported_by: List[str] = []
    contradicted_by: List[str] = []
    depends_on: List[str] = []
    seen_payload_relationships: set[Tuple[str, str]] = set()

    if not errors:
        for envelope in packet.envelopes:
            adjudication = adjudication_by_id[envelope.evidence_id]
            try:
                ref = _promote_ref(envelope, adjudication)
            except ValueError as exc:
                errors.append(f"evidence {envelope.evidence_id!r} failed qualification: {exc}")
                break
            ledger.add_evidence(ref)
            relationship = EvidenceRelationship(adjudication.relationship)
            dedupe_key = (envelope.payload_sha256, relationship.value)
            if dedupe_key in seen_payload_relationships:
                depends_on.append(ref.ref_id)
                continue
            seen_payload_relationships.add(dedupe_key)
            if relationship is EvidenceRelationship.SUPPORTS:
                supported_by.append(ref.ref_id)
            elif relationship is EvidenceRelationship.CONTRADICTS:
                contradicted_by.append(ref.ref_id)
            else:
                depends_on.append(ref.ref_id)

    if errors:
        # Do not let a partly constructed graph look claim-bearing.
        ledger = ClaimLedger()
        supported_by = []
        contradicted_by = []
        depends_on = []

    claim = ClaimRecord(
        claim_id=packet.claim_id or "UNRESOLVED-CLAIM",
        statement=packet.statement,
        capability_id=packet.capability_id,
        supported_by=supported_by,
        contradicted_by=contradicted_by,
        depends_on=depends_on,
        provenance={
            "assessment_contract": ECOSYSTEM_CLAIM_ASSESSMENT_VERSION,
            "claim_context": dict(packet.claim_context),
            "decision_owner": packet.decision_owner,
            "final_decision": "PENDING_HUMAN_DECISION",
        },
    )
    ledger.add_claim(claim)

    # ClaimLedger correctly short-circuits to ABSTAIN when support is absent.
    # Still emit a full negative warrant artifact so refusal paths are as
    # inspectable as successful paths; claim syntax itself supplies no evidence.
    if claim.warrant_evaluation is None:
        try:
            from bionexus.claim_semantics import (
                DeterministicClaimParser,
                DeterministicWarrantEngine,
                EvidenceProfile,
            )

            claim_ir = DeterministicClaimParser.parse(claim.statement, claim_id=claim.claim_id)
            claim.structured_claim = claim_ir.to_dict()
            claim.warrant_evaluation = DeterministicWarrantEngine.evaluate(
                claim_ir,
                EvidenceProfile(observational_data=False),
            ).to_dict()
        except Exception as exc:
            warnings.append(f"deterministic warrant evaluation unavailable: {exc}")

    if errors:
        audit_status = ClaimAuditStatus.BLOCKED
    elif contradicted_by:
        audit_status = ClaimAuditStatus.CONFLICTED
    else:
        audit_status = ClaimAuditStatus.PASS

    audit = EcosystemClaimAudit(
        status=audit_status.value,
        errors=tuple(errors),
        warnings=tuple(warnings),
        envelope_audits=tuple(result.to_dict() for result in envelope_audits),
        missing_adjudications=missing_adjudications,
        duplicate_payload_groups=duplicate_payload_groups,
        context_conflicts=tuple(context_conflicts),
    )
    card = _make_evidence_card(
        audit_status=audit_status,
        maturity=claim.evidence_status,
        duplicate_groups=duplicate_payload_groups,
        context_conflicts=context_conflicts,
        errors=errors,
    )
    return EcosystemClaimAssessment(
        schema_version=ECOSYSTEM_CLAIM_ASSESSMENT_VERSION,
        claim_id=claim.claim_id,
        conclusion_maturity=claim.evidence_status,
        warrant=claim.warrant_evaluation
        or {
            "claim_id": claim.claim_id,
            "is_fully_warranted": False,
            "evidence_ceiling": ConclusionMaturity.ABSTAIN.value,
            "tier_verdicts": {},
            "evidence_gaps": ["deterministic_warrant_evaluation_unavailable"],
        },
        audit=audit,
        evidence_card=card.to_dict(),
        ledger=ledger.to_dict(),
        decision_owner=packet.decision_owner,
    )
