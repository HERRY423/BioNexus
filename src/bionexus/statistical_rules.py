"""
BioNexus Statistical-Level Rules: power, minimum detectable effect, and
effect-size regime assessment (Epistemic Ladder stages 2 & 4, BNS-007).

Design-level rules (replication counts, confounding) answer "can this design
identify an effect at all". Statistical-level rules answer the harder question:
"what size of effect CAN this design identify, and does the claimed conclusion
match that regime?".

Three deterministic instruments:

1. ``estimate_min_detectable_effect`` — closed-form MDE approximation for a
   pseudobulk negative-binomial comparison at a given donor count, depth,
   dispersion, and nominal FDR. Deterministic; no data file required.
2. ``classify_effect_size_regime`` — stratifies observed log2 fold-changes into
   STRONG / MODERATE / SUBTLE regimes. The Context-Conditioned Epistemic Ladder
   explicitly rejects magic-number refusals: a strong monogenic-scale effect
   legitimately needs less replication than a subtle polygenic shift.
3. ``assess_doublet_risk`` — clustering-quality advisory: elevated doublet
   rates invalidate clean-population claims before annotation.

Normative references:
- Squair et al. 2021 (Nature Comms) — pseudoreplication and power in scRNA-seq DE
- Lun & Marioni 2017 — pseudobulk over cell-level mixed models
- Soneson & Robinson 2018 — bias, robustness and sensitivity of DE methods
- BNS-007 (parameter sensitivity), BN-F002 (insufficient statistical power),
  BN-F003 (annotation without evidence / doublet artifacts)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

#: Effect-size regime boundaries (log2 fold-change). Registry-reviewed constants.
STRONG_EFFECT_LOG2FC = 4.0   # monogenic-knockout scale (deterministic-effect regime)
MODERATE_EFFECT_LOG2FC = 1.0  # clear targeted effect
#: Below this, effects are SUBTLE polygenic shifts requiring full replication.
SUBTLE_EFFECT_LOG2FC = 0.5

#: Doublet rate above which cluster-level population claims are compromised.
DOUBLET_RATE_ADVISORY_THRESHOLD = 0.10

#: Normal approximation z-quantiles (two-sided alpha=0.05 -> 1.959964; power 0.8 -> 0.841621).
_Z_ALPHA_0P05_TWO_SIDED = 1.959964
_Z_POWER_0P8 = 0.841621


class EffectSizeRegime(str, Enum):
    """Regime of the observed effect magnitude (Ladder stage 4)."""

    STRONG = "STRONG"        # deterministic/monogenic scale; reduced replication defensible
    MODERATE = "MODERATE"    # targeted effect; standard replication expectations
    SUBTLE = "SUBTLE"        # polygenic shift; full replication + power analysis required


@dataclass
class PowerAssessment:
    """Deterministic statistical-power assessment for a pseudobulk design."""

    powered_for_regime: EffectSizeRegime
    mde_log2fc: float
    n_donors_per_group: int
    nominal_fdr: float
    mean_count_per_cell: float
    dispersion: float
    cells_per_sample: int
    warnings: List[str] = field(default_factory=list)
    remedies: List[str] = field(default_factory=list)
    rule_basis: List[str] = field(default_factory=list)

    @property
    def sufficient_for_population_claims(self) -> bool:
        """True when the design detects at least MODERATE-regime effects."""
        return self.powered_for_regime in (EffectSizeRegime.SUBTLE, EffectSizeRegime.MODERATE)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "powered_for_regime": self.powered_for_regime.value,
            "mde_log2fc": round(self.mde_log2fc, 4),
            "n_donors_per_group": self.n_donors_per_group,
            "nominal_fdr": self.nominal_fdr,
            "mean_count_per_cell": self.mean_count_per_cell,
            "dispersion": self.dispersion,
            "cells_per_sample": self.cells_per_sample,
            "sufficient_for_population_claims": self.sufficient_for_population_claims,
            "warnings": list(self.warnings),
            "remedies": list(self.remedies),
            "rule_basis": list(self.rule_basis),
        }


def estimate_min_detectable_effect(
    *,
    n_donors_per_group: int,
    mean_count_per_cell: float = 1.0,
    dispersion: float = 0.5,
    cells_per_sample: int = 100,
    sequencing_depth_factor: float = 1.0,
    nominal_fdr: float = 0.05,
    target_power: float = 0.80,
) -> float:
    """
    Closed-form MDE approximation (log2 scale) for pseudobulk NB differential expression.

    Model: per-sample pseudobulk count for one gene ~ NB(mu, dispersion). With
    k cells aggregated at mean per-cell count c, pseudobulk depth is k*c*d.
    The per-donor sampling variance of log-expression is approximated by
    (1/(k*c*d)) + dispersion/n_effective, and the two-group MSE scales the
    classic two-sample z formula:

        MDE(log2) = (z_{1-alpha/2} + z_{power}) * sqrt(2 * sigma^2 / n)

    where sigma^2 combines technical (depth) and biological (dispersion/donor)
    variance. This is a conservative screening approximation, not a substitute
    for per-gene NB GLM power simulation; it exists to make "is the claimed
    regime even detectable" auditable BEFORE compute.
    """
    if n_donors_per_group < 1:
        raise ValueError("n_donors_per_group must be >= 1")
    if mean_count_per_cell <= 0 or cells_per_sample < 1 or sequencing_depth_factor <= 0:
        raise ValueError("depth parameters must be positive")
    if dispersion < 0:
        raise ValueError("dispersion must be >= 0")

    pseudobulk_depth = max(mean_count_per_cell * cells_per_sample * sequencing_depth_factor, 1e-6)
    technical_var = 1.0 / pseudobulk_depth
    biological_var = dispersion / max(n_donors_per_group, 1)
    sigma2 = technical_var + biological_var
    z_sum = _Z_ALPHA_0P05_TWO_SIDED + _Z_POWER_0P8 * min(max(target_power, 0.01), 0.999) / 0.80
    mde_log2 = (z_sum / math.log(2)) * math.sqrt(2 * sigma2 / max(n_donors_per_group, 1))
    return float(mde_log2)


def classify_effect_size_regime(observed_log2fc: Optional[float]) -> Optional[EffectSizeRegime]:
    """Stratify an observed |log2FC| into its evidential regime (Ladder stage 4)."""
    if observed_log2fc is None:
        return None
    magnitude = abs(float(observed_log2fc))
    if magnitude >= STRONG_EFFECT_LOG2FC:
        return EffectSizeRegime.STRONG
    if magnitude >= MODERATE_EFFECT_LOG2FC:
        return EffectSizeRegime.MODERATE
    return EffectSizeRegime.SUBTLE


def assess_statistical_power(
    *,
    n_donors_per_group: int,
    observed_log2fc: Optional[float] = None,
    mean_count_per_cell: float = 1.0,
    dispersion: float = 0.5,
    cells_per_sample: int = 100,
    nominal_fdr: float = 0.05,
) -> PowerAssessment:
    """
    Assess whether the design's detectable effect regime matches the claim context.

    Returns a PowerAssessment whose warnings/remedies are phrased for direct use
    as router advisories (BN-F002): low-power designs always carry an explicit
    'power' remedy so downstream hosts cannot present them as adequately
    powered discovery runs.
    """
    mde = estimate_min_detectable_effect(
        n_donors_per_group=n_donors_per_group,
        mean_count_per_cell=mean_count_per_cell,
        dispersion=dispersion,
        cells_per_sample=cells_per_sample,
        nominal_fdr=nominal_fdr,
    )
    regime = classify_effect_size_regime(observed_log2fc)
    # ``powered_for_regime`` names the WEAKEST effect regime this design can
    # detect at nominal FDR/power: a small MDE powers even SUBTLE claims.
    if mde <= SUBTLE_EFFECT_LOG2FC:
        powered_for = EffectSizeRegime.SUBTLE
    elif mde <= MODERATE_EFFECT_LOG2FC:
        powered_for = EffectSizeRegime.MODERATE
    else:
        powered_for = EffectSizeRegime.STRONG

    warnings: List[str] = []
    remedies: List[str] = []
    basis = [
        "Squair et al. 2021 (Nature Comms); Lun & Marioni 2017; Soneson & Robinson 2018",
        "BNS-007 cross-method validation; BN-F002 insufficient statistical power",
    ]

    if n_donors_per_group < 3:
        warnings.append(
            f"Statistical power at N={n_donors_per_group} donors/group is minimal: the design can only "
            f"detect effects of |log2FC| >= {mde:.2f} at FDR={nominal_fdr} with 80% power "
            "(minimum detectable effect, closed-form NB approximation)."
        )
        remedies.append(
            f"Perform and report an explicit power analysis before claiming discovery: at N={n_donors_per_group} "
            f"the minimum detectable effect is |log2FC| >= {mde:.2f}; increase donors per group or restrict "
            "claims to candidate ranking with FRAGILE framing."
        )

    if regime is not None and regime == EffectSizeRegime.SUBTLE and n_donors_per_group < 3:
        warnings.append(
            f"Observed effect regime is SUBTLE (|log2FC| < {MODERATE_EFFECT_LOG2FC}) while replication is "
            f"N={n_donors_per_group}/group: subtle polygenic shifts are exactly the regime this design "
            "cannot separate from donor-level noise."
        )
        remedies.append(
            "Either restrict conclusions to within-sample descriptive shifts or add biological replicates; "
            "population-level claims for SUBTLE effects require the full replication regime."
        )
    if regime is not None and regime == EffectSizeRegime.STRONG and n_donors_per_group == 2:
        warnings.append(
            "Effect-size regime is STRONG (monogenic/deterministic scale): the Context-Conditioned Epistemic "
            "Ladder permits reduced replication for ruling out technical noise at this magnitude, but claims "
            "remain cohort-specific descriptive until independently reproduced."
        )
        remedies.append(
            "Record the deterministic-effect justification in provenance; conclusions remain cohort-specific "
            "descriptive until independently reproduced on an external cohort."
        )

    return PowerAssessment(
        powered_for_regime=powered_for,
        mde_log2fc=mde,
        n_donors_per_group=n_donors_per_group,
        nominal_fdr=nominal_fdr,
        mean_count_per_cell=mean_count_per_cell,
        dispersion=dispersion,
        cells_per_sample=cells_per_sample,
        warnings=warnings,
        remedies=remedies,
        rule_basis=basis,
    )


@dataclass
class DoubletRiskAssessment:
    """Clustering-quality advisory for elevated doublet rates (BN-F003)."""

    doublet_rate: float
    exceeds_threshold: bool
    warnings: List[str] = field(default_factory=list)
    remedies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doublet_rate": self.doublet_rate,
            "exceeds_threshold": self.exceeds_threshold,
            "warnings": list(self.warnings),
            "remedies": list(self.remedies),
        }


def assess_doublet_risk(doublet_rate: Optional[float]) -> Optional[DoubletRiskAssessment]:
    """
    Audit declared doublet-rate metadata before permitting clustering-based
    population claims. Rates above DOUBLET_RATE_ADVISORY_THRESHOLD compromise
    'clean biological populations' narratives regardless of cluster compactness.
    """
    if doublet_rate is None:
        return None
    rate = float(doublet_rate)
    if rate <= 0.0:
        return None
    if rate < DOUBLET_RATE_ADVISORY_THRESHOLD:
        return DoubletRiskAssessment(rate, False)
    return DoubletRiskAssessment(
        rate,
        True,
        warnings=[
            f"Declared doublet rate is {rate:.0%} (threshold {DOUBLET_RATE_ADVISORY_THRESHOLD:.0%}): apparent "
            "cluster cleanliness does not exclude doublet-driven artificial clusters, and population labels "
            "inherited from such clusters are not evidence-backed."
        ],
        remedies=[
            "Run explicit doublet detection (Scrublet/DoubletFinder/scDblFinder), remove or annotate predicted "
            "doublets, and re-cluster before naming populations; carry the doublet annotation into any "
            "downstream cell-type evidence assessment.",
        ],
    )
