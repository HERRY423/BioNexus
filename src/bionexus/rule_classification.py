"""
Rule Classification: Execution Invariants vs Warrant Constraints.

BioNexus has always conflated two fundamentally distinct classes of constraint:

- **Execution Invariants** are non-negotiable safety and integrity rules that MUST
  prevent execution when violated. They correspond to what the literature calls
  "hard invariants": identifier namespace corruption, model masquerade, clinical
  claims without regulatory certification. Breaking these produces garbage or harms.

- **Warrant Constraints** are epistemic limitations on what conclusions the current
  data + method combination CAN justify. They specify the maximum warrant (justification)
  for claims, not whether computation can proceed. Examples: "n=1 cannot support
  population-level inference", "cross-sectional data cannot support causal claims".

This distinction matters because:

1. Execution Invariants BLOCK; Warrant Constraints CAP. One stops execution;
   the other caps what you can claim AFTER execution.
2. Warrant Constraints compose with ResearchPurpose: the same n=2 design may be
   sufficient for screening but not confirmatory analysis. An execution invariant
   has no such context-sensitivity.
3. Lab Policy determines enforcement mode: Shadow warts about both; Advisory blocks
   warrant violations but allows execution; Enforced also blocks invariant violations.

See: Gold standard in computer science (Hoare logic), clinical trial methodology
(ICH E6 R3 Good Clinical Practice), statistical inference theory (Kendall 1938;
Fisher 1935).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class RuleCategory(str, Enum):
    """Whether this rule is an execution invariant or a warrant constraint.

    - INVARIANT_SAFETY: Never allow execution that violates this rule.
      Corresponds to CLIA/CAP mandates, identifier integrity, model identity.
    - INVARIANT_INTEGRITY: Never allow computation that silently corrupts data.
      Corresponds to namespace collisions, format coercion, silent substitution.
    - WARRANT_EPISTEMIC: Limits on what claims the evidence justifies.
      Does NOT block execution; blocks over-claiming. The conclusion stays at
      the highest maturity that the warrant supports.
    """

    INVARIANT_SAFETY = "INVARIANT_SAFETY"
    INVARIANT_INTEGRITY = "INVARIANT_INTEGRITY"
    WARRANT_EPISTEMIC = "WARRANT_EPISTEMIC"


# ---------------------------------------------------------------------------
# Convenience constants matching ConsensusLevel for backward compatibility.
# ---------------------------------------------------------------------------

class EnforcementLevel(str, Enum):
    """How strictly this rule must be enforced under different lab policies.

    - ENFORCED: Never permit violation; equivalent to current `hard_rule=True`.
    - ADVISORY: Permit but require explicit documentation; equivalent to
      `PERMITTED_WITH_LIMITS` with override record.
    - SHADOW: Record metadata only; does not affect routing decision.
    """

    ENFORCED = "ENFORCED"
    ADVISORY = "ADVISORY"
    SHADOW = "SHADOW"


# Backward compatibility aliases for existing provenance records.
# Old code used hard_rule: True → INVARIANT_SAFETY/INTEGRITY.
# Old code used hard_rule: False → WARRANT_EPISTEMIC (most cases).
HARD_TO_CATEGORY: Dict[bool, Set[RuleCategory]] = {
    True: {RuleCategory.INVARIANT_SAFETY, RuleCategory.INVARIANT_INTEGRITY},
    False: {RuleCategory.WARRANT_EPISTEMIC},
}


@dataclass
class RuleClassification:
    """Classification of a scientific rule into invariant vs warrant taxonomy.

    Attributes:
        category: INVARIANT_SAFETY | INVARIANT_INTEGRITY | WARRANT_EPISTEMIC.
        enforcement_level: ENFORCED | ADVISORY | SHADOW.
        rationale: Human-readable explanation of WHY this rule belongs in this
            category. This is often more informative than the citation itself.
        composition_with_purpose: Whether this rule's enforceability changes
            under different ResearchPurpose values. Only warrants are purpose-
            sensitive; invariants are always context-insensitive.
    """

    category: RuleCategory = RuleCategory.WARRANT_EPISTEMIC
    enforcement_level: EnforcementLevel = EnforcementLevel.ADVISORY
    rationale: str = ""
    composition_with_purpose: bool = False

    def __post_init__(self) -> None:
        # Derive defaults from category if not explicitly overridden.
        if not self.rationale:
            self.rationale = self._default_rationale()
        if self.category == RuleCategory.INVARIANT_SAFETY:
            self.enforcement_level = EnforcementLevel.ENFORCED
            self.composition_with_purpose = False
        elif self.category == RuleCategory.INVARIANT_INTEGRITY:
            self.enforcement_level = EnforcementLevel.ENFORCED
            self.composition_with_purpose = False
        else:  # WARRANT_EPISTEMIC
            self.composition_with_purpose = True

    def _default_rationale(self) -> str:
        mapping = {
            RuleCategory.INVARIANT_SAFETY: (
                "Hard safety invariant: violating this rule risks patient harm, "
                "regulatory violation, or scientifically invalid output presented "
                "as definitive."
            ),
            RuleCategory.INVARIANT_INTEGRITY: (
                "Hard integrity invariant: violating this rule silently corrupts "
                "data or joins mismatched ontologies, producing garbage results "
                "indistinguishable from correct ones."
            ),
            RuleCategory.WARRANT_EPISTEMIC: (
                "Epistemic warrant constraint: limits what the current evidence "
                "can justify. Execution is legal; claims are capped.",
            ),
        }
        return mapping.get(self.category, "Unclassified constraint.")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "enforcement_level": self.enforcement_level.value,
            "rationale": self.rationale,
            "composition_with_purpose": self.composition_with_purpose,
        }


# ---------------------------------------------------------------------------
# Pre-classified examples mapping to the old PROVENANCE_* records.
# ---------------------------------------------------------------------------

CLASSIFICATION_CLINICAL_DIAGNOSIS = RuleClassification(
    category=RuleCategory.INVARIANT_SAFETY,
    enforcement_level=EnforcementLevel.ENFORCED,
    rationale="CLIA/CAP mandate: clinical diagnosis without certified validation directly impacts patient treatment decisions.",
)

CLASSIFICATION_IDENTIFIER_NAMESPACE = RuleClassification(
    category=RuleCategory.INVARIANT_INTEGRITY,
    enforcement_level=EnforcementLevel.ENFORCED,
    rationale="Data integrity: joining HGNC gene symbols against Ensembl IDs produces silent one-to-many mappings indistinguishable from correct joins.",
)

CLASSIFICATION_MODEL_SUBSTITUTION = RuleClassification(
    category=RuleCategory.INVARIANT_INTEGRITY,
    enforcement_level=EnforcementLevel.ENFORCED,
    rationale="Reproducibility: substituting models without detection breaks deterministic audit trails (BN-F010).",
)

CLASSIFICATION_RAW_COUNTS_DE = RuleClassification(
    category=RuleCategory.WARRANT_EPISTEMIC,
    enforcement_level=EnforcementLevel.ADVISORY,
    rationale="Statistical theory: negative binomial models assume integer counts; feeding normalized floats violates dispersion estimation assumptions, making p-values approximate rather than calibrated.",
    composition_with_purpose=True,
)

CLASSIFICATION_BIOLOGICAL_REPLICATES = RuleClassification(
    category=RuleCategory.WARRANT_EPISTEMIC,
    enforcement_level=EnforcementLevel.ADVISORY,
    rationale="Experimental design theory: biological replication is required to estimate between-subject variance. Without it, population-level effects are confounded with sample-specific noise.",
    composition_with_purpose=True,
)

CLASSIFICATION_SPATIAL_COORDINATES = RuleClassification(
    category=RuleCategory.WARRANT_EPISTEMIC,
    enforcement_level=EnforcementLevel.ADVISORY,
    rationale="Spatial statistics: Moran's I assumes physical adjacency; embedding coordinates proxy for topological similarity which may correlate with but does not equal tissue-level structure.",
    composition_with_purpose=True,
)

CLASSIFICATION_MISSING_BACKEND = RuleClassification(
    category=RuleCategory.INVARIANT_INTEGRITY,
    enforcement_level=EnforcementLevel.ENFORCED,
    rationale="Scientific capability contract: the canonical backend defines the algorithm. Silent substitution means the result is not what was advertised — zero silent substitution policy.",
)


# ---------------------------------------------------------------------------
# Mapping from legacy condition_id strings to classifications.
# ---------------------------------------------------------------------------

_CONDITION_TO_CLASSIFICATION: Dict[str, RuleClassification] = {
    "clinical_diagnosis": CLASSIFICATION_CLINICAL_DIAGNOSIS,
    "identifier_namespace_mismatch": CLASSIFICATION_IDENTIFIER_NAMESPACE,
    "model_substitution": CLASSIFICATION_MODEL_SUBSTITUTION,
    "normalized_matrix_only": CLASSIFICATION_RAW_COUNTS_DE,
    "missing_replicates": CLASSIFICATION_BIOLOGICAL_REPLICATES,
    "min_replicates": CLASSIFICATION_BIOLOGICAL_REPLICATES,
    "spatial_coords_present": CLASSIFICATION_SPATIAL_COORDINATES,
    "embedding_substitution": CLASSIFICATION_SPATIAL_COORDINATES,
    "missing_backend": CLASSIFICATION_MISSING_BACKEND,
}


def classify_condition(condition_id: str) -> Optional[RuleClassification]:
    """Return the RuleClassification for a known condition_id, or None."""
    return _CONDITION_TO_CLASSIFICATION.get(condition_id)


def infer_classifications_from_provenance(
    source_kind: str,
    hard_rule: bool,
    source_citation: str = "",
    exceptions: Optional[List[str]] = None,
) -> RuleClassification:
    """Derive a RuleClassification from legacy provenance fields.

    This preserves backward compatibility: old code passing hard_rule=True
    gets INVARIANT classification; hard_rule=False gets Warrant by default.
    """
    if hard_rule:
        # Heuristic: regulatory mentions → SAFETY; rest → INTEGRITY.
        if any(kw in source_citation.lower() for kw in ("clia", "cap", "fda", "ivdr", "patient", "clinical")):
            cat = RuleCategory.INVARIANT_SAFETY
        else:
            cat = RuleCategory.INVARIANT_INTEGRITY
        return RuleClassification(
            category=cat,
            enforcement_level=EnforcementLevel.ENFORCED,
            rationale=f"Derived from legacy hard_rule=True ({source_kind}).",
        )
    else:
        return RuleClassification(
            category=RuleCategory.WARRANT_EPISTEMIC,
            enforcement_level=EnforcementLevel.ADVISORY,
            rationale=f"Derived from legacy hard_rule=False ({source_kind}).",
        )
