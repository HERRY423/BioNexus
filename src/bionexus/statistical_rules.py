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


class StructureConfidenceRegime(str, Enum):
    """AlphaFold/ESMFold per-residue and global confidence tiers (Jumper et al. 2021)."""

    VERY_HIGH = "VERY_HIGH"  # pLDDT >= 90: high accuracy for side chains and pockets
    CONFIDENT = "CONFIDENT"  # 70 <= pLDDT < 90: reliable backbone topology
    LOW = "LOW"  # 50 <= pLDDT < 70: low confidence, flexible/unstructured candidate
    VERY_LOW_DISORDERED = "VERY_LOW_DISORDERED"  # pLDDT < 50: intrinsically disordered region (IDR)


@dataclass
class StructureConfidenceAssessment:
    """Audit result for macromolecular structural confidence metrics."""

    regime: StructureConfidenceRegime
    mean_plddt: float
    min_plddt: float
    interdomain_pae: Optional[float]
    sufficient_for_rigid_pocket: bool
    warnings: List[str] = field(default_factory=list)
    remedies: List[str] = field(default_factory=list)
    rule_basis: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime.value,
            "mean_plddt": round(self.mean_plddt, 2),
            "min_plddt": round(self.min_plddt, 2),
            "interdomain_pae": round(self.interdomain_pae, 2) if self.interdomain_pae is not None else None,
            "sufficient_for_rigid_pocket": self.sufficient_for_rigid_pocket,
            "warnings": list(self.warnings),
            "remedies": list(self.remedies),
            "rule_basis": list(self.rule_basis),
        }


def assess_protein_structure_confidence(
    mean_plddt: float,
    min_plddt: Optional[float] = None,
    interdomain_pae: Optional[float] = None,
) -> StructureConfidenceAssessment:
    """
    Audit AlphaFold/ESMFold structural confidence metrics against epistemic criteria.

    Normative rules:
    - pLDDT < 50: Strong predictor of intrinsic disorder (IDR); never permits rigid binding site assertions.
    - 50 <= pLDDT < 70: Low confidence ribbon/backbone; exploratory screening only, no atomic docking claims.
    - 70 <= pLDDT < 90: Confident backbone; suitable for fold topology and overall domain arrangement.
    - pLDDT >= 90: High-confidence side-chain coordinates.
    - Inter-domain PAE > 15.0 Å: Inter-domain orientation cannot be asserted as fixed rigid body.
    """
    mean_val = float(mean_plddt)
    min_val = float(min_plddt) if min_plddt is not None else mean_val
    warnings: List[str] = []
    remedies: List[str] = []
    rule_basis: List[str] = ["Jumper et al. 2021 (AlphaFold2, Nature)", "Akdel et al. 2022 (Nat Struct Mol Biol)"]

    if mean_val >= 90.0 and min_val >= 70.0:
        regime = StructureConfidenceRegime.VERY_HIGH
        sufficient_for_rigid_pocket = True
    elif mean_val >= 70.0:
        regime = StructureConfidenceRegime.CONFIDENT
        sufficient_for_rigid_pocket = min_val >= 60.0
        if min_val < 60.0:
            warnings.append(
                f"Global mean pLDDT is confident ({mean_val:.1f}), but local minimum is low ({min_val:.1f}). "
                "Active site residues may reside in a flexible loop region."
            )
            remedies.append("Inspect per-residue pLDDT specifically across active site and binding pocket residues.")
    elif mean_val >= 50.0:
        regime = StructureConfidenceRegime.LOW
        sufficient_for_rigid_pocket = False
        warnings.append(
            f"Mean pLDDT is low ({mean_val:.1f}). Backbone prediction is exploratory; coordinates should not be "
            "treated as an experimental crystallographic ground truth."
        )
        remedies.append(
            "Cap structural conclusions at candidate hypothesis (FRAGILE ceiling); confirm with circular dichroism, "
            "NMR, or cryo-EM before asserting pocket druggability."
        )
    else:
        regime = StructureConfidenceRegime.VERY_LOW_DISORDERED
        sufficient_for_rigid_pocket = False
        warnings.append(
            f"Mean pLDDT is very low ({mean_val:.1f} < 50.0). Regions with pLDDT < 50 are known to correlate with "
            "intrinsic disorder (IDR); asserting a fixed 3D pocket or rigid tertiary fold is scientifically invalid."
        )
        remedies.append(
            "Abstain from rigid pocket claims. Model candidate region with IDR-specific disordered ensembles or "
            "investigate induced-fit folding upon partner binding."
        )

    if interdomain_pae is not None and float(interdomain_pae) > 15.0:
        warnings.append(
            f"Inter-domain Predicted Aligned Error (PAE) is elevated ({float(interdomain_pae):.1f} Å > 15.0 Å). "
            "Relative domain-domain orientation is unconstrained and cannot warrant a rigid multi-domain interface."
        )
        remedies.append("Evaluate individual domains independently; do not assert multi-domain cooperative pocket geometry.")

    return StructureConfidenceAssessment(
        regime=regime,
        mean_plddt=mean_val,
        min_plddt=min_val,
        interdomain_pae=float(interdomain_pae) if interdomain_pae is not None else None,
        sufficient_for_rigid_pocket=sufficient_for_rigid_pocket,
        warnings=warnings,
        remedies=remedies,
        rule_basis=rule_basis,
    )


class BioactivityRegime(str, Enum):
    """Small-molecule potency and affinity tiers (ChEMBL / IUPHAR standard)."""

    POTENT = "POTENT"  # <= 100 nM: potent nanomolar lead candidate
    MODERATE = "MODERATE"  # 100 nM - 1000 nM (1 uM): confirmed micromolar hit
    WEAK = "WEAK"  # 1 uM - 10 uM: weak/screening activity requiring SAR optimization
    INACTIVE_OR_NONSPECIFIC = "INACTIVE_OR_NONSPECIFIC"  # > 10 uM: non-specific or inactive


@dataclass
class BioactivityAssessment:
    """Audit result for small-molecule binding affinity and bioactivity metrics."""

    regime: BioactivityRegime
    metric_name: str
    value_nm: float
    has_dose_response: bool
    sufficient_for_lead_claim: bool
    warnings: List[str] = field(default_factory=list)
    remedies: List[str] = field(default_factory=list)
    rule_basis: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": self.regime.value,
            "metric_name": self.metric_name,
            "value_nm": round(self.value_nm, 2),
            "has_dose_response": self.has_dose_response,
            "sufficient_for_lead_claim": self.sufficient_for_lead_claim,
            "warnings": list(self.warnings),
            "remedies": list(self.remedies),
            "rule_basis": list(self.rule_basis),
        }


def assess_bioactivity_affinity(
    value_nm: float,
    metric_name: str = "IC50",
    has_dose_response: bool = True,
) -> BioactivityAssessment:
    """
    Audit small-molecule affinity metrics (IC50, Ki, Kd) against medicinal chemistry warrant tiers.

    Normative rules:
    - Affinity > 10,000 nM (10 uM): Classified as INACTIVE_OR_NONSPECIFIC; cannot claim targeted inhibitor.
    - 1,000 nM < Affinity <= 10,000 nM: WEAK screening hit; require SAR optimization caveats.
    - 100 nM < Affinity <= 1,000 nM: MODERATE hit.
    - Affinity <= 100 nM: POTENT lead.
    - Single-concentration screening without dose-response curve: caps claim at PRELIMINARY.
    """
    val = float(value_nm)
    metric = metric_name.upper().strip()
    warnings: List[str] = []
    remedies: List[str] = []
    rule_basis: List[str] = [
        "IUPHAR / BPS Guidelines for Pharmacology",
        "Bento et al. 2014 (ChEMBL database, Nucleic Acids Res)",
    ]

    if val <= 100.0:
        regime = BioactivityRegime.POTENT
        sufficient_for_lead_claim = has_dose_response
    elif val <= 1000.0:
        regime = BioactivityRegime.MODERATE
        sufficient_for_lead_claim = False
    elif val <= 10000.0:
        regime = BioactivityRegime.WEAK
        sufficient_for_lead_claim = False
        warnings.append(
            f"{metric} of {val:.1f} nM ({val/1000.0:.2f} µM) represents weak micromolar binding. "
            "Claims of potent or selective inhibition are unwarranted without SAR optimization."
        )
        remedies.append("Design analog series for structure-activity relationship (SAR) optimization.")
    else:
        regime = BioactivityRegime.INACTIVE_OR_NONSPECIFIC
        sufficient_for_lead_claim = False
        warnings.append(
            f"{metric} exceeds 10,000 nM ({val/1000.0:.1f} µM > 10 µM). In standard medicinal chemistry, "
            "activities > 10 µM are considered non-specific or inactive; asserting targeted inhibition is refused."
        )
        remedies.append("Abstain from targeted therapeutic claims; rule out colloidal aggregation or PAINS properties.")

    if not has_dose_response:
        warnings.append(
            f"{metric} reported from single-concentration screening without full concentration-response curve. "
            "Artifacts from compound insolubility or assay interference cannot be ruled out."
        )
        remedies.append("Perform multi-point serial dilution titration to determine robust Hill slope and true IC50/Kd.")

    return BioactivityAssessment(
        regime=regime,
        metric_name=metric,
        value_nm=val,
        has_dose_response=has_dose_response,
        sufficient_for_lead_claim=sufficient_for_lead_claim,
        warnings=warnings,
        remedies=remedies,
        rule_basis=rule_basis,
    )
