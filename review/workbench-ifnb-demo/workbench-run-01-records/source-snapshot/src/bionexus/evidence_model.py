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
    OVERRIDABLE_PURPOSES,
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
    SPATIAL_COLOCALIZATION = "spatial_colocalization"
    LIGAND_RECEPTOR_INFERENCE = "ligand_receptor_inference"
    PERTURBATION = "perturbation"
    TEMPORAL_EVIDENCE = "temporal_evidence"
    REFERENCE_GROUND_TRUTH = "reference_ground_truth"
    REGULATORY_CERTIFICATION = "regulatory_certification"
    REGULATORY_CONTEXT = "regulatory_context"


#: Positive support ladder: reaching a maturity level requires ALL listed
#: factors to be satisfied.  Ordered from strongest to weakest.
#: The ladder is strictly cumulative (REPLICATED ⊃ ROBUST ⊃ SUPPORTED ⊃ PRELIMINARY).
FACTOR_SUPPORT_LADDER: List[Tuple[ConclusionMaturity, Set[EvidenceFactor]]] = [
    (
        ConclusionMaturity.REPLICATED,
        {
            EvidenceFactor.SAMPLE_DESIGN,
            EvidenceFactor.REPLICATION,
            EvidenceFactor.CONFOUND_CONTROLS,
            EvidenceFactor.SENSITIVITY_ANALYSIS,
            EvidenceFactor.EXTERNAL_VALIDATION,
        },
    ),
    (
        ConclusionMaturity.ROBUST,
        {
            EvidenceFactor.SAMPLE_DESIGN,
            EvidenceFactor.REPLICATION,
            EvidenceFactor.CONFOUND_CONTROLS,
            EvidenceFactor.SENSITIVITY_ANALYSIS,
        },
    ),
    (
        ConclusionMaturity.SUPPORTED,
        {
            EvidenceFactor.SAMPLE_DESIGN,
            EvidenceFactor.REPLICATION,
        },
    ),
    (
        ConclusionMaturity.PRELIMINARY,
        {
            EvidenceFactor.SAMPLE_DESIGN,
        },
    ),
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
        val = f.value if isinstance(f, EvidenceFactor) else str(f)
        try:
            result.add(EvidenceFactor(val))
        except ValueError:
            # Unrecognized/misspelled factor strings are safely ignored (fail-closed, weak evidence)
            pass
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
    base_str = base_maturity.value if isinstance(base_maturity, ConclusionMaturity) else str(base_maturity)
    try:
        base_enum = ConclusionMaturity(base_str)
    except ValueError:
        base_enum = ConclusionMaturity.UNASSESSED

    # Only an actual evidence level (FRAGILE and above) can cap the
    # assessment; UNASSESSED and ABSTAIN mean "no conclusion produced", not
    # a weak evidence level.
    if (
        base_enum not in (ConclusionMaturity.UNASSESSED, ConclusionMaturity.ABSTAIN)
        and _MATURITY_RANK.get(base_enum.value, 0) < _MATURITY_RANK.get(maturity.value, 0)
    ):
        maturity = base_enum

    # L1: Filter malformed triggers (empty strings or missing condition_id attributes)
    caps: List[str] = []
    for trigger in list(invariant_triggers) + list(warrant_triggers):
        cid = getattr(trigger, "condition_id", None) or (trigger if isinstance(trigger, str) else "")
        if isinstance(cid, str) and cid.strip():
            caps.append(cid.strip())

    # M1: Active violations cap maturity at FRAGILE, but MUST NOT erase CONFLICTED status
    if caps and maturity != ConclusionMaturity.CONFLICTED and _MATURITY_RANK.get(VIOLATION_MATURITY_CAP.value, 0) < _MATURITY_RANK.get(maturity.value, 0):
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

    UNSPECIFIED = "unspecified"
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
        claim_class: The epistemic class of the claim. Defaults to UNSPECIFIED (fail-closed).
        statement: Free-text claim statement (audited by claim_checker).
    """

    claim_class: ClaimClass = ClaimClass.UNSPECIFIED
    statement: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"claim_class": self.claim_class.value, "statement": self.statement}


#: Minimum maturity and extra conditions each claim class demands, regardless
#: of declared purpose.  A claim cannot cost less than its own class.
CLAIM_REQUIREMENTS: Dict[ClaimClass, Tuple[ConclusionMaturity, List[str]]] = {
    ClaimClass.UNSPECIFIED: (ConclusionMaturity.FRAGILE, []),
    ClaimClass.DESCRIPTIVE: (ConclusionMaturity.PRELIMINARY, []),
    ClaimClass.ASSOCIATION: (ConclusionMaturity.PRELIMINARY, []),
    ClaimClass.POPULATION_EFFECT: (ConclusionMaturity.SUPPORTED, []),
    ClaimClass.CELL_IDENTITY: (ConclusionMaturity.SUPPORTED, []),
    ClaimClass.SPATIAL_DEPENDENCY: (ConclusionMaturity.SUPPORTED, ["confound_controls"]),
    ClaimClass.MECHANISTIC: (ConclusionMaturity.ROBUST, ["confound_controls"]),
    ClaimClass.CAUSAL: (
        ConclusionMaturity.ROBUST,
        ["causal_identification", "confound_controls"],
    ),
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
    purpose_maturity = PURPOSE_EVIDENCE_REQUIREMENT.get(purpose, ConclusionMaturity.REPLICATED)
    claim_maturity, claim_extras = CLAIM_REQUIREMENTS.get(
        claim_class, (ConclusionMaturity.REPLICATED, [])
    )
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
    """Authoritative verdict of the BioNexus Evidence Sufficiency Engine."""

    WARRANTED = "WARRANTED"
    WARRANTED_WITH_LIMITS = "WARRANTED_WITH_LIMITS"
    NOT_SUFFICIENT_FOR_INTENDED_USE = "NOT_SUFFICIENT_FOR_INTENDED_USE"


#: Extra conditions that can be satisfied by caller documentation alone
DOCUMENTABLE_EXTRAS: Set[str] = {
    "causal_identification",
}

#: Factor mappings for conditions that require verified empirical/evidence factors
_EXTRA_SATISFIED_BY: Dict[str, Set[EvidenceFactor]] = {
    "confound_controls": {EvidenceFactor.CONFOUND_CONTROLS},
    "external_validation": {EvidenceFactor.EXTERNAL_VALIDATION},
    "spatial_colocalization": {EvidenceFactor.SPATIAL_COLOCALIZATION},
    "ligand_receptor_inference": {EvidenceFactor.LIGAND_RECEPTOR_INFERENCE},
    "reference_ground_truth": {EvidenceFactor.REFERENCE_GROUND_TRUTH},
    "regulatory_context": {EvidenceFactor.REGULATORY_CERTIFICATION},
}


def extract_evidence_factors(
    metadata: Optional[Dict[str, Any]] = None,
    *,
    backend_fidelity: bool = False,
    has_provenance: bool = False,
    explicit_factors: Sequence[Union[str, EvidenceFactor]] = (),
    tool_receipts: Sequence[Dict[str, Any]] = (),
    receipt_log_path: Optional[Any] = None,
) -> List[str]:
    """Extract and normalize satisfied evidence factor string names from metadata,
    explicit declarations, and integrity-checked tool execution receipts (BNS-025).

    Metadata and explicit factors are caller-supplied assessment inputs, not
    authenticated evidence. Receipt integrity alone supplies no factors; the
    receipt module has no trusted host/provider attestation verifier.

    Converts:
    1. Cryptographic Tool Execution Receipts (`tool_receipts`, `receipt_log_path`).
    2. Explicit factor lists (`evidence_factors`, `satisfied_factors`).
    3. Dataset & design metadata (e.g. min_replicates_per_condition >= 2, donors_per_condition >= 2,
       replications count, confound_controls, sensitivity_analysis, spatial coordinates, perturbation, etc.).
    4. Verified backend fidelity & provenance indicators.
    """
    factors: Set[str] = set()

    # 1. Receipt factors fail closed when trusted attestation is unavailable.
    if tool_receipts:
        from bionexus.tool_receipt import extract_evidence_factors_from_receipt

        for rcpt in tool_receipts:
            rcpt_factors, _ = extract_evidence_factors_from_receipt(rcpt)
            factors.update(rcpt_factors)

    if receipt_log_path:
        from bionexus.tool_receipt import extract_evidence_factors_from_receipt_log

        rcpt_factors, _ = extract_evidence_factors_from_receipt_log(receipt_log_path)
        factors.update(rcpt_factors)

    for ef in explicit_factors:
        val = ef.value if isinstance(ef, EvidenceFactor) else str(ef)
        try:
            factors.add(EvidenceFactor(val).value)
        except ValueError:
            pass

    meta = dict(metadata or {})

    for key in ("evidence_factors", "satisfied_factors", "declared_factors"):
        raw_list = meta.get(key)
        if isinstance(raw_list, (list, tuple, set)):
            for ef in raw_list:
                val = ef.value if isinstance(ef, EvidenceFactor) else str(ef)
                try:
                    factors.add(EvidenceFactor(val).value)
                except ValueError:
                    pass

    def _is_truthy(k: str) -> bool:
        v = meta.get(k)
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v is True or v == 1)

    reps = (
        meta.get("min_replicates_per_condition")
        or meta.get("donors_per_condition")
        or meta.get("biological_replicates_count")
        or meta.get("num_donors")
        or meta.get("biological_replicates")
        or 0
    )
    try:
        reps_int = int(reps)
    except (ValueError, TypeError):
        reps_int = 0

    if reps_int >= 2 or _is_truthy("sample_design") or _is_truthy("has_sample_design"):
        factors.add(EvidenceFactor.SAMPLE_DESIGN.value)

    if reps_int >= 2 or _is_truthy("replication") or _is_truthy("replicated") or int(meta.get("independent_replications") or 0) >= 1:
        factors.add(EvidenceFactor.REPLICATION.value)

    if _is_truthy("confound_controls") or _is_truthy("has_confound_controls") or _is_truthy("covariates_adjusted") or _is_truthy("batch_corrected"):
        factors.add(EvidenceFactor.CONFOUND_CONTROLS.value)

    if _is_truthy("sensitivity_analysis") or _is_truthy("has_sensitivity_analysis") or _is_truthy("parameter_sweep") or _is_truthy("stability_verified"):
        factors.add(EvidenceFactor.SENSITIVITY_ANALYSIS.value)
        factors.add(EvidenceFactor.EFFECT_STABILITY.value)

    if _is_truthy("effect_stability"):
        factors.add(EvidenceFactor.EFFECT_STABILITY.value)

    if _is_truthy("external_validation") or _is_truthy("independent_validation") or _is_truthy("has_external_validation"):
        factors.add(EvidenceFactor.EXTERNAL_VALIDATION.value)

    if _is_truthy("has_spatial") or _is_truthy("has_spatial_coords") or _is_truthy("spatial_colocalization"):
        factors.add(EvidenceFactor.SPATIAL_COLOCALIZATION.value)

    if _is_truthy("ligand_receptor_inference"):
        factors.add(EvidenceFactor.LIGAND_RECEPTOR_INFERENCE.value)

    if _is_truthy("perturbation") or _is_truthy("is_perturbation"):
        factors.add(EvidenceFactor.PERTURBATION.value)

    if _is_truthy("temporal_evidence") or _is_truthy("time_series"):
        factors.add(EvidenceFactor.TEMPORAL_EVIDENCE.value)

    if _is_truthy("reference_ground_truth") or _is_truthy("clinical_ground_truth"):
        factors.add(EvidenceFactor.REFERENCE_GROUND_TRUTH.value)

    if _is_truthy("regulatory_certification") or _is_truthy("clia_cap_certified") or _is_truthy("fda_cleared"):
        factors.add(EvidenceFactor.REGULATORY_CERTIFICATION.value)
        factors.add(EvidenceFactor.REGULATORY_CONTEXT.value)

    if _is_truthy("regulatory_context"):
        factors.add(EvidenceFactor.REGULATORY_CONTEXT.value)
        factors.add(EvidenceFactor.REGULATORY_CERTIFICATION.value)

    if backend_fidelity or _is_truthy("backend_fidelity"):
        factors.add(EvidenceFactor.BACKEND_FIDELITY.value)

    if has_provenance or _is_truthy("provenance") or _is_truthy("has_provenance") or "bionexus_provenance" in meta:
        factors.add(EvidenceFactor.PROVENANCE.value)

    return sorted(factors)


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

    ``documented_extras`` are non-invariant extra conditions the caller documents
    outside the factor model (e.g. a causal identification strategy).
    Clinical regulatory context and verified factors cannot be satisfied by unverified
    documented free-text strings alone.

    ``override_acknowledged`` records that a researcher accepted the insufficiency
    with documented limits — for overridable purposes, the verdict downgrades to
    WARRANTED_WITH_LIMITS; for clinical or unspecified purposes, overrides are denied
    under patient safety invariants and the verdict remains NOT_SUFFICIENT_FOR_INTENDED_USE.
    """
    if isinstance(claim_context, str):
        try:
            claim = ClaimContext(claim_class=ClaimClass(claim_context))
        except ValueError:
            claim = ClaimContext(claim_class=ClaimClass.UNSPECIFIED)
    elif isinstance(claim_context, ClaimClass):
        claim = ClaimContext(claim_class=claim_context)
    else:
        claim = claim_context or ClaimContext()
    requirement = use_requirement_for(purpose_context.purpose, claim.claim_class)
    factors = _factor_set(evidence.satisfied_factors)
    documented = set(documented_extras)

    gaps: List[str] = []
    if purpose_context.purpose == ResearchPurpose.UNSPECIFIED:
        gaps.append("intended_use_undeclared")
    if claim.claim_class == ClaimClass.UNSPECIFIED:
        gaps.append("claim_class_undeclared")
    if evidence.evidence_maturity == ConclusionMaturity.CONFLICTED.value:
        gaps.append("evidence_conflicted: contradictory findings across alternative methods or benchmarks")

    if _MATURITY_RANK.get(evidence.evidence_maturity, 0) < _MATURITY_RANK.get(requirement.required_maturity.value, 0):
        gaps.append(f"evidence_maturity {evidence.evidence_maturity} < required {requirement.required_maturity.value}")

    for extra in requirement.extra_requirements:
        # Only explicitly documentable conditions may be satisfied by caller documentation
        if extra in documented and extra in DOCUMENTABLE_EXTRAS:
            continue
        satisfied_by = _EXTRA_SATISFIED_BY.get(extra)
        if satisfied_by is not None and (
            satisfied_by.issubset(factors)
            or (
                extra == "regulatory_context"
                and (
                    EvidenceFactor.REGULATORY_CERTIFICATION in factors
                    or EvidenceFactor.REGULATORY_CONTEXT in factors
                )
            )
        ):
            continue
        gaps.append(f"missing_required_condition:{extra}")

    if not gaps:
        verdict = SufficiencyVerdict.WARRANTED
    elif override_acknowledged and purpose_context.purpose in OVERRIDABLE_PURPOSES:
        verdict = SufficiencyVerdict.WARRANTED_WITH_LIMITS
    else:
        verdict = SufficiencyVerdict.NOT_SUFFICIENT_FOR_INTENDED_USE

    return SufficiencyAssessment(
        verdict=verdict,
        requirement=requirement,
        evidence_maturity=evidence.evidence_maturity,
        gaps=gaps,
    )
