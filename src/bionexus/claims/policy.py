"""
Policy and governing status enforcement for scientific claim warrants.
"""

from __future__ import annotations

from bionexus.claims.models import (
    WarrantEvaluationResult,
    WarrantTierStatus,
)
from bionexus.contracts import ConclusionMaturity
from bionexus.evidence_model import ClaimClass

_NON_AUTHORIZING_GOVERNING_STATUSES = {
    "ABSTAIN",
    "NEEDS_DATA",
    "EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN",
}


def enforce_governing_status(
    evaluation: WarrantEvaluationResult,
    governing_status: str,
) -> WarrantEvaluationResult:
    """Make a non-authorizing top-level route fail closed inside tier verdicts.

    Some consumers read only ``tier_verdicts``. Therefore a top-level refusal
    cannot coexist with a positive tier that those consumers could mistake for
    authorization. Existing negative and not-applicable tiers are preserved;
    positive tiers become explicitly ``NOT_ASSESSED`` because the governing
    preconditions prevented an authorizing assessment.
    """

    normalized = str(getattr(governing_status, "value", governing_status)).upper()
    evaluation.governing_status = normalized
    if normalized not in _NON_AUTHORIZING_GOVERNING_STATUSES:
        return evaluation

    for verdict in evaluation.tier_verdicts.values():
        if verdict.status in (
            WarrantTierStatus.WARRANTED,
            WarrantTierStatus.WARRANTED_WITH_LIMITS,
        ):
            verdict.status = WarrantTierStatus.NOT_ASSESSED
            verdict.is_warranted = False
            verdict.rationale = (
                f"Not authoritatively assessed because the governing route returned {normalized}. "
                "Resolve the top-level refusal or missing-data state before using this tier."
            )
            if "governing_route_authorization" not in verdict.missing_evidence:
                verdict.missing_evidence.append("governing_route_authorization")

    evaluation.is_fully_warranted = False
    evaluation.warranted_claim_class = ClaimClass.DESCRIPTIVE.value
    evaluation.evidence_ceiling = ConclusionMaturity.ABSTAIN.value
    gap = f"governing_status_{normalized.lower()}"
    if gap not in evaluation.evidence_gaps:
        evaluation.evidence_gaps.append(gap)
        evaluation.evidence_gaps.sort()
    evaluation.epistemic_summary = (
        f"Claim '{evaluation.claim_id}' is not scientifically authorized: governing status {normalized}. "
        "Positive tier verdicts were replaced with NOT_ASSESSED; existing negative and not-applicable verdicts remain visible."
    )
    return evaluation


