"""
Unit tests for BioNexus Cell Annotation Physical FACS Ground Truth, Blinding & Calibration Engine.
Validates:
1. Conservative Wilson score lower bounds
2. Multi-class Expected Calibration Error (ECE), MCE, and Brier score
3. Selective abstention curve across the warrant ladder (SUPPORTED vs TENTATIVE vs ABSTAIN)
4. Blinded physical FACS-sorted ground truth evaluation benchmark
"""

import hashlib

import numpy as np
import pytest

from bionexus.annotation_calibration_audit import (
    CalibrationMetrics,
    FACSGroundTruthAuditResult,
    compute_calibration_metrics,
    compute_wilson_lower_bound,
    evaluate_facs_physical_ground_truth_benchmark,
    evaluate_selective_abstention_curve,
)


def test_compute_wilson_lower_bound():
    """Test conservative Wilson score confidence intervals."""
    assert compute_wilson_lower_bound(0, 0) is None
    assert compute_wilson_lower_bound(0, 100) == 0.0

    # 100 successes out of 100 trials: lower bound should be bounded and conservative (~0.96)
    low_100 = compute_wilson_lower_bound(100, 100)
    assert 0.95 <= low_100 < 1.0

    # 95 successes out of 100 trials:
    low_95 = compute_wilson_lower_bound(95, 100)
    assert 0.88 <= low_95 < 0.95


def test_compute_calibration_metrics_perfect_calibration():
    """Test ECE and Brier score for well-calibrated predictions."""
    # 4 classes, 400 samples perfectly calibrated
    probs = np.zeros((400, 4), dtype=np.float64)
    # 100 samples per class with high confidence 0.95
    gt = np.zeros(400, dtype=int)
    for c in range(4):
        start = c * 100
        end = (c + 1) * 100
        gt[start:end] = c
        probs[start:end, :] = 0.01
        probs[start:end, c] = 0.97

    metrics = compute_calibration_metrics(
        probabilities=probs,
        ground_truth_indices=gt,
        n_bins=10,
    )

    assert isinstance(metrics, CalibrationMetrics)
    assert metrics.n_samples == 400
    assert metrics.expected_calibration_error < 0.05
    assert metrics.brier_score < 0.10
    assert metrics.is_well_calibrated is None
    assert metrics.ece_below_threshold is True


def test_compute_calibration_metrics_miscalibrated():
    """Test that severely overconfident wrong predictions produce high ECE."""
    probs = np.zeros((100, 2), dtype=np.float64)
    # Predicting class 0 with 0.99 confidence
    probs[:, 0] = 0.99
    probs[:, 1] = 0.01
    # But true label is class 1
    gt = np.ones(100, dtype=int)

    metrics = compute_calibration_metrics(
        probabilities=probs,
        ground_truth_indices=gt,
        n_bins=10,
    )

    assert metrics.is_well_calibrated is None
    assert metrics.ece_below_threshold is False
    assert metrics.expected_calibration_error > 0.50
    assert metrics.maximum_calibration_error > 0.50


def test_compute_calibration_metrics_empty():
    """Test empty probabilities array raises ValueError."""
    with pytest.raises(ValueError, match="cannot be empty"):
        compute_calibration_metrics(
            probabilities=np.empty((0, 2)),
            ground_truth_indices=np.empty(0, dtype=int),
        )


def test_evaluate_selective_abstention_curve():
    """Test that selective abstention enriches precision on accepted predictions."""
    verdicts = ["SUPPORTED"] * 80 + ["TENTATIVE"] * 10 + ["ABSTAIN"] * 10
    # SUPPORTED calls are 100% accurate (80/80)
    # TENTATIVE calls are 50% accurate (5/10)
    # ABSTAIN calls are 0% accurate (0/10)
    preds = ["T"] * 80 + ["T"] * 5 + ["B"] * 5 + ["B"] * 10
    gt = ["T"] * 80 + ["T"] * 5 + ["T"] * 5 + ["T"] * 10

    curve = evaluate_selective_abstention_curve(
        warrant_verdicts=verdicts,
        predictions=preds,
        ground_truth_labels=gt,
    )

    assert len(curve) == 3
    all_calls, non_abstain, supported_only = curve

    assert all_calls.warrant_tier == "ALL_CALLS"
    assert all_calls.n_accepted == 100
    assert all_calls.accuracy_on_accepted == 0.85

    assert non_abstain.warrant_tier == "NON_ABSTAIN"
    assert non_abstain.n_accepted == 90
    assert non_abstain.accuracy_on_accepted == (85 / 90)

    assert supported_only.warrant_tier == "SUPPORTED_ONLY"
    assert supported_only.n_accepted == 80
    assert supported_only.accuracy_on_accepted == 1.0


def test_evaluate_facs_physical_ground_truth_benchmark():
    """Test complete FACS physical ground truth benchmark execution and blinding verification."""
    genes = ["CD3D", "MS4A1", "LYZ"]
    marker_modules = {
        "T": ["CD3D"],
        "B": ["MS4A1"],
        "MONOCYTE": ["LYZ"],
    }
    # 6 cells: 2 T cells, 2 B cells, 2 Monocytes
    counts = np.array([
        [50, 0, 0],   # T
        [45, 1, 0],   # T
        [0, 60, 0],   # B
        [1, 55, 0],   # B
        [0, 0, 70],   # Monocyte
        [0, 0, 65],   # Monocyte
    ], dtype=float)

    truth = ["T", "T", "B", "B", "MONOCYTE", "MONOCYTE"]
    correct_hash = hashlib.sha256(",".join(truth).encode("utf-8")).hexdigest()

    result = evaluate_facs_physical_ground_truth_benchmark(
        dataset_name="synthetic_facs_test",
        raw_counts_matrix=counts,
        gene_names=genes,
        physical_ground_truth=truth,
        marker_modules=marker_modules,
        blinded_key_hash=correct_hash,
        confidence_margin_threshold=0.50,
    )

    assert isinstance(result, FACSGroundTruthAuditResult)
    assert result.blinding_verified is False
    assert result.reference_hash_matches is True
    assert result.positive_candidate_promoted is False
    assert result.overall_accuracy == 1.0
    assert result.supported_tier_precision == 1.0
    assert result.calibration.is_well_calibrated is None
    assert result.calibration.ece_below_threshold is True


def test_facs_benchmark_blinding_failure():
    """Test that altered ground truth key invalidates blinding check."""
    counts = np.array([[10, 0], [0, 10]], dtype=float)
    result = evaluate_facs_physical_ground_truth_benchmark(
        dataset_name="blinding_test",
        raw_counts_matrix=counts,
        gene_names=["CD3D", "MS4A1"],
        physical_ground_truth=["T", "B"],
        marker_modules={"T": ["CD3D"], "B": ["MS4A1"]},
        blinded_key_hash="invalid_hash_value_does_not_match",
    )
    assert result.blinding_verified is False
