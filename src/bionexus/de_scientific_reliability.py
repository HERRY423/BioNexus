"""Descriptive DE reference-label metrics; no automatic scientific certification.

The caller supplies labels and results. Their biological truth, independence,
execution, and experimental replication are not authenticated by these formulas.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class DEHardTruthMetrics:
    n_tested: int
    n_positive_truth: int
    n_negative_truth: int
    tp: int
    fp: int
    tn: int
    fn: int
    sensitivity: Optional[float]
    specificity: Optional[float]
    precision: Optional[float]
    empirical_fdr: Optional[float]  # Legacy name: observed FDP on this reference set.
    nominal_fdr: float
    f1_score: Optional[float]
    fdr_controlled: Optional[bool]
    observed_fdp_within_nominal: Optional[bool] = None
    estimation_status: str = "DESCRIPTIVE_REFERENCE_METRICS"

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result.update(observed_false_discovery_proportion=self.empirical_fdr,
                      fdr_control_status="NOT_ESTABLISHED",
                      scientific_authorization="NONE")
        return result


@dataclass(frozen=True)
class EmpiricalNullMetrics:
    n_null_genes: int
    n_false_discoveries: int
    empirical_fwer: Optional[float]
    ks_statistic: float
    ks_pvalue: float
    null_uniform: Optional[bool]
    description: str
    per_test_rejection_rate: float = 0.0
    uniformity_rejected: bool = False
    fwer_status: str = "NOT_ESTIMABLE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DCAPoint:
    threshold_prob: float
    net_benefit_audited: float
    net_benefit_naive: float
    net_benefit_treat_all: float
    net_benefit_treat_none: float
    net_benefit_gain: float
    avoided_false_claims_per_100: float  # Decision-weight equivalent, not measured claims prevented.

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DecisionCurveAnalysis:
    points: List[DCAPoint] = field(default_factory=list)
    optimal_threshold_range: Optional[Tuple[float, float]] = None
    mean_net_benefit_gain: Optional[float] = None
    max_avoided_false_claims_per_100: Optional[float] = None
    audited_strictly_superior: bool = False
    estimation_status: str = "NOT_ESTIMABLE"

    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["evidence_kind"] = "DESCRIPTIVE_DECISION_WEIGHT_COMPARISON"
        result["scientific_authorization"] = "NONE"
        result["interpretation"] = "Specified loss-weight arithmetic; no external benefit, causal effect, or personnel-time claim."
        return result


@dataclass(frozen=True)
class CrossCohortReplicationResult:
    cohort_a_name: str
    cohort_b_name: str
    n_shared_genes: int
    concordant_direction_count: int
    concordance_rate: Optional[float]
    effect_size_pearson_r: Optional[float]
    effect_size_spearman_rho: Optional[float]
    replication_pass: bool
    estimation_status: str = "DESCRIPTIVE_CONCORDANCE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _validate_results(genes: Sequence[str], pvalues: Sequence[float], effects: Sequence[float]) -> None:
    if len(genes) != len(pvalues) or len(genes) != len(effects):
        raise ValueError("gene_names, padj_values, and log2fc_values must have identical lengths")
    if len(set(genes)) != len(genes) or any(not isinstance(g, str) or not g for g in genes):
        raise ValueError("gene_names must be unique nonempty strings")
    if any(not math.isfinite(p) or not 0 <= p <= 1 for p in pvalues):
        raise ValueError("p-values must be finite probabilities")
    if any(not math.isfinite(x) for x in effects):
        raise ValueError("effect sizes must be finite")


def evaluate_de_hard_truth_calibration(
    *, gene_names: Sequence[str], padj_values: Sequence[float],
    log2fc_values: Sequence[float], ground_truth_positives: Set[str],
    ground_truth_negatives: Set[str], nominal_fdr: float = 0.05,
    min_abs_log2fc: float = 0.5,
) -> DEHardTruthMetrics:
    """Compute descriptive counts on caller-supplied reference labels.

    The observed FDP is not a repeated-experiment FDR estimate. No threshold
    tolerance is added, and missing denominators remain null.
    """
    _validate_results(gene_names, padj_values, log2fc_values)
    if not 0 < nominal_fdr < 1 or not math.isfinite(min_abs_log2fc) or min_abs_log2fc < 0:
        raise ValueError("invalid significance or effect-size threshold")
    if ground_truth_positives & ground_truth_negatives:
        raise ValueError("positive and negative reference labels must be disjoint")
    tp = fp = tn = fn = 0
    for gene, p, effect in zip(gene_names, padj_values, log2fc_values):
        called = p <= nominal_fdr and abs(effect) >= min_abs_log2fc
        if gene in ground_truth_positives:
            tp += int(called)
            fn += int(not called)
        elif gene in ground_truth_negatives:
            fp += int(called)
            tn += int(not called)
    pos, neg, calls = tp + fn, tn + fp, tp + fp
    fdp = fp / calls if calls else None
    return DEHardTruthMetrics(
        n_tested=pos + neg, n_positive_truth=pos, n_negative_truth=neg,
        tp=tp, fp=fp, tn=tn, fn=fn,
        sensitivity=tp / pos if pos else None,
        specificity=tn / neg if neg else None,
        precision=tp / calls if calls else None,
        empirical_fdr=fdp, nominal_fdr=nominal_fdr,
        f1_score=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        fdr_controlled=None,
        observed_fdp_within_nominal=fdp <= nominal_fdr if fdp is not None else None,
        estimation_status="DESCRIPTIVE_REFERENCE_METRICS" if pos and neg and calls else "PARTIALLY_NOT_ESTIMABLE",
    )


def evaluate_empirical_null_uniformity(
    *, null_p_values: Sequence[float], nominal_alpha: float = 0.05,
) -> EmpiricalNullMetrics:
    """Describe supplied p-values; cannot establish biological nulls or FWER.

    A non-rejection of the KS null is not a proof of uniformity. KS assumes
    independent observations, which correlated gene p-values may not satisfy.
    """
    pvalues = np.asarray(null_p_values, dtype=float)
    if pvalues.ndim != 1 or pvalues.size == 0:
        raise ValueError("null_p_values must contain at least one valid finite probability")
    if not np.all(np.isfinite(pvalues)) or np.any((pvalues < 0) | (pvalues > 1)):
        raise ValueError("null_p_values must contain only valid finite probabilities")
    if not 0 < nominal_alpha < 1:
        raise ValueError("nominal_alpha must be in (0, 1)")
    count = int(np.sum(pvalues <= nominal_alpha))
    ks = stats.kstest(pvalues, "uniform")
    return EmpiricalNullMetrics(
        n_null_genes=len(pvalues), n_false_discoveries=count, empirical_fwer=None,
        ks_statistic=float(ks.statistic), ks_pvalue=float(ks.pvalue), null_uniform=None,
        per_test_rejection_rate=count / len(pvalues), uniformity_rejected=bool(ks.pvalue < .01),
        description="Descriptive per-test rejection rate and KS test of supplied p-values. Biological null identity, independence, and family-wise error are not established.",
    )


def _validate_counts(metrics: DEHardTruthMetrics) -> None:
    values = [metrics.tp, metrics.fp, metrics.tn, metrics.fn, metrics.n_tested,
              metrics.n_positive_truth, metrics.n_negative_truth]
    if any(not isinstance(v, (int, np.integer)) or isinstance(v, bool) or v < 0 for v in values):
        raise ValueError("confusion counts must be nonnegative integers")
    if (metrics.tp + metrics.fn != metrics.n_positive_truth or
            metrics.fp + metrics.tn != metrics.n_negative_truth or
            metrics.n_tested != metrics.n_positive_truth + metrics.n_negative_truth):
        raise ValueError("inconsistent confusion counts")


def compute_decision_curve_analysis(
    *, audited_metrics: DEHardTruthMetrics, naive_metrics: DEHardTruthMetrics,
    threshold_probabilities: Optional[Sequence[float]] = None,
) -> DecisionCurveAnalysis:
    """Compare counts on the same reference population at specified loss weights."""
    _validate_counts(audited_metrics)
    _validate_counts(naive_metrics)
    if (audited_metrics.n_tested, audited_metrics.n_positive_truth, audited_metrics.n_negative_truth) != (
        naive_metrics.n_tested, naive_metrics.n_positive_truth, naive_metrics.n_negative_truth
    ):
        raise ValueError("DCA requires the same reference population in both arms")
    thresholds = list(threshold_probabilities) if threshold_probabilities is not None else [.01, .05, .1, .15, .2, .25, .3, .35, .4, .5]
    if any(not math.isfinite(p) or not 0 < p < 1 for p in thresholds):
        raise ValueError("decision thresholds must be finite probabilities in (0, 1)")
    if len(set(thresholds)) != len(thresholds):
        raise ValueError("decision thresholds must be unique")
    n = audited_metrics.n_tested
    if not n or not thresholds or not audited_metrics.n_positive_truth or not audited_metrics.n_negative_truth:
        return DecisionCurveAnalysis()
    points = []
    for p in thresholds:
        odds = p / (1 - p)
        audited = (audited_metrics.tp - audited_metrics.fp * odds) / n
        naive = (naive_metrics.tp - naive_metrics.fp * odds) / n
        gain = audited - naive
        points.append(DCAPoint(
            p, audited, naive,
            (audited_metrics.n_positive_truth - audited_metrics.n_negative_truth * odds) / n,
            0.0, gain, gain / odds * 100,
        ))
    return DecisionCurveAnalysis(
        points=points,
        mean_net_benefit_gain=float(np.mean([p.net_benefit_gain for p in points])),
        max_avoided_false_claims_per_100=max(p.avoided_false_claims_per_100 for p in points),
        audited_strictly_superior=all(p.net_benefit_gain > 0 for p in points),
        estimation_status="DESCRIPTIVE_COMPARISON_ONLY",
    )


def audit_multi_cohort_de_replication(
    *, cohort_a_name: str, cohort_b_name: str, genes_a: Sequence[str],
    log2fc_a: Sequence[float], padj_a: Sequence[float], genes_b: Sequence[str],
    log2fc_b: Sequence[float], padj_b: Sequence[float], nominal_fdr: float = .05,
    min_shared_genes: int = 10,
) -> CrossCohortReplicationResult:
    """Describe shared significant genes; caller-provided names do not prove independence."""
    _validate_results(genes_a, padj_a, log2fc_a)
    _validate_results(genes_b, padj_b, log2fc_b)
    if min_shared_genes < 2 or not 0 < nominal_fdr < 1:
        raise ValueError("at least two genes and a valid nominal threshold are required")
    a = dict(zip(genes_a, zip(log2fc_a, padj_a)))
    b = dict(zip(genes_b, zip(log2fc_b, padj_b)))
    shared = [g for g in a if g in b and (a[g][1] <= nominal_fdr or b[g][1] <= nominal_fdr)]
    # Do not silently change the endpoint to all genes if the selected set is small.
    if len(shared) < min_shared_genes:
        return CrossCohortReplicationResult(cohort_a_name, cohort_b_name, len(shared), 0, None, None, None, False, "NOT_ESTIMABLE")
    av, bv = np.array([a[g][0] for g in shared]), np.array([b[g][0] for g in shared])
    concordant = int(np.sum((np.sign(av) == np.sign(bv)) & (av != 0) & (bv != 0)))
    rate = concordant / len(shared)
    pearson = spearman = None
    if np.ptp(av) > 0 and np.ptp(bv) > 0:
        pearson = float(stats.pearsonr(av, bv).statistic)
        spearman = float(stats.spearmanr(av, bv).statistic)
    return CrossCohortReplicationResult(
        cohort_a_name, cohort_b_name, len(shared), concordant, rate, pearson, spearman,
        bool(pearson is not None and spearman is not None and rate >= .70 and pearson >= .50 and spearman >= .60),
        "DESCRIPTIVE_CONCORDANCE" if pearson is not None else "PARTIALLY_NOT_ESTIMABLE",
    )
