"""
Research Intent / Analysis Purpose Framework.

Upgrades BioNexus from "when not to compute" (binary REFUSED/PERMITTED) to
"what the evidence warrants" (purpose-modulated evidence ceilings).

The same data design can carry different epistemic weight under different
research purposes:

- **Exploratory**: hypothesis-generating; PRELIMINARY / FRAGILE conclusions
  are acceptable as starting points for further investigation.
- **Screening**: cast-a-wide net; tolerates higher false-positive rates but
  MUST NOT claim confirmatory status.
- **Confirmatory**: hypothesis-testing; requires solid statistics, validated
  inputs, and distribution-appropriate methods.
- **Causal**: causal effect estimation; demands experimental or quasi-experimental
  designs, instrumental variables, or explicit causal identification strategies.
- **Clinical**: patient-facing; highest bar — REPLICATED evidence, CLIA/CAP
  context, and regulatory compliance.

Purpose is an *input* to the capability evaluation, not a post-hoc label.
It modulates the evidence ceiling (the highest reachable ConclusionMaturity)
and determines which soft limits can be overridden by a researcher.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from bionexus.contracts import ConclusionMaturity


class ResearchPurpose(str, Enum):
    """Research Intent / Analysis Purpose.

    Ordered by increasing epistemic strictness.  Each purpose defines an
    evidence ceiling — the highest ConclusionMaturity reachable without
    external validation or researcher override.

    - UNSPECIFIED: Caller has not declared a purpose. This is NOT exploratory;
      it is a state requiring explicit declaration before purpose-aware routing
      can apply. The evidence ceiling defaults to the most conservative reachable
      level (FRAGILE) until purpose is specified.
    """

    UNSPECIFIED = "unspecified"
    EXPLORATORY = "exploratory"
    SCREENING = "screening"
    CONFIRMATORY = "confirmatory"
    CAUSAL = "causal"
    CLINICAL = "clinical"


# ---------------------------------------------------------------------------
# Evidence ceiling per purpose: the highest ConclusionMaturity reachable
# *without* external validation or explicit researcher override.
# UNSPECIFIED gets FRAGILE as default — the most conservative reachable ceiling.
PURPOSE_EVIDENCE_CEILING: Dict[ResearchPurpose, ConclusionMaturity] = {
    ResearchPurpose.UNSPECIFIED: ConclusionMaturity.FRAGILE,
    ResearchPurpose.EXPLORATORY: ConclusionMaturity.PRELIMINARY,
    ResearchPurpose.SCREENING: ConclusionMaturity.PRELIMINARY,
    ResearchPurpose.CONFIRMATORY: ConclusionMaturity.ROBUST,
    ResearchPurpose.CAUSAL: ConclusionMaturity.SUPPORTED,
    ResearchPurpose.CLINICAL: ConclusionMaturity.REPLICATED,
}

# ---------------------------------------------------------------------------
# Which purposes can a researcher override soft blocks for?
# Clinical and Unspecified purpose NEVER permit override.
# Patient safety invariant + need for explicit purpose specification.
OVERRIDABLE_PURPOSES: Set[ResearchPurpose] = {
    ResearchPurpose.EXPLORATORY,
    ResearchPurpose.SCREENING,
    ResearchPurpose.CONFIRMATORY,
    ResearchPurpose.CAUSAL,
}


# ---------------------------------------------------------------------------
# Keyword patterns for automatic purpose inference from user queries.
# ---------------------------------------------------------------------------

_PURPOSE_PATTERNS: Dict[ResearchPurpose, List[str]] = {
    ResearchPurpose.CLINICAL: [
        r"clinical\s+(?:diagnostic|decision|trial|endpoint|biomarker)",
        r"patient\s+(?:outcome|treatment|stratification|management)",
        r"companion\s+diagnostic",
        r"fda\s+(?:approval|cleared|authorized)",
        r"clia|cap\s+validated",
        r"therapeutic\s+(?:recommendation|decision)",
    ],
    ResearchPurpose.CAUSAL: [
        r"causal\s+(?:effect|inference|identification|mechanism)",
        r"(?:instrumental\s+variable|difference.in.differences|regression\s+discontinuity)",
        r"do[- ]calculus",
        r"counterfactual",
        r"treatment\s+effect\s+(?:estimation|heterogeneity)",
        r"cause\s+and\s+effect",
    ],
    ResearchPurpose.CONFIRMATORY: [
        r"(?:confirm|hypothesis[- ]test|validate|replicate)\s+(?:that|whether|if)",
        r"pre[- ]registered",
        r"primary\s+(?:endpoint|outcome|hypothesis)",
        r"statistical\s+(?:power|significance|testing)",
        r"wald\s+test",
        r"(?:bonferroni|fdr|benjamini)",
    ],
    ResearchPurpose.SCREENING: [
        r"(?:screen|scan|survey|discovery)\s+(?:for|for\s+candidate)",
        r"candidate\s+(?:gene|marker|feature|drug)",
        r"hypothesis[- ]generating",
        r"exploratory\s+screen",
        r"rank\s+(?:the\s+)?(?:top|all|candidates)",
    ],
    ResearchPurpose.EXPLORATORY: [
        r"(?:explore|look\s+at|investigate|examine|characterize|profile)",
        r"(?:what|which)\s+(?:are|is)\s+the\s+(?:main|top|dominant)",
        r"preliminary\s+(?:analysis|investigation|look)",
        r"get\s+(?:a\s+)?(?:sense|overview|picture)\s+of",
        r"quality\s+control",
        r"umap|tsne|pca",
    ],
}


def infer_research_purpose(query: str) -> ResearchPurpose:
    """Infer the research purpose from the user's query text.

    Scans for keyword patterns ordered by epistemic strictness (clinical > causal >
    confirmatory > screening > exploratory).  Falls back to UNSPECIFIED when no
    specific pattern fires — this deliberately refuses to assume exploratory on behalf
    of the caller. The absence of declared purpose means UNSPECIFIED, which caps
    evidence at FRAGILE until the user explicitly states their intent.

    IMPORTANT CHANGE from old behavior: previously fell back to EXPLORATORY. This
    gave the inference engine too much power. Now the default is UNSPECIFIED, which
    forces callers to declare their purpose if they want higher ceilings.
    """
    query_lower = query.lower()
    # Check in strictness order: clinical first, unspecified last.
    for purpose in (
        ResearchPurpose.CLINICAL,
        ResearchPurpose.CAUSAL,
        ResearchPurpose.CONFIRMATORY,
        ResearchPurpose.SCREENING,
        ResearchPurpose.EXPLORATORY,
    ):
        for pattern in _PURPOSE_PATTERNS.get(purpose, []):
            if re.search(pattern, query_lower):
                return purpose
    return ResearchPurpose.UNSPECIFIED


# ---------------------------------------------------------------------------
# PurposeContext: the full purpose specification for a routing decision.
# ---------------------------------------------------------------------------


@dataclass
class PurposeContext:
    """Research purpose context for a capability evaluation.

    Attributes:
        purpose: The declared or inferred research purpose.
        explicitly_declared: True if the caller specified the purpose directly;
            False if it was inferred from the query text OR defaulted to UNSPECIFIED.
        override_active: True when a researcher has invoked an explicit override
            to proceed past a soft block.
        override_justification: Free-text reason recorded when override is active.
    """

    purpose: ResearchPurpose = ResearchPurpose.UNSPECIFIED
    explicitly_declared: bool = False
    override_active: bool = False
    override_justification: str = ""

    @property
    def evidence_ceiling(self) -> ConclusionMaturity:
        """The highest ConclusionMaturity reachable under this purpose."""
        return PURPOSE_EVIDENCE_CEILING.get(
            self.purpose, ConclusionMaturity.PRELIMINARY
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "purpose": self.purpose.value,
            "explicitly_declared": self.explicitly_declared,
            "override_active": self.override_active,
            "override_justification": self.override_justification,
            "evidence_ceiling": self.evidence_ceiling.value,
        }


def purpose_from_string(value: str) -> ResearchPurpose:
    """Convert a string to a ResearchPurpose, with validation."""
    try:
        return ResearchPurpose(value.lower().strip())
    except ValueError:
        valid = ", ".join(p.value for p in ResearchPurpose)
        raise ValueError(
            f"Unknown research purpose '{value}'. Valid purposes: {valid}"
        )
