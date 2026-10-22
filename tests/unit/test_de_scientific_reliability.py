"""
Unit tests for BioNexus Pseudobulk DE Scientific Reliability & Decision Net Benefit Engine.
Validates:
1. Hard biological truth evaluation & empirical FDR control
2. Empirical null distribution uniformity testing (Kolmogorov-Smirnov)
3. Decision Curve Analysis (DCA) net benefit metrics & avoided false discovery claims
4. Multi-cohort cross-platform concordance audit
"""

import numpy as np
import pytest

from bionexus.de_scientific_reliability import (
    CrossCohortReplicationResult,
    DecisionCurveAnalysis,
    DEHardTruthMetrics,
    EmpiricalNullMetrics,
    audit_multi_cohort_de_replication,
    compute_decision_curve_analysis,
    evaluate_de_hard_truth_calibration,
    evaluate_empirical_null_uniformity,
)


def test_de_hard_truth_calibration_perfect_control():
    """Test empirical FDR calculation with perfect sensitivity and specificity."""
    genes = ["ISG15", "IFIT1", "OAS1", "ACTB", "GAPDH", "TUBB"]
    padj = [1e-5, 2e-4, 1e-6, 0.85, 0.92, 0.77]
    log2fc = [3.2, 2.8, 4.1, 0.02, -0.05, 0.08]
    positives = {"ISG15", "IFIT1", "OAS1"}
    negatives = {"ACTB", "GAPDH", "TUBB"}

    metrics = evaluate_de_hard_truth_calibration(
        gene_names=genes,
        padj_values=padj,
        log2fc_values=log2fc,
        ground_truth_positives=positives,
        ground_truth_negatives=negatives,
        nominal_fdr=0.05,
        min_abs_log2fc=0.5,
    )

    assert isinstance(metrics, DEHardTruthMetrics)
    assert metrics.tp == 3
    assert metrics.tn == 3
    assert metrics.fp == 0
    assert metrics.fn == 0
    assert metrics.sensitivity == 1.0
    assert metrics.specificity == 1.0
    assert metrics.precision == 1.0
    assert metrics.empirical_fdr == 0.0
    assert metrics.fdr_controlled is None  # A single reference set does not estimate procedure FDR.
    assert metrics.observed_fdp_within_nominal is True


def test_de_hard_truth_calibration_length_mismatch():
    """Test that mismatched input arrays raise ValueError."""
    with pytest.raises(ValueError, match="identical lengths"):
        evaluate_de_hard_truth_calibration(
            gene_names=["ISG15", "ACTB"],
            padj_values=[0.01],
            log2fc_values=[2.0, 0.1],
            ground_truth_positives={"ISG15"},
            ground_truth_negatives={"ACTB"},
        )


def test_de_hard_truth_calibration_with_false_positives():
    """Test empirical FDR reflects false positive discoveries correctly."""
    genes = ["ISG15", "ACTB", "GAPDH"]
    # ACTB is negative but passes significance threshold -> FP
    padj = [0.001, 0.002, 0.8]
    log2fc = [2.5, 1.2, 0.1]
    positives = {"ISG15"}
    negatives = {"ACTB", "GAPDH"}

    metrics = evaluate_de_hard_truth_calibration(
        gene_names=genes,
        padj_values=padj,
        log2fc_values=log2fc,
        ground_truth_positives=positives,
        ground_truth_negatives=negatives,
        nominal_fdr=0.05,
        min_abs_log2fc=0.5,
    )

    assert metrics.tp == 1
    assert metrics.fp == 1
    assert metrics.tn == 1
    assert metrics.fn == 0
    assert metrics.precision == 0.5
    assert metrics.empirical_fdr == 0.5
    assert metrics.fdr_controlled is None
    assert metrics.observed_fdp_within_nominal is False


def test_empirical_null_uniformity_pass():
    """Test KS uniformity test on genuine uniform p-values."""
    # Perfectly spaced uniform quantiles
    uniform_pvals = np.linspace(0.001, 0.999, 500)
    metrics = evaluate_empirical_null_uniformity(null_p_values=uniform_pvals, nominal_alpha=0.05)

    assert isinstance(metrics, EmpiricalNullMetrics)
    assert metrics.null_uniform is None  # KS non-rejection is not proof of uniformity.
    assert metrics.uniformity_rejected is False
    assert metrics.empirical_fwer is None
    assert metrics.per_test_rejection_rate == .05
    assert metrics.ks_pvalue >= 0.01


def test_empirical_null_uniformity_fail_skewed():
    """Test KS test correctly flags severely distorted / anti-conservative null distribution."""
    # Heavily biased towards 0 (simulating false positive inflation under pseudoreplication)
    inflated_pvals = np.concatenate([np.repeat(0.001, 200), np.linspace(0.05, 1.0, 300)])
    metrics = evaluate_empirical_null_uniformity(null_p_values=inflated_pvals, nominal_alpha=0.05)

    assert metrics.null_uniform is None
    assert metrics.uniformity_rejected is True
    assert metrics.ks_pvalue < 0.01
    assert metrics.n_false_discoveries >= 200


def test_compute_de_decision_curves():
    """Test Decision Curve Analysis (DCA) net benefit calculation and superiority."""
    audited = DEHardTruthMetrics(
        n_tested=100,
        n_positive_truth=50,
        n_negative_truth=50,
        tp=50,
        fp=0,
        tn=50,
        fn=0,
        sensitivity=1.0,
        specificity=1.0,
        precision=1.0,
        empirical_fdr=0.0,
        nominal_fdr=0.05,
        f1_score=1.0,
        fdr_controlled=True,
    )
    naive = DEHardTruthMetrics(
        n_tested=100,
        n_positive_truth=50,
        n_negative_truth=50,
        tp=50,
        fp=35,
        tn=15,
        fn=0,
        sensitivity=1.0,
        specificity=0.30,
        precision=0.588,
        empirical_fdr=0.412,
        nominal_fdr=0.05,
        f1_score=0.74,
        fdr_controlled=False,
    )

    dca = compute_decision_curve_analysis(
        audited_metrics=audited,
        naive_metrics=naive,
        threshold_probabilities=[0.05, 0.10, 0.20, 0.30, 0.40],
    )

    assert isinstance(dca, DecisionCurveAnalysis)
    assert len(dca.points) == 5
    assert dca.mean_net_benefit_gain > 0.0
    assert dca.max_avoided_false_claims_per_100 > 0.0
    assert dca.audited_strictly_superior is True


def test_audit_cross_cohort_replication():
    """Test cross-cohort directional concordance and correlation auditing."""
    shared_genes = [f"GENE_{i}" for i in range(10)]
    lfc_a = [2.0, -1.5, 3.2, 0.8, -2.1, 1.4, -0.9, 2.5, -1.8, 0.5]
    # Identical signs with slight variation
    lfc_b = [1.8, -1.3, 3.0, 0.9, -1.9, 1.5, -0.7, 2.2, -1.6, 0.6]

    padj_a = [0.001] * 10
    padj_b = [0.001] * 10

    res = audit_multi_cohort_de_replication(
        cohort_a_name="10x_GSE96583",
        cohort_b_name="Parse_10M",
        genes_a=shared_genes,
        log2fc_a=lfc_a,
        padj_a=padj_a,
        genes_b=shared_genes,
        log2fc_b=lfc_b,
        padj_b=padj_b,
        nominal_fdr=0.05,
        min_shared_genes=10,
    )

    assert isinstance(res, CrossCohortReplicationResult)
    assert res.n_shared_genes == 10
    assert res.concordance_rate == 1.0
    assert res.effect_size_pearson_r > 0.95
    assert res.replication_pass is True
