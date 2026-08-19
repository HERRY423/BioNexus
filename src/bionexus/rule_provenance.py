"""
Scientific Rule Provenance, Consensus Level, and Exceptions.

BioNexus preconditions and refusal triggers should never look like the project
authors invented scientific law out of thin air.  Every scientific rule carries
explicit provenance metadata:

- **source**: Where the rule comes from (textbook, landmark paper, community
  guideline, statistical theory, or project-internal invariant).
- **consensus_level**: How broadly the rule is accepted (ESTABLISHED, STRONG,
  EMERGING, DEBATED, PROJECT_INTERNAL).
- **exceptions**: Known situations where the rule does not apply or is relaxed.
- **last_verified**: When the rule was last checked against the literature.

This module also classifies rules into hard vs soft:

- **hard rules** are safety invariants that cannot be overridden (e.g. clinical
  diagnosis without certification, identifier namespace corruption).
- **soft rules** are methodological guidelines that can be relaxed under an
  explicit researcher override with documented limitations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ConsensusLevel(str, Enum):
    """How broadly a scientific rule is accepted in the relevant community.

    - ESTABLISHED: Textbook-level consensus; no serious dissent.
    - STRONG: Strong majority support; dissent exists but is minority.
    - EMERGING: Active research area; the rule reflects current best practice
      but may evolve.
    - DEBATED: Meaningful disagreement in the community; the rule represents
      one defensible position, not a universal law.
    - PROJECT_INTERNAL: A BioNexus project invariant (e.g. honesty policy);
      not a scientific claim about the natural world.
    """

    ESTABLISHED = "ESTABLISHED"
    STRONG = "STRONG"
    EMERGING = "EMERGING"
    DEBATED = "DEBATED"
    PROJECT_INTERNAL = "PROJECT_INTERNAL"


class RuleSourceKind(str, Enum):
    """The kind of source a scientific rule derives from."""

    TEXTBOOK = "textbook"
    LANDMARK_PAPER = "landmark_paper"
    COMMUNITY_GUIDELINE = "community_guideline"
    STATISTICAL_THEORY = "statistical_theory"
    REGULATORY = "regulatory"
    PROJECT_INVARIANT = "project_invariant"
    BEST_PRACTICE = "best_practice"


@dataclass
class RuleProvenance:
    """Provenance metadata for a scientific rule (precondition or refusal trigger).

    Attributes:
        source_kind: What kind of source the rule derives from.
        source_citation: Human-readable citation or description of the source.
        consensus: How broadly the rule is accepted.
        exceptions: Known situations where the rule does not apply.
        last_verified: ISO date string of when the rule was last verified against
            the literature (e.g. "2025-06").
        hard_rule: Whether this rule is a hard safety invariant (never overridable)
            or a soft methodological guideline (overridable with documentation).
    """

    source_kind: RuleSourceKind = RuleSourceKind.BEST_PRACTICE
    source_citation: str = ""
    consensus: ConsensusLevel = ConsensusLevel.STRONG
    exceptions: List[str] = field(default_factory=list)
    last_verified: str = ""
    hard_rule: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_kind": self.source_kind.value,
            "source_citation": self.source_citation,
            "consensus": self.consensus.value,
            "exceptions": self.exceptions,
            "last_verified": self.last_verified,
            "hard_rule": self.hard_rule,
        }


# ---------------------------------------------------------------------------
# Pre-built provenance records for common BioNexus rules.
# Skills and capability contracts reference these instead of restating them.
# ---------------------------------------------------------------------------

# --- Hard rules (never overridable) ---

PROVENANCE_CLINICAL_DIAGNOSIS = RuleProvenance(
    source_kind=RuleSourceKind.REGULATORY,
    source_citation="CLIA/CAP regulations; EU IVDR 2017/746; FDA 21 CFR Part 11",
    consensus=ConsensusLevel.ESTABLISHED,
    exceptions=[],
    last_verified="2025-06",
    hard_rule=True,
)

PROVENANCE_IDENTIFIER_NAMESPACE = RuleProvenance(
    source_kind=RuleSourceKind.STATISTICAL_THEORY,
    source_citation="Data integrity invariant: joining mismatched namespaces corrupts all downstream results (BN-F004)",
    consensus=ConsensusLevel.ESTABLISHED,
    exceptions=["Explicit mapping table provided and recorded in provenance"],
    last_verified="2025-06",
    hard_rule=True,
)

PROVENANCE_MODEL_SUBSTITUTION = RuleProvenance(
    source_kind=RuleSourceKind.PROJECT_INVARIANT,
    source_citation="BioNexus honesty policy (BNS-EF-002, BN-F010): never present heuristic output as canonical backend results",
    consensus=ConsensusLevel.PROJECT_INTERNAL,
    exceptions=[],
    last_verified="2025-06",
    hard_rule=True,
)

# --- Soft rules (overridable with documentation) ---

PROVENANCE_RAW_COUNTS_DE = RuleProvenance(
    source_kind=RuleSourceKind.STATISTICAL_THEORY,
    source_citation="Negative binomial GLM requires integer counts; Love et al. 2014 (DESeq2), Soneson & Robinson 2016 (pseudobulk)",
    consensus=ConsensusLevel.STRONG,
    exceptions=[
        "Exploratory marker ranking with normalized input (ceiling: PRELIMINARY)",
        "Pseudobulk aggregation from log-normalized data with explicit disclaimer",
    ],
    last_verified="2025-06",
    hard_rule=False,
)

PROVENANCE_BIOLOGICAL_REPLICATES = RuleProvenance(
    source_kind=RuleSourceKind.STATISTICAL_THEORY,
    source_citation="Biological replication is required for population-level inference; Fisher 1935, design-based inference",
    consensus=ConsensusLevel.ESTABLISHED,
    exceptions=[
        "Exploratory per-sample descriptive statistics (no population claim)",
        "Screening with explicit 'no inferential claims' disclaimer",
    ],
    last_verified="2025-06",
    hard_rule=False,
)

PROVENANCE_SPATIAL_COORDINATES = RuleProvenance(
    source_kind=RuleSourceKind.LANDMARK_PAPER,
    source_citation="Spatial statistics require physical coordinates; embedding substitution invalidates Moran's I (BN-F009, BNS-II-006)",
    consensus=ConsensusLevel.STRONG,
    exceptions=[
        "Embedding coordinates with explicit spatial justification and FRAGILE ceiling",
    ],
    last_verified="2025-06",
    hard_rule=False,
)

PROVENANCE_ANNOTATION_EVIDENCE = RuleProvenance(
    source_kind=RuleSourceKind.BEST_PRACTICE,
    source_citation="Cell-type labels require evidence support (reference atlas, marker panel); BN-F003",
    consensus=ConsensusLevel.STRONG,
    exceptions=[
        "Numeric cluster labels without biological identity claims",
        "Exploratory annotation with explicit 'candidate only' disclaimer",
    ],
    last_verified="2025-06",
    hard_rule=False,
)

PROVENANCE_MULTIPLE_TESTING = RuleProvenance(
    source_kind=RuleSourceKind.STATISTICAL_THEORY,
    source_citation="Multiple testing correction required when testing >1 hypothesis; Benjamini & Hochberg 1995",
    consensus=ConsensusLevel.ESTABLISHED,
    exceptions=[
        "Single pre-registered hypothesis (no correction needed)",
        "Exploratory ranking without inferential claims",
    ],
    last_verified="2025-06",
    hard_rule=False,
)

PROVENANCE_BACKEND_IDENTITY = RuleProvenance(
    source_kind=RuleSourceKind.PROJECT_INVARIANT,
    source_citation="Backend identity conformance (BNS-EF-012..016, BN-F010): declared == observed, no silent substitution",
    consensus=ConsensusLevel.PROJECT_INTERNAL,
    exceptions=[],
    last_verified="2025-06",
    hard_rule=True,
)


def default_provenance_for_condition_id(condition_id: str) -> Optional[RuleProvenance]:
    """Look up the default provenance for a well-known refusal/precondition ID.

    Returns None for unknown condition IDs (callers should supply their own).
    """
    _MAP = {
        "clinical_diagnosis_without_certification": PROVENANCE_CLINICAL_DIAGNOSIS,
        "treatment_recommendation": PROVENANCE_CLINICAL_DIAGNOSIS,
        "normalized_matrix_only": PROVENANCE_RAW_COUNTS_DE,
        "raw_counts_only": PROVENANCE_RAW_COUNTS_DE,
        "missing_replicates": PROVENANCE_BIOLOGICAL_REPLICATES,
        "min_replicates": PROVENANCE_BIOLOGICAL_REPLICATES,
        "spatial_coords_present": PROVENANCE_SPATIAL_COORDINATES,
        "non_degenerate_geometry": PROVENANCE_SPATIAL_COORDINATES,
        "embedding_substitution": PROVENANCE_SPATIAL_COORDINATES,
        "annotation_source_recorded": PROVENANCE_ANNOTATION_EVIDENCE,
        "negative_markers_evaluated": PROVENANCE_ANNOTATION_EVIDENCE,
        "model_substitution_attempt": PROVENANCE_MODEL_SUBSTITUTION,
        "missing_backend": PROVENANCE_BACKEND_IDENTITY,
    }
    return _MAP.get(condition_id)
