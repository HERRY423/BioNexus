"""
Unit tests for statistical-level rules: MDE estimation, effect-size regimes,
power assessment, and doublet-risk advisories (BNS-007 / BN-F002 / BN-F003).
"""

from __future__ import annotations

import math

import pytest

from bionexus.statistical_rules import (
    DOUBLET_RATE_ADVISORY_THRESHOLD,
    MODERATE_EFFECT_LOG2FC,
    STRONG_EFFECT_LOG2FC,
    EffectSizeRegime,
    assess_doublet_risk,
    assess_statistical_power,
    classify_effect_size_regime,
    estimate_min_detectable_effect,
)

# ---------------------------------------------------------------------------
# MDE estimation
# ---------------------------------------------------------------------------


def test_mde_decreases_with_more_donors():
    mde_n2 = estimate_min_detectable_effect(n_donors_per_group=2)
    mde_n5 = estimate_min_detectable_effect(n_donors_per_group=5)
    mde_n10 = estimate_min_detectable_effect(n_donors_per_group=10)
    assert mde_n2 > mde_n5 > mde_n10 > 0


def test_mde_increases_with_dispersion():
    assert estimate_min_detectable_effect(n_donors_per_group=3, dispersion=1.0) > (
        estimate_min_detectable_effect(n_donors_per_group=3, dispersion=0.1)
    )


def test_mde_deterministic_and_finite():
    a = estimate_min_detectable_effect(n_donors_per_group=2, dispersion=0.4)
    b = estimate_min_detectable_effect(n_donors_per_group=2, dispersion=0.4)
    assert a == b and math.isfinite(a)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_donors_per_group": 0},
        {"n_donors_per_group": 2, "mean_count_per_cell": 0},
        {"n_donors_per_group": 2, "dispersion": -0.1},
        {"n_donors_per_group": 2, "cells_per_sample": 0},
    ],
)
def test_mde_rejects_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        estimate_min_detectable_effect(**kwargs)


def test_n2_mde_exceeds_moderate_threshold():
    """The BF-010 regime: at n=2/group the design cannot detect moderate effects."""
    mde = estimate_min_detectable_effect(n_donors_per_group=2)
    assert mde > MODERATE_EFFECT_LOG2FC


# ---------------------------------------------------------------------------
# Effect-size regime classification (no magic-number refusals)
# ---------------------------------------------------------------------------


def test_regime_boundaries():
    assert classify_effect_size_regime(6.0) is EffectSizeRegime.STRONG
    assert classify_effect_size_regime(STRONG_EFFECT_LOG2FC) is EffectSizeRegime.STRONG
    assert classify_effect_size_regime(2.0) is EffectSizeRegime.MODERATE
    assert classify_effect_size_regime(0.7) is EffectSizeRegime.SUBTLE
    assert classify_effect_size_regime(None) is None
    # sign-symmetric
    assert classify_effect_size_regime(-5.0) is EffectSizeRegime.STRONG


def test_power_assessment_low_replication_carries_power_remedy():
    assessment = assess_statistical_power(n_donors_per_group=2, observed_log2fc=0.8)
    assert not assessment.sufficient_for_population_claims
    joined = " ".join(assessment.remedies).lower()
    assert "power" in joined
    assert any("log2fc" in w.lower() for w in assessment.warnings)


def test_power_assessment_subtle_effect_low_n_flags_regime_mismatch():
    assessment = assess_statistical_power(n_donors_per_group=2, observed_log2fc=0.3)
    assert any("subtle" in w.lower() for w in assessment.warnings)


def test_power_assessment_strong_effect_relaxes_but_discloses():
    """Ladder stage 4: strong effects legitimately need less replication."""
    assessment = assess_statistical_power(n_donors_per_group=2, observed_log2fc=6.0)
    assert any("strong" in w.lower() for w in assessment.warnings)
    assert any("cohort-specific" in r.lower() or "descriptive" in r.lower() for r in assessment.remedies)


def test_power_assessment_well_powered_design_has_no_warnings():
    assessment = assess_statistical_power(
        n_donors_per_group=6, observed_log2fc=2.0, dispersion=0.2, cells_per_sample=500
    )
    assert assessment.warnings == []
    assert assessment.remedies == []


def test_power_to_dict_roundtrip():
    d = assess_statistical_power(n_donors_per_group=2).to_dict()
    assert d["sufficient_for_population_claims"] is False
    assert "mde_log2fc" in d and "rule_basis" in d


# ---------------------------------------------------------------------------
# Doublet risk
# ---------------------------------------------------------------------------


def test_doublet_below_threshold_is_silent():
    assert assess_doublet_risk(0.05) is not None
    assert assess_doublet_risk(0.05).exceeds_threshold is False


def test_doublet_above_threshold_advises():
    res = assess_doublet_risk(0.18)
    assert res.exceeds_threshold is True
    joined = " ".join(res.remedies).lower()
    assert "doublet" in joined
    assert any("scrublet" in joined or "doubletfinder" in joined for _ in [1])


def test_doublet_none_or_nonpositive_returns_none():
    assert assess_doublet_risk(None) is None
    assert assess_doublet_risk(0.0) is None


def test_doublet_threshold_constant_matches_bench_expectation():
    assert abs(DOUBLET_RATE_ADVISORY_THRESHOLD - 0.10) < 1e-9
