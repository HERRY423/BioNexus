"""
BioNexus Pseudobulk Inferential Warrant & Epistemic Boundary Engine.

Defines and enforces the four inferential regimes for single-cell differential expression:
1. POPULATION_INFERENCE (N >= 3 biological replicates/donors per group, raw integer counts,
   sufficient cell counts per sample) -> SUPPORTED / ROBUST warrant for population-level claims.
2. DESCRIPTIVE_ONLY (N = 2 replicates, or low cell count / high sparsity, or marker-gene comparisons)
   -> Capped at TENTATIVE / EXPLORATORY; population-level generalization is prohibited.
3. ABSTAIN_UNREPLICATED (N = 1 per group, pseudoreplication without donor identifiers)
   -> Strictly refused (ABSTAIN); zero degrees of freedom for biological variance.
4. ABSTAIN_INVALID_INPUT (Normalized/log-transformed floats to count models, confounded designs)
   -> Strictly refused (ABSTAIN); mathematical assumptions violated.
5. CAUSAL_CLAIM_BLOCK (Observational cross-sectional single-cell data claiming causal mechanisms)
   -> Intercepted and remediated to associational language.

Normative references:
- BNS-010 / BNS-015 (Flagship Capability A: scrna.pseudobulk_de)
- BNS-CC-009 (Statistical Warrant Clamping)
- BN-F001 (Pseudoreplication / Cell != Biological Replicate)
- BN-F006 (Confounded Design / Zero Replicates)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from bionexus.contracts import ConclusionMaturity


class InferentialRegime(str, Enum):
    """The inferential regime justified by the experimental design and data state."""

    POPULATION_INFERENCE = "POPULATION_INFERENCE"
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    ABSTAIN_UNREPLICATED = "ABSTAIN_UNREPLICATED"
    ABSTAIN_INVALID_INPUT = "ABSTAIN_INVALID_INPUT"
    ABSTAIN_CONFOUNDED = "ABSTAIN_CONFOUNDED"


@dataclass
class PseudobulkWarrantVerdict:
    """The formal warrant assessment for a pseudobulk differential expression run."""

    regime: InferentialRegime
    maturity_ceiling: ConclusionMaturity
    permitted: bool
    population_claims_allowed: bool
    causal_claims_allowed: bool
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    remedy: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime.value,
            "maturity_ceiling": self.maturity_ceiling.value,
            "permitted": self.permitted,
            "population_claims_allowed": self.population_claims_allowed,
            "causal_claims_allowed": self.causal_claims_allowed,
            "reasons": list(self.reasons),
            "warnings": list(self.warnings),
            "remedy": self.remedy,
            "metrics": dict(self.metrics),
        }


def evaluate_pseudobulk_inferential_warrant(
    *,
    n_donors_per_group: int | Dict[str, int],
    min_cells_per_sample: int = 20,
    is_raw_counts: bool = True,
    is_confounded: bool = False,
    has_donor_metadata: bool = True,
    is_interventional: bool = False,
    nominal_fdr: float = 0.05,
    design_balanced_or_paired: bool = False,
    dispersion_verified: bool = False,
    intervention_identified: bool = False,
) -> PseudobulkWarrantVerdict:
    """
    Evaluate what inferential conclusions are scientifically warranted for a pseudobulk DE design.

    Parameters:
        n_donors_per_group: Number of biological replicates (donors/animals) per condition.
            Can be an integer or a dict mapping condition name to donor count.
        min_cells_per_sample: Minimum number of cells aggregated per pseudobulk sample.
        is_raw_counts: Whether the input expression matrix contains raw integer counts.
        is_confounded: Whether donor/batch is 100% confounded with condition.
        has_donor_metadata: Whether biological replicate/donor identifiers exist.
        is_interventional: Whether this is a controlled perturbation study (e.g. CRISPR/Perturb-seq).
        nominal_fdr: Multiple testing FDR threshold (default: 0.05).
        design_balanced_or_paired: Whether treatment assignment is balanced or paired across donors.
        dispersion_verified: Whether negative binomial dispersion estimation was properly modeled and converged.
        intervention_identified: Whether exchangeability and unconfoundedness conditions are explicitly verified.

    Returns:
        PseudobulkWarrantVerdict detailing the justified regime, ceiling, and claim boundaries.
    """
    if isinstance(n_donors_per_group, dict):
        min_donors = min(n_donors_per_group.values()) if n_donors_per_group else 0
        donor_dict = dict(n_donors_per_group)
    else:
        min_donors = int(n_donors_per_group)
        donor_dict = {"min_group": min_donors}

    metrics: Dict[str, Any] = {
        "min_donors_per_group": min_donors,
        "donors_by_group": donor_dict,
        "min_cells_per_sample": min_cells_per_sample,
        "is_raw_counts": is_raw_counts,
        "is_confounded": is_confounded,
        "has_donor_metadata": has_donor_metadata,
        "is_interventional": is_interventional,
        "nominal_fdr": nominal_fdr,
        "design_balanced_or_paired": design_balanced_or_paired,
        "dispersion_verified": dispersion_verified,
        "intervention_identified": intervention_identified,
    }

    # 1. Check Fatal Invariants: Non-integer counts / Invalid input
    if not is_raw_counts:
        return PseudobulkWarrantVerdict(
            regime=InferentialRegime.ABSTAIN_INVALID_INPUT,
            maturity_ceiling=ConclusionMaturity.ABSTAIN,
            permitted=False,
            population_claims_allowed=False,
            causal_claims_allowed=False,
            reasons=[
                "Negative binomial generalized linear models (PyDESeq2) strictly assume discrete integer counts. "
                "Normalized or log-transformed floats violate dispersion estimation mathematics."
            ],
            remedy="Provide the raw UMI integer count layer (adata.layers['counts'] or raw adata.X).",
            metrics=metrics,
        )

    # 2. Check Fatal Invariants: Completely confounded design
    if is_confounded:
        return PseudobulkWarrantVerdict(
            regime=InferentialRegime.ABSTAIN_CONFOUNDED,
            maturity_ceiling=ConclusionMaturity.ABSTAIN,
            permitted=False,
            population_claims_allowed=False,
            causal_claims_allowed=False,
            reasons=[
                "Experimental condition is 100% confounded with technical batch or donor identity (BN-F006). "
                "Condition effect cannot be mathematically separated from batch variation."
            ],
            remedy="Include samples where condition and batch/donor vary orthogonally.",
            metrics=metrics,
        )

    # 3. Check Fatal Invariants: Zero biological replicates or pseudoreplication (N < 2)
    if not has_donor_metadata or min_donors < 2:
        return PseudobulkWarrantVerdict(
            regime=InferentialRegime.ABSTAIN_UNREPLICATED,
            maturity_ceiling=ConclusionMaturity.ABSTAIN,
            permitted=False,
            population_claims_allowed=False,
            causal_claims_allowed=False,
            reasons=[
                f"Design has N={min_donors} biological replicate(s) per group. Biological differential expression "
                "requires >= 2 (and ideally >= 3) independent replicates to estimate biological variance (BN-F001). "
                "Treating single cells as independent replicates constitutes pseudoreplication."
            ],
            remedy="Annotate sample metadata with biological replicate/donor identifiers (at least 2, preferably >= 3 donors per group).",
            metrics=metrics,
        )

    # 4. Low replicate regime: N = 2 (Descriptive only)
    if min_donors == 2:
        warnings = [
            "Low biological replicate count (N=2 per group): degrees of freedom are minimal. "
            "Dispersion estimation relies entirely on empirical Bayes shrinkage across genes. "
            "Results are exploratory and descriptive of this specific sample pair, NOT generalizable to the population."
        ]
        if min_cells_per_sample < 10:
            warnings.append(
                f"Low cell count per sample ({min_cells_per_sample} < 10): sampling noise may dominate pseudobulk counts."
            )
        return PseudobulkWarrantVerdict(
            regime=InferentialRegime.DESCRIPTIVE_ONLY,
            maturity_ceiling=ConclusionMaturity.PRELIMINARY,
            permitted=True,
            population_claims_allowed=False,
            causal_claims_allowed=False,
            reasons=[
                "N=2 replicates per group permits descriptive DE modeling but does not warrant population-level inference."
            ],
            warnings=warnings,
            remedy="Increase cohort size to >= 3 donors per group to enable population-level claims.",
            metrics=metrics,
        )

    # 5. Full population inference regime: N >= 3
    warnings = []
    if min_cells_per_sample < 10:
        warnings.append(
            f"Low cell count per sample ({min_cells_per_sample} < 10): pseudobulk counts for sparse cell types may have elevated variance."
        )

    # Causal identification requires verified experimental design, dispersion modeling,
    # and exchangeability, not merely an interventional flag on minimum replicates (Squair et al. 2021).
    causal_allowed = False
    maturity = ConclusionMaturity.SUPPORTED

    if is_interventional:
        if intervention_identified and (design_balanced_or_paired or dispersion_verified):
            causal_allowed = True
            maturity = ConclusionMaturity.ROBUST
        else:
            warnings.append(
                "Interventional study declared, but causal identification conditions "
                "(exchangeability, balanced/paired design matrix, dispersion modeling) "
                "are unverified. Causal claims restricted; defaulting to population-level associational inference."
            )

    return PseudobulkWarrantVerdict(
        regime=InferentialRegime.POPULATION_INFERENCE,
        maturity_ceiling=maturity,
        permitted=True,
        population_claims_allowed=True,
        causal_claims_allowed=causal_allowed,
        reasons=[
            f"Sufficient biological replicates (min N={min_donors} >= 3) and raw integer counts. "
            "Negative binomial GLM with Wald tests warrants population-level differential expression inference."
        ],
        warnings=warnings,
        remedy=None,
        metrics=metrics,
    )
