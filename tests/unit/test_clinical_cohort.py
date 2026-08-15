"""
Unit tests for Clinical Multi-Cohort Analysis suite:
Kaplan-Meier survival estimator, Log-rank test, Cox Hazard Ratios, DepMap synthetic lethality, and immune deconvolution.
"""

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
import sys

# Add skill script directories to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "skills" / "clinical-cohort-analysis" / "scripts"))

from survival_analyzer import (
    compute_kaplan_meier,
    log_rank_test,
    calculate_cox_hazard_ratio
)
from synthetic_lethality import (
    analyze_synthetic_lethal_interaction
)
from immune_deconvolution import (
    deconvolve_immune_microenvironment
)


def test_kaplan_meier_and_log_rank():
    """Test Kaplan-Meier survival curves and Log-rank test."""
    np.random.seed(42)
    times_a = np.array([5.0, 10.0, 15.0, 20.0, 25.0])
    events_a = np.array([1, 1, 1, 0, 1])

    km_times, km_probs, med_os = compute_kaplan_meier(times_a, events_a)
    assert len(km_times) == len(km_probs)
    assert km_probs[0] == 1.0
    assert km_probs[-1] < 1.0
    assert med_os > 0.0

    times_b = np.array([20.0, 30.0, 40.0, 50.0, 60.0])
    events_b = np.array([1, 1, 0, 1, 0])

    chi2_stat, p_val = log_rank_test(times_a, events_a, times_b, events_b)
    assert chi2_stat > 0.0
    assert 0.0 <= p_val <= 1.0


def test_cox_hazard_ratio():
    """Test Cox Proportional Hazards regression and prognostic stratification."""
    times = np.array([5.0, 8.0, 12.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 60.0])
    events = np.array([1, 1, 1, 1, 0, 1, 0, 1, 0, 0])
    groups = np.array([1, 1, 1, 1, 1, 0, 0, 0, 0, 0])  # Group 1 has early events

    res = calculate_cox_hazard_ratio(times, events, groups)
    assert res["method"] in {"lifelines_coxph", "event_rate_ratio_not_cox"}
    if res["method"] == "lifelines_coxph":
        assert res["hazard_ratio"] > 1.0
        assert len(res["hazard_ratio_95_ci"]) == 2
    else:
        assert res.get("event_rate_ratio", res.get("hazard_ratio", 0)) > 1.0


def test_synthetic_lethality_mining():
    """Test DepMap CERES dependency correlation and synthetic lethal evaluation."""
    np.random.seed(42)
    ceres_mut = np.random.normal(-0.85, 0.15, size=15)  # Highly dependent (negative CERES)
    ceres_wt = np.random.normal(-0.15, 0.15, size=20)   # Not dependent

    res = analyze_synthetic_lethal_interaction("KRAS", "CDK4", ceres_mut, ceres_wt)
    assert res["is_synthetic_lethal"] is True
    assert res["cohens_d_effect_size"] < -1.0
    assert res["p_value"] < 0.001
    assert "Caller-array screen" in res["therapeutic_verdict"]


def test_immune_microenvironment_deconvolution():
    """Test NNLS immune cell fraction deconvolution."""
    np.random.seed(42)
    bulk_tpm = np.random.exponential(10.0, size=(3, 50))
    gene_names = [f"Gene_{i}" for i in range(50)]

    signature = np.random.exponential(10.0, size=(50, 6))
    deconv_df = deconvolve_immune_microenvironment(
        bulk_tpm, gene_names, reference_signature_matrix=signature
    )
    assert deconv_df.shape == (3, 6)
    # Check row sums equal 1.0 (normalized fractions)
    row_sums = deconv_df.sum(axis=1).values
    for s in row_sums:
        assert np.isclose(s, 1.0, atol=1e-3)
