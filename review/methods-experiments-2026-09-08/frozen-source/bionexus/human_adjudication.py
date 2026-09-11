"""Human-owned scientific adjudication bound to a frozen assessment.

BioNexus validates record integrity and non-bypassable boundaries.  It does
not choose the decision, infer that an identity is human, or change the
scientific warrant.  A valid record is therefore evidence of a declared,
content-bound decision process -- not proof that the decision is scientifically
correct or that the signer is independently authenticated.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Mapping, Sequence, Tuple

HUMAN_ADJUDICATION_SCHEMA_VERSION = "bionexus.human-scientific-adjudication.v1"


class HumanScientificDecision(str, Enum):
    """Human workflow decisions; none of them upgrades evidence maturity."""

    ACCEPT_FOR_EXPLORATION = "ACCEPT_FOR_EXPLORATION"
    ACCEPT_WITH_LIMITS = "ACCEPT_WITH_LIMITS"
    DEFER_PENDING_EVIDENCE = "DEFER_PENDING_EVIDENCE"
    REJECT = "REJECT"


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _assessment_dict(assessment: Any) -> Dict[str, Any]:
    if hasattr(assessment, "to_dict"):
        value = assessment.to_dict()
    elif isinstance(assessment, Mapping):
        value = dict(assessment)
    else:
        raise TypeError("assessment must expose to_dict() or be a mapping")
    if not isinstance(value, dict):
        raise TypeError("assessment serialization must be a mapping")
    return value


def assessment_sha256(assessment: Any) -> str:
    """Hash the complete assessment that the human reviewed."""

    return _canonical_sha256(_assessment_dict(assessment))


@dataclass(frozen=True)
class HumanScientificAdjudication:
    """A named human's decision over one exact assessment snapshot."""

    schema_version: str
    claim_id: str
    decision: str
    decision_owner_id: str
    adjudicator_id: str
    decided_at: str
    rationale: str
    intended_use: str
    assessment_sha256: str
    human_attestation: bool
    acknowledges_evidence_limits: bool
    addressed_contradiction_ids: Tuple[str, ...] = ()
    conditions: Tuple[str, ...] = ()
    decision_receipt_sha256: str = ""

    @classmethod
    def create(
        cls,
        *,
        claim_id: str,
        decision: str,
        decision_owner_id: str,
        adjudicator_id: str,
        decided_at: str,
        rationale: str,
        intended_use: str,
        assessment_sha256: str,
        human_attestation: bool,
        acknowledges_evidence_limits: bool,
        addressed_contradiction_ids: Sequence[str] = (),
        conditions: Sequence[str] = (),
    ) -> "HumanScientificAdjudication":
        draft = cls(
            schema_version=HUMAN_ADJUDICATION_SCHEMA_VERSION,
            claim_id=claim_id,
            decision=decision,
            decision_owner_id=decision_owner_id,
            adjudicator_id=adjudicator_id,
            decided_at=decided_at,
            rationale=rationale,
            intended_use=intended_use,
            assessment_sha256=assessment_sha256,
            human_attestation=human_attestation,
            acknowledges_evidence_limits=acknowledges_evidence_limits,
            addressed_contradiction_ids=tuple(addressed_contradiction_ids),
            conditions=tuple(conditions),
        )
        return replace(draft, decision_receipt_sha256=draft.expected_receipt_sha256())

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "HumanScientificAdjudication":
        data = dict(value)
        data["addressed_contradiction_ids"] = tuple(data.get("addressed_contradiction_ids") or ())
        data["conditions"] = tuple(data.get("conditions") or ())
        return cls(**data)

    def receipt_payload(self) -> Dict[str, Any]:
        value = asdict(self)
        value.pop("decision_receipt_sha256", None)
        return value

    def expected_receipt_sha256(self) -> str:
        return _canonical_sha256(self.receipt_payload())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HumanAdjudicationResult:
    """Validation result that preserves the machine-assessed evidence boundary."""

    status: str
    final_decision: str
    human_decision_required: bool
    errors: Tuple[str, ...]
    warnings: Tuple[str, ...]
    decision_owner_id: str
    assessment_sha256: str
    decision_receipt_sha256: str
    preserved_conclusion_maturity: str
    preserved_warrant: Dict[str, Any]
    assessment_audit_status: str
    adjudication: Dict[str, Any]
    machine_role: str = "record_integrity_and_boundary_validation_only"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _declared(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _timezone_aware(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _obviously_automated_identity(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith(("ai:", "agent:", "model:")) or normalized in {
        "bionexus",
        "gpt",
        "chatgpt",
    }


def adjudicate_ecosystem_claim(
    assessment: Any,
    adjudication: HumanScientificAdjudication,
) -> HumanAdjudicationResult:
    """Validate a human decision without changing the underlying warrant."""

    snapshot = _assessment_dict(assessment)
    expected_assessment_sha = _canonical_sha256(snapshot)
    errors = []
    warnings = [
        "Human adjudication does not promote conclusion maturity or rewrite the warrant.",
        "The content digest detects mutation but does not authenticate real-world identity or authority.",
    ]

    if adjudication.schema_version != HUMAN_ADJUDICATION_SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {adjudication.schema_version!r}")
    try:
        decision = HumanScientificDecision(adjudication.decision)
    except ValueError:
        decision = None
        errors.append(f"unsupported human decision: {adjudication.decision!r}")

    claim_id = str(snapshot.get("claim_id", ""))
    decision_owner = str(snapshot.get("decision_owner", ""))
    if adjudication.claim_id != claim_id:
        errors.append("adjudication claim_id does not match the assessed claim")
    if not _declared(adjudication.decision_owner_id):
        errors.append("a named decision_owner_id is required")
    elif adjudication.decision_owner_id != decision_owner:
        errors.append("decision_owner_id does not match the owner frozen in the assessment")
    if not _declared(adjudication.adjudicator_id):
        errors.append("a named adjudicator_id is required")
    if not adjudication.human_attestation:
        errors.append("human_attestation must be explicitly true")
    if _obviously_automated_identity(adjudication.decision_owner_id) or _obviously_automated_identity(
        adjudication.adjudicator_id
    ):
        errors.append("an AI/model identity cannot be the scientific decision owner or adjudicator")
    if not _timezone_aware(adjudication.decided_at):
        errors.append("decided_at must be an ISO-8601 timestamp with timezone")
    if not _declared(adjudication.rationale):
        errors.append("a scientific rationale is required")
    if adjudication.assessment_sha256 != expected_assessment_sha:
        errors.append("assessment_sha256 does not match the exact assessment under review")
    if adjudication.decision_receipt_sha256 != adjudication.expected_receipt_sha256():
        errors.append("decision_receipt_sha256 does not match the adjudication record")

    audit = snapshot.get("audit") or {}
    audit_status = str(audit.get("status", ""))
    acceptance_decisions = {
        HumanScientificDecision.ACCEPT_FOR_EXPLORATION,
        HumanScientificDecision.ACCEPT_WITH_LIMITS,
    }
    if decision in acceptance_decisions:
        if audit_status == "BLOCKED":
            errors.append("a structurally BLOCKED assessment cannot be accepted by adjudication")
        if not _declared(adjudication.intended_use):
            errors.append("accepted work requires a declared intended_use")
        if not adjudication.acknowledges_evidence_limits:
            errors.append("accepted work must explicitly acknowledge the frozen evidence limits")
        if decision is HumanScientificDecision.ACCEPT_WITH_LIMITS and not adjudication.conditions:
            errors.append("ACCEPT_WITH_LIMITS requires at least one explicit condition")

    ledger = snapshot.get("ledger") or {}
    claim = (ledger.get("claims") or {}).get(claim_id) or {}
    contradictions = set(claim.get("contradicted_by") or ())
    addressed = set(adjudication.addressed_contradiction_ids)
    if decision in acceptance_decisions and not contradictions.issubset(addressed):
        errors.append(
            "accepted work must explicitly address every contradicted evidence id: "
            f"{sorted(contradictions - addressed)}"
        )

    status = "VALID" if not errors else "INVALID"
    final_decision = adjudication.decision if not errors else "PENDING_HUMAN_DECISION"
    return HumanAdjudicationResult(
        status=status,
        final_decision=final_decision,
        human_decision_required=bool(errors),
        errors=tuple(errors),
        warnings=tuple(warnings),
        decision_owner_id=adjudication.decision_owner_id,
        assessment_sha256=expected_assessment_sha,
        decision_receipt_sha256=adjudication.decision_receipt_sha256,
        preserved_conclusion_maturity=str(snapshot.get("conclusion_maturity", "")),
        preserved_warrant=dict(snapshot.get("warrant") or {}),
        assessment_audit_status=audit_status,
        adjudication=adjudication.to_dict(),
    )
