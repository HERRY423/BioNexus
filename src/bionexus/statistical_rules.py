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
2. ``classify_effect_size_regime`` — stratifies shrunken log2 fold-changes for
   expressed genes. Magnitude can inform interpretation within the assayed
   donors or cell line. Population claims require independent replication.
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
from numbers import Integral
from statistics import NormalDist
from typing import Any, Dict, List, Optional

from bionexus.empirical_warrant import (
    CalibrationContext,
    CalibrationRegistry,
    ComparisonDirection,
    default_calibration_registry,
)
from bionexus.rule_provenance import STATISTICAL_THRESHOLDS

STRONG_EFFECT_LOG2FC = STATISTICAL_THRESHOLDS["strong_effect_log2fc"]
MODERATE_EFFECT_LOG2FC = STATISTICAL_THRESHOLDS["moderate_effect_log2fc"]
SUBTLE_EFFECT_LOG2FC = STATISTICAL_THRESHOLDS["subtle_effect_log2fc"]
DOUBLET_RATE_ADVISORY_THRESHOLD = STATISTICAL_THRESHOLDS["doublet_rate_advisory"]


class EffectSizeRegime(str, Enum):
    """Regime of the observed effect magnitude (Ladder stage 4)."""

    STRONG = "STRONG"        # descriptive magnitude within the assayed biological units
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
    alpha_basis: str = "fdr_as_alpha_optimistic"
    per_test_alpha: Optional[float] = None
    target_power: float = 0.80
    observed_effect_regime: Optional[EffectSizeRegime] = None
    shrunk_log2fc: Optional[float] = None
    base_mean: Optional[float] = None
    sequencing_depth_factor: float = 1.0
    n_tests: Optional[int] = None
    n_true_effects: Optional[int] = None

    @property
    def sufficient_for_population_claims(self) -> bool:
        """Replication and power screen only. Design identifiability is audited separately."""
        return self.n_donors_per_group >= 3 and self.powered_for_regime in (
            EffectSizeRegime.SUBTLE, EffectSizeRegime.MODERATE
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "powered_for_regime": self.powered_for_regime.value,
            "mde_log2fc": round(self.mde_log2fc, 4),
            "n_donors_per_group": self.n_donors_per_group,
            "nominal_fdr": self.nominal_fdr,
            "alpha_basis": self.alpha_basis,
            "per_test_alpha": self.per_test_alpha,
            "target_power": self.target_power,
            "observed_effect_regime": self.observed_effect_regime.value if self.observed_effect_regime else None,
            "shrunk_log2fc": self.shrunk_log2fc,
            "base_mean": self.base_mean,
            "sequencing_depth_factor": self.sequencing_depth_factor,
            "n_tests": self.n_tests,
            "n_true_effects": self.n_true_effects,
            "mean_count_per_cell": self.mean_count_per_cell,
            "dispersion": self.dispersion,
            "cells_per_sample": self.cells_per_sample,
            "sufficient_for_population_claims": self.sufficient_for_population_claims,
            "warnings": list(self.warnings),
            "remedies": list(self.remedies),
            "rule_basis": list(self.rule_basis),
        }


def _per_test_alpha(
    nominal_fdr: float, target_power: float, n_tests: Optional[int], n_true_effects: Optional[int]
) -> tuple[float, str]:
    if not (0 < nominal_fdr < 1 and 0 < target_power < 1):
        raise ValueError("nominal_fdr and target_power must be in (0, 1)")
    for count in (n_tests, n_true_effects):
        if count is not None and (not isinstance(count, Integral) or isinstance(count, bool) or count <= 0):
            raise ValueError("test and expected true-effect counts must be positive integers")
    if n_tests is None or n_true_effects is None:
        return nominal_fdr, "fdr_as_alpha_optimistic"
    if n_true_effects >= n_tests:
        raise ValueError("supply counts satisfying 0 < n_true_effects < n_tests")
    n_null = n_tests - n_true_effects
    alpha = target_power * n_true_effects * nominal_fdr / (n_null * (1 - nominal_fdr))
    return min(alpha, 1.0), "jung2005"


def _nb_mde(
    n_donors_per_group: int, mean_count_per_cell: float, dispersion: float,
    cells_per_sample: int, sequencing_depth_factor: float, alpha: float, target_power: float,
) -> float:
    if not isinstance(n_donors_per_group, Integral) or n_donors_per_group < 2:
        raise ValueError("n_donors_per_group must be an integer >= 2 for a variance-based MDE")
    if not isinstance(cells_per_sample, Integral) or isinstance(cells_per_sample, bool) or cells_per_sample < 1:
        raise ValueError("cells_per_sample must be a positive integer")
    if not all(math.isfinite(x) and x > 0 for x in (mean_count_per_cell, sequencing_depth_factor)):
        raise ValueError("depth parameters must be finite and positive")
    if not math.isfinite(dispersion) or dispersion < 0:
        raise ValueError("dispersion must be finite and >= 0")

    mean = mean_count_per_cell * cells_per_sample * sequencing_depth_factor
    if not math.isfinite(mean) or mean <= 0:
        raise ValueError("pseudobulk depth must be finite and positive")
    if alpha / 2 == 0:
        raise ValueError("per-test alpha is too small for the normal approximation")
    if target_power <= alpha:
        return 0.0  # At zero effect the rejection probability already reaches the target.
    # Use the lower tail directly to avoid losing very small alpha in 1 - alpha/2.
    normal = NormalDist()
    z_sum = -normal.inv_cdf(alpha / 2) + normal.inv_cdf(target_power)
    var_log = 1.0 / mean + dispersion
    return max(0.0, z_sum) * math.sqrt(2 * var_log / n_donors_per_group) / math.log(2)


def estimate_min_detectable_effect(
    *,
    n_donors_per_group: int,
    mean_count_per_cell: float = 1.0,
    dispersion: float = 0.5,
    cells_per_sample: int = 100,
    sequencing_depth_factor: float = 1.0,
    nominal_fdr: float = 0.05,
    target_power: float = 0.80,
    n_tests: Optional[int] = None,
    n_true_effects: Optional[int] = None,
) -> float:
    """Approximate two-group NB MDE on the log2 scale for balanced independent donors.

    The delta-method variance of log pseudobulk counts is 1/mean + dispersion
    per sample. The two-group difference has variance 2 * (1/mean + dispersion) / n.
    With both test counts, use the Jung (2005) expected discovery approximation.
    Without them, nominal FDR serves as an optimistic per-test alpha.
    """
    alpha, _ = _per_test_alpha(nominal_fdr, target_power, n_tests, n_true_effects)
    return _nb_mde(n_donors_per_group, mean_count_per_cell, dispersion, cells_per_sample,
                   sequencing_depth_factor, alpha, target_power)


def classify_effect_size_regime(
    observed_log2fc: Optional[float] = None, *, shrunk_log2fc: Optional[float] = None,
    base_mean: Optional[float] = None,
) -> Optional[EffectSizeRegime]:
    """Classify a shrunken effect above the expression floor. Raw-only calls return None."""
    if shrunk_log2fc is None or base_mean is None:
        return None
    if not math.isfinite(shrunk_log2fc) or not math.isfinite(base_mean):
        return None
    if base_mean < STATISTICAL_THRESHOLDS["effect_min_base_mean"]:
        return None
    magnitude = abs(shrunk_log2fc)
    if magnitude >= STRONG_EFFECT_LOG2FC:
        return EffectSizeRegime.STRONG
    if magnitude >= MODERATE_EFFECT_LOG2FC:
        return EffectSizeRegime.MODERATE
    return EffectSizeRegime.SUBTLE


def assess_statistical_power(
    *,
    n_donors_per_group: int,
    observed_log2fc: Optional[float] = None,
    shrunk_log2fc: Optional[float] = None,
    base_mean: Optional[float] = None,
    mean_count_per_cell: float = 1.0,
    dispersion: float = 0.5,
    cells_per_sample: int = 100,
    nominal_fdr: float = 0.05,
    sequencing_depth_factor: float = 1.0,
    target_power: float = 0.80,
    n_tests: Optional[int] = None,
    n_true_effects: Optional[int] = None,
) -> PowerAssessment:
    """Compare a design's MDE with the claimed effect, recording its alpha basis."""
    alpha, alpha_basis = _per_test_alpha(nominal_fdr, target_power, n_tests, n_true_effects)
    mde = _nb_mde(n_donors_per_group, mean_count_per_cell, dispersion, cells_per_sample,
                  sequencing_depth_factor, alpha, target_power)
    regime = classify_effect_size_regime(shrunk_log2fc=shrunk_log2fc, base_mean=base_mean)
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
            f"detect effects of |log2FC| >= {mde:.2f} at per-test alpha={alpha:.3g} "
            f"({alpha_basis}) with {target_power:.1%} power "
            "(minimum detectable effect, closed-form NB approximation)."
        )
        remedies.append(
            f"Perform and report an explicit power analysis before claiming discovery: at N={n_donors_per_group} "
            f"the minimum detectable effect is |log2FC| >= {mde:.2f}; increase donors per group or restrict "
            "claims to candidate ranking with FRAGILE framing."
        )

    if regime == EffectSizeRegime.SUBTLE and n_donors_per_group < 3:
        warnings.append(
            f"Observed effect regime is SUBTLE (|log2FC| < {MODERATE_EFFECT_LOG2FC}) while replication is "
            f"N={n_donors_per_group}/group: subtle polygenic shifts are exactly the regime this design "
            "cannot separate from donor-level noise."
        )
        remedies.append(
            "Either restrict conclusions to within-sample descriptive shifts or add biological replicates; "
            "population-level claims for SUBTLE effects require the full replication regime."
        )
    if regime == EffectSizeRegime.STRONG and n_donors_per_group == 2:
        warnings.append(
            "The shrunken effect is STRONG. In a paired or isogenic design this can reduce concern about "
            "technical noise. Claims remain descriptive within the assayed donors or cell line."
        )
        remedies.append(
            "Report the shrunken effect, baseMean and design. Limit conclusions to cohort-specific "
            "descriptive claims until independently replicated."
        )

    if regime is None and (observed_log2fc is not None or shrunk_log2fc is not None):
        warnings.append(
            f"Effect-size regime undetermined: supply a finite shrunken log2FC and baseMean "
            f">= {STATISTICAL_THRESHOLDS['effect_min_base_mean']:g}."
        )

    return PowerAssessment(
        alpha_basis=alpha_basis,
        per_test_alpha=alpha,
        target_power=target_power,
        observed_effect_regime=regime,
        shrunk_log2fc=shrunk_log2fc if regime is not None else None,
        base_mean=base_mean if base_mean is not None and math.isfinite(base_mean) else None,
        sequencing_depth_factor=sequencing_depth_factor,
        n_tests=n_tests,
        n_true_effects=n_true_effects,
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
    threshold: float = DOUBLET_RATE_ADVISORY_THRESHOLD
    threshold_basis: str = "screening_advisory"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doublet_rate": self.doublet_rate,
            "exceeds_threshold": self.exceeds_threshold,
            "threshold": self.threshold,
            "threshold_basis": self.threshold_basis,
            "warnings": list(self.warnings),
            "remedies": list(self.remedies),
        }


def assess_doublet_risk(
    doublet_rate: Optional[float], *, calibration_context: Optional[CalibrationContext] = None,
    calibration_registry: Optional[CalibrationRegistry] = None,
) -> Optional[DoubletRiskAssessment]:
    """
    Audit declared doublet-rate metadata before permitting clustering-based
    population claims. Rates above DOUBLET_RATE_ADVISORY_THRESHOLD compromise
    'clean biological populations' narratives regardless of cluster compactness.
    """
    if doublet_rate is None:
        return None
    rate = float(doublet_rate)
    if not math.isfinite(rate) or rate > 1:
        raise ValueError("doublet_rate must be a finite proportion")
    if rate <= 0.0:
        return None
    threshold = DOUBLET_RATE_ADVISORY_THRESHOLD
    basis = "screening_advisory"
    flagged = rate >= threshold
    if calibration_context is not None:
        registry = calibration_registry or default_calibration_registry()
        resolution = registry.resolve("doublet_rate", calibration_context)
        if resolution.resolved and resolution.direction == ComparisonDirection.AT_MOST and resolution.threshold is not None:
            threshold = resolution.threshold
            basis = f"{resolution.profile_id}@{resolution.profile_version}"
            flagged = rate > threshold
    if not flagged:
        return DoubletRiskAssessment(rate, False, threshold=threshold, threshold_basis=basis)
    return DoubletRiskAssessment(
        rate,
        True,
        threshold=threshold,
        threshold_basis=basis,
        warnings=[
            f"Declared doublet rate is {rate:.0%} (threshold {threshold:.0%}, {basis}): apparent "
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
