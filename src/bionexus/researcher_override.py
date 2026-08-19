"""
Explicit Researcher Override Mechanism.

Professional researchers sometimes need to proceed past a soft block
(e.g. running DE with only 1 replicate per condition for a pilot study).
BioNexus permits this, but the override MUST be explicit and documented:

1. **Why**: The researcher's justification for proceeding.
2. **What remains**: Which limitations are still in effect despite the override.
3. **What cannot be claimed**: Which claims are permanently blocked regardless
   of the override (e.g. population-level inference from n=1).

Hard rules (clinical diagnosis, identifier corruption, model substitution)
are NEVER overridable.  The override mechanism only applies to soft rules
(methodological guidelines like replicate count, input distribution, etc.).

Override records are attached to the EvidenceCard and provenance sidecar so
that downstream consumers can see exactly what was overridden and why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from bionexus.contracts import ConclusionMaturity
from bionexus.research_purpose import OVERRIDABLE_PURPOSES, ResearchPurpose
from bionexus.rule_provenance import ConsensusLevel, RuleProvenance


@dataclass
class OverrideRecord:
    """A documented researcher override of a soft scientific rule.

    Attributes:
        rule_id: The condition_id or precondition_id that was overridden.
        rule_description: Human-readable description of the overridden rule.
        justification: Why the researcher is overriding this rule.
        researcher_id: Optional identifier for the researcher (for audit trail).
        timestamp: When the override was invoked (ISO 8601).
        residual_limitations: Limitations that remain despite the override.
        blocked_claims: Claims that are still NOT warranted even after override.
        evidence_ceiling_override: The new maximum ConclusionMaturity under override.
            This is typically LOWER than what the purpose would allow.
        provenance: The provenance of the overridden rule (for transparency).
    """

    rule_id: str
    rule_description: str
    justification: str
    researcher_id: str = ""
    timestamp: str = ""
    residual_limitations: List[str] = field(default_factory=list)
    blocked_claims: List[str] = field(default_factory=list)
    evidence_ceiling_override: ConclusionMaturity = ConclusionMaturity.FRAGILE
    provenance: Optional[RuleProvenance] = None

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_description": self.rule_description,
            "justification": self.justification,
            "researcher_id": self.researcher_id,
            "timestamp": self.timestamp,
            "residual_limitations": self.residual_limitations,
            "blocked_claims": self.blocked_claims,
            "evidence_ceiling_override": self.evidence_ceiling_override.value,
            "provenance": self.provenance.to_dict() if self.provenance else None,
        }


# ---------------------------------------------------------------------------
# Override eligibility checks
# ---------------------------------------------------------------------------


def is_override_permitted(
    purpose: ResearchPurpose,
    provenance: Optional[RuleProvenance] = None,
) -> bool:
    """Check whether a rule can be overridden under the given purpose.

    Override is blocked when:
    - The purpose is UNSPECIFIED (declare a purpose before overriding).
    - The purpose is CLINICAL (patient safety invariant).
    - The rule is a hard rule (safety invariant).
    """
    if purpose not in OVERRIDABLE_PURPOSES:
        return False
    if provenance and provenance.hard_rule:
        return False
    return True


# ---------------------------------------------------------------------------
# Default residual limitations and blocked claims per overridden rule.
# ---------------------------------------------------------------------------

_DEFAULT_RESIDUAL_LIMITATIONS: Dict[str, List[str]] = {
    "normalized_matrix_only": [
        "Input is not raw integer counts; negative binomial dispersion assumptions are violated.",
        "P-values and fold-changes are approximate; do not cite as definitive DE results.",
    ],
    "missing_replicates": [
        "No biological replication; population-level inference is not possible.",
        "Results describe this specific sample only; generalization requires independent replication.",
    ],
    "min_replicates": [
        "Fewer than 2 replicates per condition; dispersion estimation is unreliable.",
        "Condition effects are confounded with biological noise.",
    ],
    "spatial_coords_present": [
        "Physical tissue coordinates are absent or substituted; spatial statistics may be invalid.",
    ],
    "embedding_substitution": [
        "Embedding coordinates used in place of physical coordinates; spatial autocorrelation measures are not comparable to tissue-level analyses.",
    ],
    "annotation_source_recorded": [
        "Cell-type labels lack documented evidence support; identity claims are candidates only.",
    ],
    "negative_markers_evaluated": [
        "Negative marker validation not performed; related lineages may be confused.",
    ],
    "missing_backend": [
        "Canonical backend not installed; execution uses a heuristic or proxy.",
        "Results MUST NOT be cited as canonical backend output.",
    ],
}

_DEFAULT_BLOCKED_CLAIMS: Dict[str, List[str]] = {
    "normalized_matrix_only": [
        "causal_interaction",
        "clinical_diagnosis",
        "treatment_recommendation",
    ],
    "missing_replicates": [
        "population_level_inference",
        "causal_interaction",
        "clinical_diagnosis",
        "treatment_recommendation",
    ],
    "min_replicates": [
        "population_level_inference",
        "causal_interaction",
        "clinical_diagnosis",
    ],
    "spatial_coords_present": [
        "tissue_level_spatial_conclusion",
        "clinical_diagnosis",
    ],
    "embedding_substitution": [
        "tissue_level_spatial_conclusion",
        "clinical_diagnosis",
    ],
    "annotation_source_recorded": [
        "cell_type_identity",
        "clinical_diagnosis",
    ],
    "missing_backend": [
        "canonical_backend_output",
        "clinical_diagnosis",
    ],
}

_DEFAULT_EVIDENCE_CEILING: Dict[str, ConclusionMaturity] = {
    "normalized_matrix_only": ConclusionMaturity.FRAGILE,
    "missing_replicates": ConclusionMaturity.FRAGILE,
    "min_replicates": ConclusionMaturity.FRAGILE,
    "spatial_coords_present": ConclusionMaturity.FRAGILE,
    "embedding_substitution": ConclusionMaturity.FRAGILE,
    "annotation_source_recorded": ConclusionMaturity.FRAGILE,
    "negative_markers_evaluated": ConclusionMaturity.PRELIMINARY,
    "missing_backend": ConclusionMaturity.FRAGILE,
}


def create_override_record(
    rule_id: str,
    rule_description: str,
    justification: str,
    *,
    purpose: ResearchPurpose = ResearchPurpose.UNSPECIFIED,
    researcher_id: str = "",
    provenance: Optional[RuleProvenance] = None,
) -> OverrideRecord:
    """Create a documented override record with default residual limitations.

    Automatically populates residual limitations, blocked claims, and evidence
    ceiling based on the overridden rule.  Callers can modify these fields
    after creation if the defaults need adjustment.
    """
    if not is_override_permitted(purpose, provenance):
        if purpose == ResearchPurpose.UNSPECIFIED:
            reason = (
                "Research purpose is UNSPECIFIED: declare a purpose "
                "(exploratory / screening / confirmatory / causal) before invoking an override."
            )
        elif purpose == ResearchPurpose.CLINICAL:
            reason = "Clinical purpose never permits override (patient safety invariant)."
        else:
            reason = "This is a hard rule (safety invariant)."
        raise OverrideDenied(
            f"Rule '{rule_id}' cannot be overridden under purpose '{purpose.value}'. {reason}"
        )

    return OverrideRecord(
        rule_id=rule_id,
        rule_description=rule_description,
        justification=justification,
        researcher_id=researcher_id,
        residual_limitations=_DEFAULT_RESIDUAL_LIMITATIONS.get(rule_id, [f"Rule '{rule_id}' overridden; limitations not pre-specified."]),
        blocked_claims=_DEFAULT_BLOCKED_CLAIMS.get(rule_id, ["clinical_diagnosis", "treatment_recommendation"]),
        evidence_ceiling_override=_DEFAULT_EVIDENCE_CEILING.get(rule_id, ConclusionMaturity.FRAGILE),
        provenance=provenance,
    )


class OverrideDenied(RuntimeError):
    """Raised when an override is attempted on a non-overridable rule."""

    pass
