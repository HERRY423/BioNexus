"""Calibration freeze on held-out contexts (BNS-023).

A threshold/calibration profile may only issue a positive warrant in a
context that its frozen held-out evidence actually covers.  Freezing is the
hash-locked bridge between :mod:`bionexus.empirical_warrant` (which fits
CANDIDATE profiles and requires accountable human approval before APPROVED)
and downstream warrant issuance:

1. Only an ``APPROVED`` profile whose own ``validation_issues()`` are empty
   can be frozen — an approved profile cannot be overwritten by automatic
   fitting, and freezing cannot launder an unfit profile.
2. The freeze binds the exact canonical profile hash to one or more
   **held-out contexts** (disease / tissue / platform / technology tuples
   bound to concrete dataset digests).  Freezing with no held-out context is
   refused.
3. Frozen records are immutable and independently verifiable
   (:func:`verify_freeze` recomputes the profile hash).  Any later edit of
   the profile invalidates the freeze instead of silently following it.
4. :func:`authorize_context` fail-closed gates warrant issuance: a profile
   that is not APPROVED, not frozen, frozen under a different hash, or used
   outside its frozen held-out contexts yields a non-authorizing decision.

The packaged calibration registry ships zero APPROVED profiles and the IVN
registry ships zero freezes, so nothing is authorized today — matching the
OPEN_QUESTIONS judgment that no approved empirical calibration profile
exists yet.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from bionexus.empirical_warrant import (
    CalibrationProfile,
    CalibrationReviewStatus,
    _canonical_sha256,
)

__all__ = [
    "FREEZE_SCHEMA_VERSION",
    "CalibrationFreezeError",
    "FreezeDecision",
    "HeldOutContext",
    "CalibrationFreezeRecord",
    "freeze_profile",
    "verify_freeze",
    "context_covered",
    "authorize_context",
    "load_freeze_records",
    "profile_from_payload",
]

FREEZE_SCHEMA_VERSION = "bionexus.calibration-freeze.v1"

_HEX64 = set("0123456789abcdef")


class CalibrationFreezeError(ValueError):
    """Raised when a freeze request or record violates the fail-closed rules."""


class FreezeDecision(str, Enum):
    """Outcomes of the fail-closed context authorization gate."""

    AUTHORIZED = "AUTHORIZED"
    PROFILE_NOT_APPROVED = "PROFILE_NOT_APPROVED"
    FREEZE_REQUIRED = "FREEZE_REQUIRED"
    FREEZE_MISMATCH = "FREEZE_MISMATCH"
    CONTEXT_NOT_COVERED = "CONTEXT_NOT_COVERED"
    INVALID_CONTEXT = "INVALID_CONTEXT"


@dataclass(frozen=True)
class HeldOutContext:
    """One held-out context a frozen profile is validated and bound to."""

    dataset_id: str
    dataset_sha256: str
    disease: str
    tissue: str
    platform: str
    technology: str
    partition: str = "validation"

    def __post_init__(self) -> None:
        for key in ("dataset_id", "disease", "tissue", "platform", "technology"):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip():
                raise CalibrationFreezeError(f"held-out context field '{key}' must be a non-empty string")
        if not (isinstance(self.dataset_sha256, str) and len(self.dataset_sha256) == 64
                and set(self.dataset_sha256.lower()) <= _HEX64):
            raise CalibrationFreezeError("held-out context dataset_sha256 must be 64 hex characters")
        if self.partition != "validation":
            raise CalibrationFreezeError(
                "freeze contexts must be the held-out 'validation' partition, never the calibration partition"
            )

    def fingerprint(self) -> Dict[str, str]:
        """Context identity used for coverage checks (dataset binding excluded)."""
        return {
            "disease": self.disease.strip().casefold(),
            "tissue": self.tissue.strip().casefold(),
            "platform": self.platform.strip().casefold(),
            "technology": self.technology.strip().casefold(),
        }

    def to_dict(self) -> Dict[str, str]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.dataset_sha256,
            "disease": self.disease,
            "tissue": self.tissue,
            "platform": self.platform,
            "technology": self.technology,
            "partition": self.partition,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "HeldOutContext":
        return cls(
            dataset_id=payload.get("dataset_id", ""),
            dataset_sha256=payload.get("dataset_sha256", ""),
            disease=payload.get("disease", ""),
            tissue=payload.get("tissue", ""),
            platform=payload.get("platform", ""),
            technology=payload.get("technology", ""),
            partition=payload.get("partition", "validation"),
        )


@dataclass(frozen=True)
class CalibrationFreezeRecord:
    """An immutable, hash-locked freeze of one profile version."""

    freeze_id: str
    profile_id: str
    profile_version: str
    metric: str
    direction: str
    threshold: float
    profile_sha256: str
    held_out_contexts: Tuple[HeldOutContext, ...]
    approved_by: Tuple[str, ...]
    frozen_at: str
    frozen_by: str
    supersedes: Optional[str] = None
    notes: str = ""

    def __post_init__(self) -> None:
        for key in ("freeze_id", "profile_id", "profile_version", "metric", "profile_sha256", "frozen_at", "frozen_by"):
            value = getattr(self, key)
            if not isinstance(value, str) or not value.strip():
                raise CalibrationFreezeError(f"freeze record field '{key}' must be a non-empty string")
        if not (isinstance(self.profile_sha256, str) and len(self.profile_sha256) == 64
                and set(self.profile_sha256.lower()) <= _HEX64):
            raise CalibrationFreezeError("profile_sha256 must be 64 hex characters")
        if not self.held_out_contexts:
            raise CalibrationFreezeError("a freeze must bind at least one held-out context")
        if not self.approved_by:
            raise CalibrationFreezeError("a freeze must record the accountable approver(s)")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": FREEZE_SCHEMA_VERSION,
            "freeze_id": self.freeze_id,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "metric": self.metric,
            "direction": self.direction,
            "threshold": self.threshold,
            "profile_sha256": self.profile_sha256,
            "held_out_contexts": [context.to_dict() for context in self.held_out_contexts],
            "approved_by": list(self.approved_by),
            "frozen_at": self.frozen_at,
            "frozen_by": self.frozen_by,
            "supersedes": self.supersedes,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CalibrationFreezeRecord":
        return cls(
            freeze_id=payload.get("freeze_id", ""),
            profile_id=payload.get("profile_id", ""),
            profile_version=payload.get("profile_version", ""),
            metric=payload.get("metric", ""),
            direction=payload.get("direction", ""),
            threshold=float(payload.get("threshold", 0.0)),
            profile_sha256=payload.get("profile_sha256", ""),
            held_out_contexts=tuple(
                HeldOutContext.from_dict(item) for item in payload.get("held_out_contexts", ())
            ),
            approved_by=tuple(payload.get("approved_by", ())),
            frozen_at=payload.get("frozen_at", ""),
            frozen_by=payload.get("frozen_by", ""),
            supersedes=payload.get("supersedes"),
            notes=payload.get("notes", ""),
        )


def freeze_profile(
    profile: CalibrationProfile,
    held_out_contexts: Sequence[HeldOutContext],
    *,
    freeze_id: str,
    frozen_by: str,
    frozen_at: str = "",
    supersedes: Optional[str] = None,
    notes: str = "",
) -> CalibrationFreezeRecord:
    """Freeze an APPROVED profile hash to its held-out contexts (fail-closed)."""
    if profile.review_status is not CalibrationReviewStatus.APPROVED:
        raise CalibrationFreezeError(
            "only APPROVED profiles can be frozen; "
            f"profile {profile.profile_id}:{profile.version} is {profile.review_status.value}"
        )
    issues = profile.validation_issues()
    if issues:
        raise CalibrationFreezeError(
            "refusing to freeze a profile with validation issues: " + "; ".join(issues)
        )
    contexts = tuple(held_out_contexts)
    if not contexts:
        raise CalibrationFreezeError("freezing requires at least one held-out context")
    seen: set = set()
    for context in contexts:
        key = json.dumps(context.fingerprint(), sort_keys=True)
        if key in seen:
            raise CalibrationFreezeError("duplicate held-out context fingerprint in freeze request")
        seen.add(key)
    return CalibrationFreezeRecord(
        freeze_id=freeze_id,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        metric=profile.metric,
        direction=profile.direction.value,
        threshold=profile.threshold,
        profile_sha256=_canonical_sha256(profile.to_dict()),
        held_out_contexts=contexts,
        approved_by=tuple(approval.reviewer_id for approval in profile.approvals),
        frozen_at=frozen_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        frozen_by=frozen_by,
        supersedes=supersedes,
        notes=notes,
    )


def verify_freeze(
    record: CalibrationFreezeRecord, profile: Optional[CalibrationProfile] = None
) -> Tuple[bool, List[str]]:
    """Re-verify a freeze record; with a profile, recompute the bound hash."""
    reasons: List[str] = []
    try:
        record.to_dict()
    except CalibrationFreezeError as exc:
        reasons.append(str(exc))
        return False, reasons
    if not record.held_out_contexts:
        reasons.append("freeze binds no held-out context")
    if profile is not None:
        if profile.profile_id != record.profile_id or profile.version != record.profile_version:
            reasons.append("profile identity does not match the freeze record")
        else:
            current_hash = _canonical_sha256(profile.to_dict())
            if current_hash != record.profile_sha256:
                reasons.append(
                    "profile hash changed since the freeze was recorded "
                    f"(frozen {record.profile_sha256[:12]}..., current {current_hash[:12]}...)"
                )
    return not reasons, reasons


def context_covered(record: CalibrationFreezeRecord, context: HeldOutContext) -> bool:
    """True when the context fingerprint is inside the frozen held-out scope."""
    fingerprint = json.dumps(context.fingerprint(), sort_keys=True)
    return any(
        json.dumps(bound.fingerprint(), sort_keys=True) == fingerprint
        for bound in record.held_out_contexts
    )


def authorize_context(
    profile: CalibrationProfile,
    freezes: Sequence[CalibrationFreezeRecord],
    context: HeldOutContext,
    *,
    at_profile_hash: Optional[str] = None,
) -> Dict[str, Any]:
    """Fail-closed gate: may this profile issue a positive warrant in this context?

    A positive warrant requires (a) the profile to be APPROVED, (b) a freeze
    record for the exact profile version, (c) the frozen profile hash to still
    match, and (d) the context fingerprint to be inside the frozen held-out
    scope.  Any other combination is a non-authorizing decision.
    """
    if profile.review_status is not CalibrationReviewStatus.APPROVED:
        decision, reason = FreezeDecision.PROFILE_NOT_APPROVED, (
            f"profile {profile.profile_id}:{profile.version} is "
            f"{profile.review_status.value}; only APPROVED profiles may authorize"
        )
    else:
        candidates = [
            record
            for record in freezes
            if record.profile_id == profile.profile_id and record.profile_version == profile.version
        ]
        if not candidates:
            decision, reason = FreezeDecision.FREEZE_REQUIRED, (
                "no freeze record binds this profile to held-out contexts"
            )
        else:
            verified = [record for record in candidates if verify_freeze(record, profile)[0]]
            if not verified:
                decision, reason = FreezeDecision.FREEZE_MISMATCH, (
                    "freeze record(s) exist but the profile hash no longer matches; "
                    "re-approval and a new freeze are required"
                )
            elif at_profile_hash and at_profile_hash != verified[0].profile_sha256:
                decision, reason = FreezeDecision.FREEZE_MISMATCH, (
                    "caller-supplied profile hash does not match the frozen hash"
                )
            else:
                covered = [record for record in verified if context_covered(record, context)]
                if covered:
                    decision, reason = FreezeDecision.AUTHORIZED, (
                        f"context covered by frozen held-out scope of {covered[0].freeze_id}"
                    )
                else:
                    decision, reason = FreezeDecision.CONTEXT_NOT_COVERED, (
                        "context fingerprint is outside every frozen held-out scope; "
                        "the profile says nothing about this context"
                    )
    return {
        "decision": decision.value,
        "authorizing": decision is FreezeDecision.AUTHORIZED,
        "reason": reason,
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
        "context": context.fingerprint(),
    }


def load_freeze_records(payload: Sequence[Mapping[str, Any]]) -> List[CalibrationFreezeRecord]:
    records: List[CalibrationFreezeRecord] = []
    for item in payload:
        if item.get("schema_version", FREEZE_SCHEMA_VERSION) != FREEZE_SCHEMA_VERSION:
            raise CalibrationFreezeError("unsupported freeze record schema")
        records.append(CalibrationFreezeRecord.from_dict(item))
    return records


def profile_from_payload(payload: Mapping[str, Any]) -> CalibrationProfile:
    """Build a :class:`CalibrationProfile` from its serialized form.

    Accepts the registry serialization (``regime`` nested dict) or a flat
    payload with top-level ``tissues``/``platforms``/... keys; evidence and
    approval records are rebuilt from their dicts.
    """
    from bionexus.empirical_warrant import (
        CalibrationReviewStatus,
        ComparisonDirection,
        EmpiricalEvidence,
        ReviewerApproval,
    )

    regime = payload.get("regime") or {}
    flat = {
        key: payload.get(key, regime.get(key, ()))
        for key in ("tissues", "platforms", "references", "tasks", "evidence_sources")
    }
    try:
        evidence = tuple(
            EmpiricalEvidence(
                evidence_id=str(item["evidence_id"]),
                dataset_id=str(item["dataset_id"]),
                source_uri=str(item["source_uri"]),
                source_sha256=str(item["source_sha256"]),
                sample_size=int(item["sample_size"]),
                positive_outcomes=int(item["positive_outcomes"]),
                negative_outcomes=int(item["negative_outcomes"]),
                outcome_definition=str(item["outcome_definition"]),
                estimator=str(item["estimator"]),
                validation_partition=str(item["validation_partition"]),
                independent_validation=bool(item["independent_validation"]),
                observed_precision=float(item["observed_precision"]),
                precision_interval=(
                    float(item["precision_interval"][0]),
                    float(item["precision_interval"][1]),
                ),
                generated_at=str(item.get("generated_at", "")),
            )
            for item in payload.get("evidence", ())
        )
        approvals = tuple(
            ReviewerApproval(
                reviewer_id=str(item["reviewer_id"]),
                reviewed_at=str(item["reviewed_at"]),
                decision=str(item["decision"]),
                scope=str(item["scope"]),
                attestation_sha256=str(item["attestation_sha256"]),
            )
            for item in payload.get("approvals", ())
        )
        return CalibrationProfile(
            profile_id=str(payload["profile_id"]),
            version=str(payload.get("version", "v1")),
            metric=str(payload["metric"]),
            direction=ComparisonDirection(payload.get("direction", "AT_LEAST")),
            threshold=float(payload["threshold"]),
            tissues=tuple(flat["tissues"]),
            platforms=tuple(flat["platforms"]),
            references=tuple(flat["references"]),
            tasks=tuple(flat["tasks"]),
            evidence_sources=tuple(flat["evidence_sources"]),
            review_status=CalibrationReviewStatus(payload.get("review_status", "CANDIDATE")),
            evidence=evidence,
            approvals=approvals,
            applicability_notes=str(payload.get("applicability_notes", "")),
            known_failures=tuple(payload.get("known_failures", ())),
            supersedes=payload.get("supersedes"),
            metadata=dict(payload.get("metadata", {})),
        )
    except KeyError as exc:
        raise CalibrationFreezeError(f"profile payload missing required field {exc}") from exc
