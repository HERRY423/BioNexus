"""
Evidence Model: Evidence Strength ≠ Intended Use Requirement.

The third theoretical decoupling of the warrant engine, after
warrant-vs-policy (``warrant.py``) and the epistemic rule taxonomy
(``rule_classification.py``):

    Purpose decides the evidence REQUIREMENT, never the evidence VALUE.

A study with 10 donors per group, pre-registration, adequate power, and an
independent replication carries ROBUST evidence whether the researcher calls
it exploratory or confirmatory.  Conversely, weak data does not acquire a
REPLICATED ceiling because someone declares a clinical purpose.

Three objects make this explicit:

1. **EvidenceAssessment** — how strong the evidence IS.  Computed only from
   evidence facts (replication, sample design, effect stability, external
   validation, sensitivity analysis, confound controls, backend fidelity,
   provenance) and from active rule violations.  Purpose- and policy-
   independent by construction.

2. **ClaimContext** — what the researcher wants to claim (descriptive,
   association, population effect, cell identity, spatial dependency,
   mechanistic, causal, predictive, clinical actionability).

3. **UseRequirement** — how much evidence the intended use + claim class
   demands.  This is where ResearchPurpose lives now: purpose sets the bar,
   it does not set the score.

The verdict compares them:

    evidence_maturity  >=  required_maturity  (+ extra conditions)
        -> WARRANTED
    otherwise
        -> NOT_SUFFICIENT_FOR_INTENDED_USE   (with an explicit gap list)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union

from bionexus.contracts import _MATURITY_RANK, ConclusionMaturity
from bionexus.research_purpose import (
    PURPOSE_EVIDENCE_REQUIREMENT,
    PURPOSE_EXTRA_REQUIREMENTS,
    PurposeContext,
    ResearchPurpose,
)


class EvidenceFactor(str, Enum):
    """An evidence fact that can support a conclusion's maturity.

    Factors are declared by the caller (and recorded in provenance); BioNexus
    never assumes an undeclared factor.  Undeclared evidence is weak evidence.
    """

    REPLICATION = "replication"
    SAMPLE_DESIGN = "sample_design"
    EFFECT_STABILITY = "effect_stability"
    EXTERNAL_VALIDATION = "external_validation"
    SENSITIVITY_ANALYSIS = "sensitivity_analysis"
    CONFOUND_CONTROLS = "confound_controls"
    BACKEND_FIDELITY = "backend_fidelity"
    PROVENANCE = "provenance"


#: Positive support ladder: reaching a maturity level requires ALL listed
#: factors to be satisfied.  Ordered from strongest to weakest.
FACTOR_SUPPORT_LADDER: List[Tuple[ConclusionMaturity, Set[EvidenceFactor]]] = [
    (ConclusionMaturity.REPLICATED, {EvidenceFactor.REPLICATION, EvidenceFactor.EXTERNAL_VALIDATION}),
    (
        ConclusionMaturity.ROBUST,
        {
            EvidenceFactor.SAMPLE_DESIGN,
            EvidenceFactor.CONFOUND_CONTROLS,
            EvidenceFactor.SENSITIVITY_ANALYSIS,
        },
    ),
    (ConclusionMaturity.SUPPORTED, {EvidenceFactor.SAMPLE_DESIGN, EvidenceFactor.REPLICATION}),
    (ConclusionMaturity.PRELIMINARY, {EvidenceFactor.SAMPLE_DESIGN}),
]

#: Integrity prerequisites for ROBUST and above: a robust claim must rest on
#: a faithful backend and a recorded provenance chain.
INTEGRITY_FACTORS: Set[EvidenceFactor] = {
    EvidenceFactor.BACKEND_FIDELITY,
    EvidenceFactor.PROVENANCE,
}

#: Honest default: a cleanly executed single analysis with verified
#: preconditions but no declared supporting factors is PRELIMINARY at best.
DEFAULT_UNEVIDENCED_MATURITY = ConclusionMaturity.PRELIMINARY

#: Any active violation caps evidence at FRAGILE (shared with warrant.py).
VIOLATION_MATURITY_CAP = ConclusionMaturity.FRAGILE


@dataclass
class EvidenceAssessment:
    """How strong the evidence IS — independent of purpose and policy.

    Attributes:
        evidence_maturity: The maturity the evidence facts actually support.
        satisfied_factors: The declared evidence factors behind it.
        caps_applied: Rule IDs that actively cap the evidence (violations).
        rationale: Human-readable derivation summary.
    """

    evidence_maturity: str
    satisfied_factors: List[str] = field(default_factory=list)
    caps_applied: List[str] = field(default_factory=list)
    rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evidence_maturity": self.evidence_maturity,
            "satisfied_factors": self.satisfied_factors,
            "caps_applied": self.caps_applied,
            "rationale": self.rationale,
            "purpose_independent": True,
            "policy_independent": True,
        }


def _factor_set(factors: Sequence[Union[str, EvidenceFactor]]) -> Set[EvidenceFactor]:
    result: Set[EvidenceFactor] = set()
    for f in factors:
        result.add(EvidenceFactor(f.value if isinstance(f, EvidenceFactor) else str(f)))
    return result


def assess_evidence(
    *,
    base_maturity: Union[str, ConclusionMaturity] = ConclusionMaturity.UNASSESSED,
    satisfied_factors: Sequence[Union[str, EvidenceFactor]] = (),
    warrant_triggers: Sequence[Any] = (),
    invariant_triggers: Sequence[Any] = (),
) -> EvidenceAssessment:
    """Assess evidence strength from evidence facts alone.

    Neither the research purpose nor the lab policy appears in this
    computation — that is the contract.
    """
    factors = _factor_set(satisfied_factors)

    # The support ladder: highest level whose required factors are all present.
    supported = DEFAULT_UNEVIDENCED_MATURITY
    for level, required in FACTOR_SUPPORT_LADDER:
        if not required.issubset(factors):
            continue
        if _MATURITY_RANK.get(level.value, 0) >= _MATURITY_RANK.get(
            ConclusionMaturity.ROBUST.value, 0
        ) and not INTEGRITY_FACTORS.issubset(factors):
            continue
        supported = level
        break

    maturity = supported
    base = base_maturity.value if isinstance(base_maturity, ConclusionMaturity) else str(base_maturity)
    # Only an actual evidence level (FRAGILE and above) can cap the
    # assessment; UNASSESSED and ABSTAIN mean "no conclusion produced", not
    # a weak evidence level.
    if (
        base not in (ConclusionMaturity.UNASSESSED.value, ConclusionMaturity.ABSTAIN.value)
        and _MATURITY_RANK.get(base, 0) < _MATURITY_RANK.get(maturity.value, 0)
    ):
        maturity = ConclusionMaturity(base)

    caps: List[str] = []
    for trigger in list(invariant_triggers) + list(warrant_triggers):
        caps.append(getattr(trigger, "condition_id", ""))
    if caps and _MATURITY_RANK.get(VIOLATION_MATURITY_CAP.value, 0) < _MATURITY_RANK.get(maturity.value, 0):
        maturity = VIOLATION_MATURITY_CAP

    if caps:
        rationale = (
            f"Active violations ({', '.join(sorted(set(caps)))}) cap evidence at "
            f"{maturity.value}; declared factors: {sorted(f.value for f in factors) or 'none'}."
        )
    else:
        rationale = (
            f"Evidence maturity {maturity.value} derived from declared factors "
            f"{sorted(f.value for f in factors) or 'none'}; purpose and policy "
            f"play no role in this assessment."
        )

    return EvidenceAssessment(
        evidence_maturity=maturity.value,
        satisfied_factors=sorted(f.value for f in factors),
        caps_applied=sorted(set(caps)),
        rationale=rationale,
    )


class ClaimClass(str, Enum):
    """What the researcher wants to claim."""

    DESCRIPTIVE = "descriptive"
    ASSOCIATION = "association"
    POPULATION_EFFECT = "population_effect"
    CELL_IDENTITY = "cell_identity"
    SPATIAL_DEPENDENCY = "spatial_dependency"
    MECHANISTIC = "mechanistic"
    CAUSAL = "causal"
    PREDICTIVE = "predictive"
    CLINICAL_ACTIONABILITY = "clinical_actionability"


@dataclass
class ClaimContext:
    """The claim under evaluation.

    Attributes:
        claim_class: The epistemic class of the claim.
        statement: Free-text claim statement (audited by claim_checker).
    """

    claim_class: ClaimClass = ClaimClass.DESCRIPTIVE
    statement: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"claim_class": self.claim_class.value, "statement": self.statement}


#: Minimum maturity and extra conditions each claim class demands, regardless
#: of declared purpose.  A claim cannot cost less than its own class.
CLAIM_REQUIREMENTS: Dict[ClaimClass, Tuple[ConclusionMaturity, List[str]]] = {
    ClaimClass.DESCRIPTIVE: (ConclusionMaturity.PRELIMINARY, []),
    ClaimClass.ASSOCIATION: (ConclusionMaturity.PRELIMINARY, []),
    ClaimClass.POPULATION_EFFECT: (ConclusionMaturity.SUPPORTED, []),
    ClaimClass.CELL_IDENTITY: (ConclusionMaturity.SUPPORTED, []),
    ClaimClass.SPATIAL_DEPENDENCY: (ConclusionMaturity.SUPPORTED, ["confound_controls"]),
    ClaimClass.MECHANISTIC: (ConclusionMaturity.ROBUST, ["confound_controls"]),
    ClaimClass.CAUSAL: (ConclusionMaturity.SUPPORTED, ["causal_identification"]),
    ClaimClass.PREDICTIVE: (ConclusionMaturity.ROBUST, ["external_validation"]),
    ClaimClass.CLINICAL_ACTIONABILITY: (
        ConclusionMaturity.REPLICATED,
        ["external_validation", "regulatory_context"],
    ),
}


@dataclass
class UseRequirement:
    """How much evidence the intended use + claim class demands.

    This is the ONLY place ResearchPurpose affects the verdict: it sets the
    bar the evidence must clear, never the evidence itself.
    """

    purpose: ResearchPurpose
    claim_class: ClaimClass
    required_maturity: ConclusionMaturity
    extra_requirements: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "purpose": self.purpose.value,
            "claim_class": self.claim_class.value,
            "required_maturity": self.required_maturity.value,
            "extra_requirements": self.extra_requirements,
        }


def use_requirement_for(purpose: ResearchPurpose, claim_class: ClaimClass) -> UseRequirement:
    """Compose the requirement from the intended use and the claim class."""
    purpose_maturity = PURPOSE_EVIDENCE_REQUIREMENT.get(purpose, ConclusionMaturity.FRAGILE)
    claim_maturity, claim_extras = CLAIM_REQUIREMENTS[claim_class]
    required = (
        purpose_maturity
        if _MATURITY_RANK.get(purpose_maturity.value, 0) >= _MATURITY_RANK.get(claim_maturity.value, 0)
        else claim_maturity
    )
    extras = sorted(set(PURPOSE_EXTRA_REQUIREMENTS.get(purpose, [])) | set(claim_extras))
    return UseRequirement(
        purpose=purpose,
        claim_class=claim_class,
        required_maturity=required,
        extra_requirements=extras,
    )


class SufficiencyVerdict(str, Enum):
    """Is the evidence sufficient for the intended use?"""

    WARRANTED = "WARRANTED"
    WARRANTED_WITH_LIMITS = "WARRANTED_WITH_LIMITS"
    NOT_SUFFICIENT_FOR_INTENDED_USE = "NOT_SUFFICIENT_FOR_INTENDED_USE"


#: Extra requirements that a declared evidence factor can satisfy.
_EXTRA_SATISFIED_BY: Dict[str, Set[EvidenceFactor]] = {
    "external_validation": {EvidenceFactor.EXTERNAL_VALIDATION},
    "confound_controls": {EvidenceFactor.CONFOUND_CONTROLS},
}


@dataclass
class SufficiencyAssessment:
    """The verdict comparing evidence against the intended-use requirement."""

    verdict: SufficiencyVerdict
    requirement: UseRequirement
    evidence_maturity: str
    gaps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "requirement": self.requirement.to_dict(),
            "evidence_maturity": self.evidence_maturity,
            "gaps": self.gaps,
        }


def evaluate_sufficiency(
    *,
    evidence: EvidenceAssessment,
    purpose_context: PurposeContext,
    claim_context: Optional[ClaimContext] = None,
    documented_extras: Sequence[str] = (),
    override_acknowledged: bool = False,
) -> SufficiencyAssessment:
    """Compare evidence against the intended-use requirement.

    ``documented_extras`` are extra conditions the caller documents outside
    the factor model (e.g. a causal identification strategy, a regulatory
    context).  ``override_acknowledged`` records that a researcher accepted
    the insufficiency with documented limits — the verdict downgrades to
    WARRANTED_WITH_LIMITS, the requirement itself never changes.
    """
    claim = claim_context or ClaimContext()
    requirement = use_requirement_for(purpose_context.purpose, claim.claim_class)
    factors = _factor_set(evidence.satisfied_factors)
    documented = set(documented_extras)

    gaps: List[str] = []
    if purpose_context.purpose == ResearchPurpose.UNSPECIFIED:
        gaps.append("intended_use_undeclared")

    if _MATURITY_RANK.get(evidence.evidence_maturity, 0) < _MATURITY_RANK.get(requirement.required_maturity.value, 0):
        gaps.append(f"evidence_maturity {evidence.evidence_maturity} < required {requirement.required_maturity.value}")

    for extra in requirement.extra_requirements:
        if extra in documented:
            continue
        satisfied_by = _EXTRA_SATISFIED_BY.get(extra)
        if satisfied_by is not None and satisfied_by.issubset(factors):
            continue
        gaps.append(f"missing_required_condition:{extra}")

    if not gaps:
        verdict = SufficiencyVerdict.WARRANTED
    elif override_acknowledged:
        verdict = SufficiencyVerdict.WARRANTED_WITH_LIMITS
    else:
        verdict = SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE

    return SufficiencyAssessment(
        verdict=verdict,
        requirement=requirement,
        evidence_maturity=evidence.evidence_maturity,
        gaps=gaps,
    )
