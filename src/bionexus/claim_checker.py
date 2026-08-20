"""
BioNexus Prohibited Claims & Scientific Hallucination Verification Engine.

Audits agent responses, scientific reports, and result artifacts against
non-negotiable scientific honesty invariants:
1. Unverified Cell-Type Hallucinations (Numeric clusters -> Specific cell-type claims without reference).
2. False Causal Treatment DE Claims (Marker p-values -> Treatment causal effects).
3. False Regulatory / GxP Compliance Claims (Part 11 / CLIA / CAP certification overclaims).
4. Machine Learning Backend Substitutions (BLOSUM heuristics -> ESM-2 / AlphaFold claims).
5. Survival Hazard Ratio Overclaims (Empirical event rates -> Cox Hazard Ratios).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ClaimViolationType(str, Enum):
    """Types of scientific prohibited claim violations."""

    CELL_TYPE_HALLUCINATION = "CELL_TYPE_HALLUCINATION"
    CAUSAL_TREATMENT_DE_OVERCLAIM = "CAUSAL_TREATMENT_DE_OVERCLAIM"
    REGULATORY_COMPLIANCE_OVERCLAIM = "REGULATORY_COMPLIANCE_OVERCLAIM"
    MODEL_SUBSTITUTION_OVERCLAIM = "MODEL_SUBSTITUTION_OVERCLAIM"
    SURVIVAL_HAZARD_OVERCLAIM = "SURVIVAL_HAZARD_OVERCLAIM"
    PROHIBITED_CLAIM_MATCH = "PROHIBITED_CLAIM_MATCH"


@dataclass
class ClaimViolation:
    """A detected prohibited claim violation in text or result artifact."""

    violation_type: ClaimViolationType
    matched_text: str
    rule_description: str
    remedy: str
    severity: str = "FATAL"  # "FATAL" | "ADVISORY"


@dataclass
class ClaimAuditResult:
    """Summary of prohibited claims evaluation."""

    passed: bool
    violations: List[ClaimViolation] = field(default_factory=list)
    violation_count: int = 0
    clean_text: Optional[str] = None
    audit_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "violation_count": self.violation_count,
            "violations": [
                {
                    "type": v.violation_type.value,
                    "matched_text": v.matched_text,
                    "rule": v.rule_description,
                    "remedy": v.remedy,
                    "severity": v.severity,
                }
                for v in self.violations
            ],
            "audit_notes": self.audit_notes,
        }


# ==============================================================================
# Canonical Prohibited Claim Patterns
# ==============================================================================

# 1. Unverified Cell-Type Assertion Patterns
# Matches: "Cluster 0 is CD4+ T cell", "Cluster 1 represents B-cell", "Cluster 2: Macrophages"
_CELL_TYPES_REGEX = (
    r"(cd[48]\+?\s*(?:t\s*cell|t-cell|t\s*lymphocyte)?|"
    r"t\s*(?:helper|regulatory|reg|cytotoxic)?\s*(?:cell|lymphocyte)?|"
    r"b\s*(?:cell|lymphocyte)?|plasma\s*cell|"
    r"natural\s*killer|nk\s*cell|"
    r"macrophage|monocyte|dendritic\s*cell|microglia|"
    r"neutrophil|granulocyte|erythrocyte|platelet|"
    r"astrocyte|oligodendrocyte|neuron|cardiomyocyte|fibroblast|endothelial)"
)

_CELL_TYPE_ASSERTION_PATTERNS = [
    re.compile(
        rf"\bcluster\s*\d+\s*(?:is|represents|corresponds\s*to|identified\s*as|assigned\s*as|defines)\s*(?:a|an|the)?\s*{_CELL_TYPES_REGEX}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bcluster\s*\d+\s*:\s*{_CELL_TYPES_REGEX}\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bconcluded?\s*that\s*cluster\s*\d+\s*(?:is|are)\s*{_CELL_TYPES_REGEX}\b",
        re.IGNORECASE,
    ),
]

# 2. Causal Treatment DE Claims from rank_genes_groups / cell markers / observational scRNA
_CAUSAL_DE_PATTERNS = [
    re.compile(
        r"\b(?:rank_genes_groups|marker\s*genes?|marker\s*p-?values?)\s*(?:(?:proves?|demonstrates?|confirms?)(?:\s*that)?)\s*(?:(?:drug|treatment|compound|condition)\s*)+(?:caused|induced|altered|triggered)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:rank_genes_groups|marker\s*p-?values?)\s+.*?\b(?:proves?|proves\s*that|caused|treatment\s*effect)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:caused|induced)\s*\d+\s*(?:differential(?:ly)?\s*expressed\s*genes|degs|genes)\s*(?:without\s*replicates|at\s*single-cell\s*level|from\s*marker)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:proves?|establishes?|confirms?)\s+(?:a\s+)?causal\s+(?:mechanism|relationship|link|role|effect)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bcausally\s+(?:drives?|induced?|altered?|repressed?|activated?)\s+(?:the\s+)?(?:disease|phenotype|condition|expression)\b",
        re.IGNORECASE,
    ),
]

# 3. Regulatory / GxP Overclaims
_REGULATORY_PATTERNS = [
    re.compile(
        r"\b(?:fda\s*)?(?:21\s*cfr\s*part\s*11|gxp|clia|cap|ivdr)\s*(?:compliant|certified|approved|validated|guaranteed)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:valid|certified)\s*for\s*(?:clinical\s*diagnos(?:is|tic)|patient\s*treatment\s*decisions)\b",
        re.IGNORECASE,
    ),
]

# 4. Model Substitution Overclaims
_MODEL_SUBSTITUTION_PATTERNS = [
    re.compile(
        r"\b(?:esm-?2|alphafold|protbert)\s*(?:embedding|prediction|score)\s*(?:computed\s*via|using)\s*(?:blosum|local\s*heuristic|substitution\s*matrix)\b",
        re.IGNORECASE,
    ),
]

# 5. Survival Hazard Ratio Overclaims
_SURVIVAL_HAZARD_PATTERNS = [
    re.compile(
        r"\bhazard\s*ratio\s*(?:of\s*[\d\.]+|is\s*[\d\.]+)\s*(?:without\s*cox|from\s*event\s*counts?|from\s*empirical\s*frequency)\b",
        re.IGNORECASE,
    ),
]


def audit_prohibited_claims(
    text: str,
    *,
    capability_id: Optional[str] = None,
    custom_prohibited_patterns: Optional[List[str]] = None,
    allow_unverified_cell_types: bool = False,
    allow_regulatory_claims: bool = False,
) -> ClaimAuditResult:
    """
    Audit response text or scientific report artifact for prohibited claims.

    Parameters:
        text: Response markdown, text, or report content to evaluate.
        capability_id: Optional CapabilityContract ID to apply domain-specific filters.
        custom_prohibited_patterns: Optional custom regex strings to prohibit.
        allow_unverified_cell_types: Set true only if ground truth reference mapping was verified.
        allow_regulatory_claims: Set true only if formal clinical validation metadata is present.
    """
    violations: List[ClaimViolation] = []
    notes: List[str] = []

    # 1. Check Unverified Cell-Type Hallucinations
    if not allow_unverified_cell_types:
        for pat in _CELL_TYPE_ASSERTION_PATTERNS:
            for match in pat.finditer(text):
                matched = match.group(0)
                # Ignore if explicitly qualified with candidate / putative / unverified
                surrounding = text[max(0, match.start() - 30) : min(len(text), match.end() + 30)].lower()
                if any(
                    q in surrounding for q in ("candidate", "putative", "unverified", "hypothesized", "exploratory")
                ):
                    continue

                violations.append(
                    ClaimViolation(
                        violation_type=ClaimViolationType.CELL_TYPE_HALLUCINATION,
                        matched_text=matched,
                        rule_description="Single-cell clusters must remain numeric unless verified against ground truth reference markers.",
                        remedy="Refer to clusters numerically (e.g. 'Cluster 0') or explicitly qualify as putative/exploratory candidates.",
                    )
                )

    # 2. Check Causal DE Overclaims
    for pat in _CAUSAL_DE_PATTERNS:
        for match in pat.finditer(text):
            matched = match.group(0)
            surrounding = text[max(0, match.start() - 30) : min(len(text), match.end() + 30)].lower()
            if any(
                neg in surrounding
                for neg in ("cannot", "can not", "does not", "do not", "never", "not prove", "unable")
            ):
                continue

            violations.append(
                ClaimViolation(
                    violation_type=ClaimViolationType.CAUSAL_TREATMENT_DE_OVERCLAIM,
                    matched_text=matched,
                    rule_description="Marker p-values from rank_genes_groups cannot be cited as causal treatment condition DE p-values.",
                    remedy="Perform pseudobulk sample aggregation and run PyDESeq2 Wald/LRT tests with biological replicates.",
                )
            )

    # 3. Check Regulatory Compliance Overclaims
    if not allow_regulatory_claims:
        for pat in _REGULATORY_PATTERNS:
            for match in pat.finditer(text):
                matched = match.group(0)
                # Check if accompanied by Research Use Only disclaimer in text
                if "research use only" not in text.lower() and "ruo" not in text.lower():
                    violations.append(
                        ClaimViolation(
                            violation_type=ClaimViolationType.REGULATORY_COMPLIANCE_OVERCLAIM,
                            matched_text=matched,
                            rule_description="BioNexus outputs must never claim FDA Part 11, GxP, CLIA, or CAP certification without mandatory RUO disclaimers.",
                            remedy="Include mandatory Research Use Only (RUO) and non-diagnostic disclaimers.",
                        )
                    )

    # 4. Check Model Substitution Overclaims
    for pat in _MODEL_SUBSTITUTION_PATTERNS:
        for match in pat.finditer(text):
            violations.append(
                ClaimViolation(
                    violation_type=ClaimViolationType.MODEL_SUBSTITUTION_OVERCLAIM,
                    matched_text=match.group(0),
                    rule_description="Local BLOSUM/heuristic substitutions must not be labeled as ESM-2 or AlphaFold deep learning models.",
                    remedy="Accurately report algorithm as BLOSUM substitution matrix or heuristic.",
                )
            )

    # 5. Check Survival Hazard Ratio Overclaims
    for pat in _SURVIVAL_HAZARD_PATTERNS:
        for match in pat.finditer(text):
            violations.append(
                ClaimViolation(
                    violation_type=ClaimViolationType.SURVIVAL_HAZARD_OVERCLAIM,
                    matched_text=match.group(0),
                    rule_description="Hazard ratios require Cox proportional hazards estimation via lifelines, not empirical event ratios.",
                    remedy="Report empirical event rate ratio or fit lifelines CoxPHFitter.",
                )
            )

    # 6. Custom Prohibited Patterns
    if custom_prohibited_patterns:
        for custom_pat in custom_prohibited_patterns:
            c_re = re.compile(custom_pat, re.IGNORECASE)
            for match in c_re.finditer(text):
                violations.append(
                    ClaimViolation(
                        violation_type=ClaimViolationType.PROHIBITED_CLAIM_MATCH,
                        matched_text=match.group(0),
                        rule_description=f"Matched custom prohibited pattern: '{custom_pat}'",
                        remedy="Remove prohibited claim phrasing from response.",
                    )
                )

    passed = len(violations) == 0
    if passed:
        notes.append("No prohibited claims detected. Text complies with scientific honesty invariants.")
    else:
        notes.append(f"Detected {len(violations)} prohibited claim violation(s).")

    return ClaimAuditResult(
        passed=passed,
        violations=violations,
        violation_count=len(violations),
        clean_text=text,
        audit_notes=notes,
    )
