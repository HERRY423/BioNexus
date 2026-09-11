"""
BioNexus Prescriptive Power & Experimental Remediation Engine.

Translates diagnostic rejections and claim caps into quantitative, actionable
study design prescriptions and power-calibrated remediation pathways.

Theoretical foundations:
- Hart, S. N. et al. (2013). Calculating sample size estimates for RNA sequencing data.
  Journal of Computational Biology, 20(12), 970-978.
- Squair, J. W. et al. (2021). Confronting false discoveries in single-cell differential expression.
  Nature Communications, 12(1), 5692.
- Love, M. I., Huber, W., & Anders, S. (2014). Moderated estimation of fold change and dispersion
  for RNA-seq data with DESeq2. Genome Biology, 15(12), 550.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from bionexus.contracts import ConclusionMaturity


class RemediationStrategy(str, Enum):
    """Category of scientific remediation action."""

    ADD_BIOLOGICAL_REPLICATES = "ADD_BIOLOGICAL_REPLICATES"
    SWITCH_TO_PAIRED_DESIGN = "SWITCH_TO_PAIRED_DESIGN"
    EMPIRICAL_BAYES_SHRINKAGE = "EMPIRICAL_BAYES_SHRINKAGE"
    DOWNGRADE_CLAIM_CEILING = "DOWNGRADE_CLAIM_CEILING"
    CORRECT_COUNT_PREPROCESSING = "CORRECT_COUNT_PREPROCESSING"
    APPLY_FDR_CORRECTION = "APPLY_FDR_CORRECTION"
    BACKEND_FIDELITY_ENFORCEMENT = "BACKEND_FIDELITY_ENFORCEMENT"


@dataclass
class PowerCalculationResult:
    """Quantitative statistical power assessment under Negative Binomial dispersion."""

    power: float
    alpha: float
    n_per_group: int
    target_log2fc: float
    dispersion: float
    mean_read_depth: float
    is_adequate: bool  # True if power >= target threshold (e.g. 0.80)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "power": round(self.power, 4),
            "alpha": self.alpha,
            "n_per_group": self.n_per_group,
            "target_log2fc": self.target_log2fc,
            "dispersion": self.dispersion,
            "mean_read_depth": self.mean_read_depth,
            "is_adequate": self.is_adequate,
        }


@dataclass
class RemediationPrescription:
    """Actionable scientific prescription to overcome a warrant limitation or failure."""

    violation_id: str
    primary_strategy: str
    current_state_summary: str
    target_maturity: str
    minimum_required_samples: int = 0
    additional_samples_needed: int = 0
    power_assessment: Optional[PowerCalculationResult] = None
    analytical_remedies: List[str] = field(default_factory=list)
    academic_citations: List[str] = field(default_factory=list)
    remediation_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "violation_id": self.violation_id,
            "primary_strategy": self.primary_strategy,
            "current_state_summary": self.current_state_summary,
            "target_maturity": self.target_maturity,
            "minimum_required_samples": self.minimum_required_samples,
            "additional_samples_needed": self.additional_samples_needed,
            "power_assessment": self.power_assessment.to_dict() if self.power_assessment else None,
            "analytical_remedies": self.analytical_remedies,
            "academic_citations": self.academic_citations,
            "remediation_text": self.remediation_text,
        }


def _standard_normal_cdf(x: float) -> float:
    """Gaussian CDF using math.erf."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _standard_normal_quantile(p: float) -> float:
    """Rational approximation for normal inverse CDF (Winitzki approximation)."""
    if p <= 0.0 or p >= 1.0:
        raise ValueError("p must be in (0, 1)")
    # Approximation of normal quantile function
    # Abramowitz and Stegun 26.2.23
    t = math.sqrt(-2.0 * math.log(min(p, 1.0 - p)))
    c0 = 2.515517
    c1 = 0.802853
    c2 = 0.010328
    d1 = 1.432788
    d2 = 0.189269
    d3 = 0.001308
    numerator = c0 + c1 * t + c2 * (t**2)
    denominator = 1.0 + d1 * t + d2 * (t**2) + d3 * (t**3)
    val = t - (numerator / denominator)
    return -val if p < 0.5 else val


def calculate_pseudobulk_power(
    n_per_group: int,
    log2fc: float = 1.0,
    dispersion: float = 0.2,
    alpha: float = 0.05,
    mean_read_depth: float = 20.0,
    target_power: float = 0.80,
) -> PowerCalculationResult:
    """Calculate statistical power for RNA-seq / pseudobulk DE under Negative Binomial model.

    Variance for log-fold-change estimator:
        sigma^2 = (2 / n) * (1 / mu + phi)
    Test statistic under H1:
        Z = |log_e(FC)| / sqrt(sigma^2) = (|log2fc| * ln(2)) / sqrt(sigma^2)
    Power = Phi(Z - Z_{1 - alpha/2})
    """
    if n_per_group < 1:
        return PowerCalculationResult(
            power=0.0,
            alpha=alpha,
            n_per_group=n_per_group,
            target_log2fc=log2fc,
            dispersion=dispersion,
            mean_read_depth=mean_read_depth,
            is_adequate=False,
        )

    # Convert log2 fold change to natural log
    delta = abs(log2fc) * math.log(2.0)
    mu = max(1.0, float(mean_read_depth))
    phi = max(0.001, float(dispersion))

    # Variance per group
    var_logfc = (2.0 / float(n_per_group)) * ((1.0 / mu) + phi)
    se_logfc = math.sqrt(var_logfc)

    z_crit = _standard_normal_quantile(1.0 - alpha / 2.0)
    z_stat = delta / se_logfc

    power = _standard_normal_cdf(z_stat - z_crit)
    power = max(0.0, min(1.0, power))

    return PowerCalculationResult(
        power=power,
        alpha=alpha,
        n_per_group=n_per_group,
        target_log2fc=log2fc,
        dispersion=dispersion,
        mean_read_depth=mean_read_depth,
        is_adequate=(power >= target_power),
    )


def calculate_required_replicates(
    target_power: float = 0.80,
    target_log2fc: float = 1.0,
    dispersion: float = 0.2,
    alpha: float = 0.05,
    mean_read_depth: float = 20.0,
    max_replicates: int = 100,
) -> int:
    """Find minimum biological replicates per group to achieve target_power."""
    for n in range(2, max_replicates + 1):
        res = calculate_pseudobulk_power(
            n_per_group=n,
            log2fc=target_log2fc,
            dispersion=dispersion,
            alpha=alpha,
            mean_read_depth=mean_read_depth,
            target_power=target_power,
        )
        if res.power >= target_power:
            return n
    return max_replicates


def generate_prescription_for_violation(
    violation_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> RemediationPrescription:
    """Generate prescriptive study-design remediation for specific BioNexus failures."""
    meta = metadata or {}
    v_upper = violation_id.upper()

    if "BN-F006" in v_upper or "PSEUDOREPLICATION" in v_upper:
        current_n = int(meta.get("n_donors_min", meta.get("n_replicates", 1)))
        target_fc = float(meta.get("target_log2fc", 1.0))
        disp = float(meta.get("dispersion", 0.25))  # typical human donor dispersion
        power_current = calculate_pseudobulk_power(current_n, log2fc=target_fc, dispersion=disp)
        required_n = calculate_required_replicates(0.80, target_log2fc=target_fc, dispersion=disp)
        diff_n = max(0, required_n - current_n)

        text = (
            f"Remediation Recipe (BN-F006): Biological replicates (N={current_n}) fail to estimate "
            f"within-donor vs between-donor variance (current power: {power_current.power:.1%}). "
            f"To warrant POPULATION_EFFECT at ROBUST maturity, add at least {diff_n} independent donor(s) "
            f"per condition (total N={required_n} per group). "
            f"Alternative in-silico remedy: Aggregate to pseudobulk and demote claim to sample-specific descriptive."
        )

        return RemediationPrescription(
            violation_id="BN-F006",
            primary_strategy=RemediationStrategy.ADD_BIOLOGICAL_REPLICATES.value,
            current_state_summary=f"Unpaired single-cell design with N={current_n} donor(s)/group.",
            target_maturity=ConclusionMaturity.ROBUST.value,
            minimum_required_samples=required_n,
            additional_samples_needed=diff_n,
            power_assessment=power_current,
            analytical_remedies=[
                "Aggregate counts to pseudobulk (donor x cell_type sum).",
                "Apply Empirical Bayes dispersion shrinkage (DESeq2/edgeR).",
                "Cap claim class to descriptive sample ranking if N < 3.",
            ],
            academic_citations=[
                "Squair et al. (2021) Nature Comms 12:5692",
                "Lun & Marioni (2017) Biostatistics 18:451-464",
            ],
            remediation_text=text,
        )

    elif "BN-F001" in v_upper or "RAW_COUNTS" in v_upper:
        text = (
            "Remediation Recipe (BN-F001): Count-based model received non-integer / normalized counts. "
            "Re-load anndata.layers['counts'] or raw AnnData matrix before running pseudobulk DE / scVI."
        )
        return RemediationPrescription(
            violation_id="BN-F001",
            primary_strategy=RemediationStrategy.CORRECT_COUNT_PREPROCESSING.value,
            current_state_summary="Assay matrix is log-normalized or scaled.",
            target_maturity=ConclusionMaturity.ROBUST.value,
            analytical_remedies=[
                "Verify adata.raw or adata.layers['counts'] contains non-negative integer counts.",
                "Do NOT apply log1p or standard scaling prior to negative binomial modeling.",
            ],
            academic_citations=["Love et al. (2014) Genome Biology 15:550"],
            remediation_text=text,
        )

    elif "BN-F005" in v_upper or "FDR" in v_upper:
        text = (
            "Remediation Recipe (BN-F005): Multiple hypothesis testing correction missing. "
            "Apply Benjamini-Hochberg FDR adjustment across all tested genes at alpha=0.05."
        )
        return RemediationPrescription(
            violation_id="BN-F005",
            primary_strategy=RemediationStrategy.APPLY_FDR_CORRECTION.value,
            current_state_summary="Raw p-values reported without FDR control.",
            target_maturity=ConclusionMaturity.SUPPORTED.value,
            analytical_remedies=[
                "Compute adjusted p-values via statsmodels.stats.multitest.multipletests(method='fdr_bh').",
                "Report number of significant genes at padj < 0.05 instead of raw p < 0.05.",
            ],
            academic_citations=["Benjamini & Hochberg (1995) JRSS-B 57:289-300"],
            remediation_text=text,
        )

    elif "BN-F010" in v_upper or "BACKEND" in v_upper:
        text = (
            "Remediation Recipe (BN-F010): Declared gold backend was substituted with unverified implementation. "
            "Ensure PyDESeq2 / Harmonypy / Squidpy is installed and executed directly."
        )
        return RemediationPrescription(
            violation_id="BN-F010",
            primary_strategy=RemediationStrategy.BACKEND_FIDELITY_ENFORCEMENT.value,
            current_state_summary="Execution backend discrepancy detected.",
            target_maturity=ConclusionMaturity.ROBUST.value,
            analytical_remedies=[
                "Install official dependencies via 'pip install -e .[goldchain]'.",
                "Avoid custom numpy reimplementations of complex statistical models.",
            ],
            academic_citations=["BioNexus Scientific Contract BNS-003"],
            remediation_text=text,
        )

    else:
        text = f"Remediation Recipe ({violation_id}): Review experimental design and satisfy required evidence factors."
        return RemediationPrescription(
            violation_id=violation_id,
            primary_strategy=RemediationStrategy.DOWNGRADE_CLAIM_CEILING.value,
            current_state_summary=f"Violation {violation_id} active.",
            target_maturity=ConclusionMaturity.SUPPORTED.value,
            analytical_remedies=["Consult SCIENTIFIC_RULE_CATALOG.json for detailed exception conditions."],
            remediation_text=text,
        )
