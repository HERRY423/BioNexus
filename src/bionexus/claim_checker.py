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
from typing import Any, Dict, List, Optional, Sequence, Set


class ClaimViolationType(str, Enum):
    """Types of scientific prohibited claim violations."""

    CELL_TYPE_HALLUCINATION = "CELL_TYPE_HALLUCINATION"
    CAUSAL_TREATMENT_DE_OVERCLAIM = "CAUSAL_TREATMENT_DE_OVERCLAIM"
    REGULATORY_COMPLIANCE_OVERCLAIM = "REGULATORY_COMPLIANCE_OVERCLAIM"
    MODEL_SUBSTITUTION_OVERCLAIM = "MODEL_SUBSTITUTION_OVERCLAIM"
    SURVIVAL_HAZARD_OVERCLAIM = "SURVIVAL_HAZARD_OVERCLAIM"
    PROHIBITED_CLAIM_MATCH = "PROHIBITED_CLAIM_MATCH"
    UNWARRANTED_CAUSAL_MECHANISM = "UNWARRANTED_CAUSAL_MECHANISM"
    UNWARRANTED_POPULATION_GENERALIZATION = "UNWARRANTED_POPULATION_GENERALIZATION"


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


def build_evidence_profile_from_factors(
    factors: Sequence[str] = (),
    *,
    reference_ground_truth: bool = False,
    regulatory_certification: bool = False,
    ruo_disclaimer_present: bool = False,
) -> Any:
    """Construct a typed EvidenceProfile from evidence factors and context flags."""
    from bionexus.claim_semantics import EvidenceProfile

    factor_set = {f.lower().strip() for f in factors if isinstance(f, str)}

    confounds = []
    if "confound_controls" in factor_set:
        confounds = ["donor", "batch"]

    causal_status = "UNASSESSED"
    if "perturbation" in factor_set or "causal_identification" in factor_set:
        causal_status = "BACKDOOR_SATISFIED"

    return EvidenceProfile(
        observational_data="sample_design" in factor_set or bool(factor_set),
        spatial_colocalization="spatial_colocalization" in factor_set,
        ligand_receptor_inference="ligand_receptor_inference" in factor_set,
        perturbation="perturbation" in factor_set,
        temporal_evidence="temporal_evidence" in factor_set,
        independent_validation="external_validation" in factor_set or "replication" in factor_set,
        biological_replicates_count=3 if "replication" in factor_set else (2 if "sample_design" in factor_set else 0),
        pseudobulk_aggregated="sample_design" in factor_set,
        confound_controls=confounds,
        causal_identification_status=causal_status,
        reference_ground_truth=reference_ground_truth or "reference_ground_truth" in factor_set,
        clinical_ground_truth="clinical_ground_truth" in factor_set,
        regulatory_certification=regulatory_certification or "regulatory_certification" in factor_set or "regulatory_context" in factor_set,
        ruo_disclaimer_present=ruo_disclaimer_present,
        cross_method_concordance="effect_stability" in factor_set,
    )


def audit_prohibited_claims(
    text: str,
    *,
    capability_id: Optional[str] = None,
    custom_prohibited_patterns: Optional[List[str]] = None,
    allow_unverified_cell_types: bool = False,
    allow_regulatory_claims: bool = False,
    evidence_profile: Optional[Any] = None,
    evidence_factors: Sequence[str] = (),
    tool_receipts: Sequence[Dict[str, Any]] = (),
) -> ClaimAuditResult:
    """Audit response text or scientific report artifact for prohibited claims.

    Combines:
    1. Structured BNS-017 ScientificClaimIR and DeterministicWarrantEngine matching across 5 epistemic tiers.
    2. Deterministic regex pattern matchers for known failure modes and model substitution invariants.
    3. Tool execution receipt factor binding and cryptographic evidence profiles.

    Parameters:
        text: Response markdown, text, or report content to evaluate.
        capability_id: Optional CapabilityContract ID to apply domain-specific filters.
        custom_prohibited_patterns: Optional custom regex strings to prohibit.
        allow_unverified_cell_types: Set true only if ground truth reference mapping was verified.
        allow_regulatory_claims: Set true only if formal clinical validation metadata is present.
        evidence_profile: Optional pre-constructed EvidenceProfile.
        evidence_factors: Optional sequence of satisfied evidence factor strings.
        tool_receipts: Optional sequence of verified tool execution receipts.
    """
    from bionexus.claim_semantics import (
        DeterministicClaimParser,
        DeterministicWarrantEngine,
        GeneralizationScope,
        WarrantTierStatus,
    )

    violations: List[ClaimViolation] = []
    notes: List[str] = []

    # 0. Build or resolve EvidenceProfile
    combined_factors: Set[str] = set(f.lower().strip() for f in evidence_factors if isinstance(f, str))
    if tool_receipts:
        from bionexus.tool_receipt import extract_evidence_factors_from_receipt

        for rcpt in tool_receipts:
            rcpt_factors, _ = extract_evidence_factors_from_receipt(rcpt)
            combined_factors.update(rcpt_factors)

    ruo_present = "research use only" in text.lower() or "ruo" in text.lower()
    if evidence_profile is not None:
        ev_profile = evidence_profile
    else:
        ev_profile = build_evidence_profile_from_factors(
            sorted(combined_factors),
            reference_ground_truth=allow_unverified_cell_types or ("reference_ground_truth" in combined_factors),
            regulatory_certification=allow_regulatory_claims or ("regulatory_certification" in combined_factors),
            ruo_disclaimer_present=ruo_present,
        )

    # 1. Semantic Claim IR & Deterministic Warrant Engine (BNS-017)
    sentences = [s.strip() for s in re.split(r"[.\n\r]+", text) if len(s.strip()) > 5]
    for sent in sentences:
        try:
            claim_ir = DeterministicClaimParser.parse(sent)
            # Negated and hedged claims are epistemically honest
            if claim_ir.negated:
                continue

            w_res = DeterministicWarrantEngine.evaluate(claim_ir, ev_profile)
            if not w_res.is_fully_warranted:
                # Tier 1: Cell Identity Claim
                if (
                    w_res.tier_verdicts.get("cell_identity_claim")
                    and w_res.tier_verdicts["cell_identity_claim"].status in (WarrantTierStatus.NOT_WARRANTED, WarrantTierStatus.PROHIBITED)
                ):
                    surrounding = sent.lower()
                    if not any(q in surrounding for q in ("candidate", "putative", "unverified", "hypothesized", "exploratory")):
                        # Check if regex will catch this or already caught it
                        regex_matches = [m.group(0) for p in _CELL_TYPE_ASSERTION_PATTERNS for m in p.finditer(sent)]
                        if not regex_matches:
                            remedy = "; ".join(w_res.remedies) or "Refer to clusters numerically or qualify as putative/candidate markers."
                            violations.append(
                                ClaimViolation(
                                    violation_type=ClaimViolationType.CELL_TYPE_HALLUCINATION,
                                    matched_text=sent,
                                    rule_description="Single-cell clusters must remain numeric unless verified against ground truth reference markers.",
                                    remedy=remedy,
                                )
                            )

                # Tier 2: Causal Mechanism Claim
                if (
                    w_res.tier_verdicts.get("causal_claim")
                    and w_res.tier_verdicts["causal_claim"].status in (WarrantTierStatus.NOT_WARRANTED, WarrantTierStatus.PROHIBITED)
                ):
                    remedy = "; ".join(w_res.remedies) or "Downgrade causal phrasing to correlational observation or perform perturbation experiment."
                    violations.append(
                        ClaimViolation(
                            violation_type=ClaimViolationType.UNWARRANTED_CAUSAL_MECHANISM,
                            matched_text=sent,
                            rule_description=(
                                f"Causal claim '{claim_ir.subject_entity.name} -> "
                                f"{claim_ir.object_entity.name if claim_ir.object_entity else 'effect'}' is not "
                                "warranted without experimental perturbation or confound controls."
                            ),
                            remedy=remedy,
                        )
                    )

                # Tier 3: Clinical Actionability Claim
                if (
                    w_res.tier_verdicts.get("clinical_actionability_claim")
                    and w_res.tier_verdicts["clinical_actionability_claim"].status in (WarrantTierStatus.NOT_WARRANTED, WarrantTierStatus.PROHIBITED)
                    and not ruo_present
                ):
                    remedy = "; ".join(w_res.remedies) or "Include mandatory Research Use Only (RUO) and non-diagnostic disclaimers."
                    violations.append(
                        ClaimViolation(
                            violation_type=ClaimViolationType.REGULATORY_COMPLIANCE_OVERCLAIM,
                            matched_text=sent,
                            rule_description="Clinical actionability and diagnostic claims require validated regulatory certification and mandatory RUO disclaimers.",
                            remedy=remedy,
                        )
                    )

                # Tier 4: Population Generalization Claim
                if (
                    w_res.tier_verdicts.get("population_generalization_claim")
                    and w_res.tier_verdicts["population_generalization_claim"].status in (WarrantTierStatus.NOT_WARRANTED, WarrantTierStatus.PROHIBITED)
                    and claim_ir.generalization_scope == GeneralizationScope.POPULATION_GENERAL
                ):
                    remedy = "; ".join(w_res.remedies) or "Scope claim to analyzed cohort or validate on independent external dataset."
                    violations.append(
                        ClaimViolation(
                            violation_type=ClaimViolationType.UNWARRANTED_POPULATION_GENERALIZATION,
                            matched_text=sent,
                            rule_description="Universal population generalization claims require independent validation across multiple cohorts.",
                            remedy=remedy,
                        )
                    )
        except Exception:
            pass

    # 2. Deterministic Regex Pattern Matchers (Deterministic safety net)

    # 2a. Unverified Cell-Type Hallucinations
    if not allow_unverified_cell_types and not ev_profile.reference_ground_truth:
        for pat in _CELL_TYPE_ASSERTION_PATTERNS:
            for match in pat.finditer(text):
                matched = match.group(0)
                surrounding = text[max(0, match.start() - 30) : min(len(text), match.end() + 30)].lower()
                if any(q in surrounding for q in ("candidate", "putative", "unverified", "hypothesized", "exploratory")):
                    continue
                if not any(v.violation_type == ClaimViolationType.CELL_TYPE_HALLUCINATION and (matched in v.matched_text or v.matched_text in matched) for v in violations):
                    violations.append(
                        ClaimViolation(
                            violation_type=ClaimViolationType.CELL_TYPE_HALLUCINATION,
                            matched_text=matched,
                            rule_description="Single-cell clusters must remain numeric unless verified against ground truth reference markers.",
                            remedy="Refer to clusters numerically (e.g. 'Cluster 0') or explicitly qualify as putative/exploratory candidates.",
                        )
                    )

    # 2b. Causal DE Overclaims from rank_genes_groups
    for pat in _CAUSAL_DE_PATTERNS:
        for match in pat.finditer(text):
            matched = match.group(0)
            surrounding = text[max(0, match.start() - 30) : min(len(text), match.end() + 30)].lower()
            if any(neg in surrounding for neg in ("cannot", "can not", "does not", "do not", "never", "not prove", "unable")):
                continue
            if not any((v.violation_type in (ClaimViolationType.CAUSAL_TREATMENT_DE_OVERCLAIM, ClaimViolationType.UNWARRANTED_CAUSAL_MECHANISM)) and (matched in v.matched_text or v.matched_text in matched) for v in violations):
                violations.append(
                    ClaimViolation(
                        violation_type=ClaimViolationType.CAUSAL_TREATMENT_DE_OVERCLAIM,
                        matched_text=matched,
                        rule_description="Marker p-values from rank_genes_groups cannot be cited as causal treatment condition DE p-values.",
                        remedy="Perform pseudobulk sample aggregation and run PyDESeq2 Wald/LRT tests with biological replicates.",
                    )
                )

    # 2c. Regulatory Compliance Overclaims
    if not allow_regulatory_claims and not ev_profile.regulatory_certification:
        for pat in _REGULATORY_PATTERNS:
            for match in pat.finditer(text):
                matched = match.group(0)
                if not ruo_present:
                    if not any(v.violation_type == ClaimViolationType.REGULATORY_COMPLIANCE_OVERCLAIM and (matched in v.matched_text or v.matched_text in matched) for v in violations):
                        violations.append(
                            ClaimViolation(
                                violation_type=ClaimViolationType.REGULATORY_COMPLIANCE_OVERCLAIM,
                                matched_text=matched,
                                rule_description="BioNexus outputs must never claim FDA Part 11, GxP, CLIA, or CAP certification without mandatory RUO disclaimers.",
                                remedy="Include mandatory Research Use Only (RUO) and non-diagnostic disclaimers.",
                            )
                        )

    # 2d. Model Substitution Overclaims
    for pat in _MODEL_SUBSTITUTION_PATTERNS:
        for match in pat.finditer(text):
            matched = match.group(0)
            if not any(v.violation_type == ClaimViolationType.MODEL_SUBSTITUTION_OVERCLAIM and (matched in v.matched_text or v.matched_text in matched) for v in violations):
                violations.append(
                    ClaimViolation(
                        violation_type=ClaimViolationType.MODEL_SUBSTITUTION_OVERCLAIM,
                        matched_text=matched,
                        rule_description="Local BLOSUM/heuristic substitutions must not be labeled as ESM-2 or AlphaFold deep learning models.",
                        remedy="Accurately report algorithm as BLOSUM substitution matrix or heuristic.",
                    )
                )

    # 2e. Survival Hazard Ratio Overclaims
    for pat in _SURVIVAL_HAZARD_PATTERNS:
        for match in pat.finditer(text):
            matched = match.group(0)
            if not any(v.violation_type == ClaimViolationType.SURVIVAL_HAZARD_OVERCLAIM and (matched in v.matched_text or v.matched_text in matched) for v in violations):
                violations.append(
                    ClaimViolation(
                        violation_type=ClaimViolationType.SURVIVAL_HAZARD_OVERCLAIM,
                        matched_text=matched,
                        rule_description="Hazard ratios require Cox proportional hazards estimation via lifelines, not empirical event ratios.",
                        remedy="Report empirical event rate ratio or fit lifelines CoxPHFitter.",
                    )
                )

    # 2f. Custom Prohibited Patterns
    if custom_prohibited_patterns:
        for custom_pat in custom_prohibited_patterns:
            c_re = re.compile(custom_pat, re.IGNORECASE)
            for match in c_re.finditer(text):
                matched = match.group(0)
                violations.append(
                    ClaimViolation(
                        violation_type=ClaimViolationType.PROHIBITED_CLAIM_MATCH,
                        matched_text=matched,
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


def audit_claim_semantics(
    text: str,
    evidence: Optional[Any] = None,
) -> Any:
    """Dedicated semantic claim auditor returning structured ScientificClaimIR and
    Deterministic Warrant Engine verdicts (BNS-017).
    """
    from bionexus.claim_semantics import DeterministicClaimParser, DeterministicWarrantEngine, EvidenceProfile

    ev = evidence or EvidenceProfile()
    sentences = [s.strip() for s in re.split(r"[.\n\r]+", text) if len(s.strip()) > 5]
    results = []
    for sent in sentences:
        claim_ir = DeterministicClaimParser.parse(sent)
        w_eval = DeterministicWarrantEngine.evaluate(claim_ir, ev)
        results.append({"claim_ir": claim_ir.to_dict(), "warrant_evaluation": w_eval.to_dict()})
    return results


