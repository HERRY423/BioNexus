"""
Counterfactual advisory engine for scientific claims warrant progression.
"""

from __future__ import annotations

from typing import Any, Dict, List

from bionexus.claims.models import (
    EvidenceProfile,
    ScientificClaimIR,
    WarrantEvaluationResult,
    WarrantTierStatus,
)
from bionexus.contracts import ConclusionMaturity


def generate_counterfactual_warrant_advice(
    claim: ScientificClaimIR,
    facts: EvidenceProfile,
    evaluation: WarrantEvaluationResult,
) -> List[Dict[str, Any]]:
    """Compute minimal counterfactual evidence delta required to upgrade warrant standing.

    Tells scientists and agents precisely what wet-lab experiments or analytical
    adjustments will promote a FRAGILE/NOT_WARRANTED claim to SUPPORTED or ROBUST.
    """
    advice: List[Dict[str, Any]] = []

    # 1. Check unwarranted tiers
    for tier_name, verdict in evaluation.tier_verdicts.items():
        if not verdict.is_warranted:
            if tier_name == "population_claim":
                advice.append({
                    "target_tier": tier_name,
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.SUPPORTED.value,
                    "missing_facts": {
                        "biological_replicates_count": ">= 3 (currently %d)" % facts.biological_replicates_count,
                        "pseudobulk_aggregated": "True (currently %s)" % str(facts.pseudobulk_aggregated),
                    },
                    "actionable_remediation": (
                        "Collect at least %d additional biological replicate donor(s) and aggregate single-cell counts "
                        "into sample-level pseudobulk before statistical testing (Squair et al. 2021)."
                        % max(1, 3 - facts.biological_replicates_count)
                    ),
                })
            elif tier_name == "causal_claim":
                advice.append({
                    "target_tier": tier_name,
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.ROBUST.value,
                    "missing_facts": {
                        "perturbation": "True (currently False)",
                        "causal_identification_status": "'BACKDOOR_SATISFIED' or 'FRONTDOOR_SATISFIED'",
                    },
                    "actionable_remediation": (
                        "Perform targeted genetic perturbation (CRISPR KO / knockdown) or construct a structural causal DAG "
                        "satisfying Backdoor or Frontdoor criterion to justify counterfactual causal language."
                    ),
                })
            elif tier_name == "mechanistic_claim":
                advice.append({
                    "target_tier": tier_name,
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.SUPPORTED.value,
                    "missing_facts": {
                        "perturbation": "True",
                        "temporal_evidence": "True",
                    },
                    "actionable_remediation": (
                        "Provide functional rescue/inhibition assay data or longitudinal time-series kinetics to prove "
                        "intermediate directional signaling."
                    ),
                })
            elif tier_name == "cell_identity_claim":
                advice.append({
                    "target_tier": tier_name,
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.SUPPORTED.value,
                    "missing_facts": {
                        "reference_ground_truth": "True",
                        "qualifiers": "Include 'putative' or 'candidate'",
                    },
                    "actionable_remediation": (
                        "Map against an established reference atlas (e.g. Azimuth/CellTypist) with CITE-seq/FACS sorting, "
                        "or prepend 'candidate' / 'putative' to marker-inferred labels."
                    ),
                })
            elif tier_name == "clinical_claim":
                advice.append({
                    "target_tier": tier_name,
                    "target_status": WarrantTierStatus.PROHIBITED.value,
                    "target_ceiling": ConclusionMaturity.ABSTAIN.value,
                    "missing_facts": {
                        "regulatory_certification": "CLIA/CAP or FDA approved device",
                    },
                    "actionable_remediation": (
                        "Clinical actionability is strictly prohibited on Research Use Only (RUO) software. "
                        "Restructure claim as exploratory basic biomarker discovery."
                    ),
                })

    # 2. If all tiers are warranted, advise on reaching higher maturity (ROBUST / REPLICATED)
    if evaluation.is_fully_warranted:
        if evaluation.evidence_ceiling == ConclusionMaturity.SUPPORTED.value:
            if not facts.independent_validation:
                advice.append({
                    "target_tier": "overall_maturity",
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.REPLICATED.value,
                    "missing_facts": {
                        "independent_validation": "True (currently False)",
                    },
                    "actionable_remediation": (
                        "Validate top candidates in an independent held-out patient cohort to upgrade evidence standing "
                        "from SUPPORTED to REPLICATED."
                    ),
                })
            if not facts.perturbation:
                advice.append({
                    "target_tier": "overall_maturity",
                    "target_status": WarrantTierStatus.WARRANTED.value,
                    "target_ceiling": ConclusionMaturity.ROBUST.value,
                    "missing_facts": {
                        "perturbation": "True (currently False)",
                        "biological_replicates_count": ">= 3",
                    },
                    "actionable_remediation": (
                        "Couple observational findings with functional in vitro perturbation across >=3 biological replicates "
                        "to upgrade to ROBUST evidence."
                    ),
                })

    return advice


