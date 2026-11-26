"""
Unit tests for statistical-level rules: MDE estimation, effect-size regimes,
power assessment, and doublet-risk advisories (BNS-007 / BN-F002 / BN-F003).
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from statistics import NormalDist

import pytest

from bionexus.empirical_warrant import CalibrationRegistry
from bionexus.statistical_rules import (
    DOUBLET_RATE_ADVISORY_THRESHOLD,
    MODERATE_EFFECT_LOG2FC,
    STATISTICAL_THRESHOLDS,
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


def test_mde_scales_with_inverse_sqrt_donor_count():
    small = estimate_min_detectable_effect(n_donors_per_group=5)
    large = estimate_min_detectable_effect(n_donors_per_group=20)
    assert small / large == pytest.approx(2)
    assert not assess_statistical_power(n_donors_per_group=5).sufficient_for_population_claims


def test_mde_uses_fdr_and_records_single_test_alpha_basis():
    default = assess_statistical_power(n_donors_per_group=3)
    strict = assess_statistical_power(n_donors_per_group=3, n_tests=15000, n_true_effects=300)
    assert default.mde_log2fc == pytest.approx(2.36, abs=0.01)
    assert default.alpha_basis == "fdr_as_alpha_optimistic"
    assert assess_statistical_power(n_donors_per_group=3, n_tests=15000).alpha_basis == default.alpha_basis
    assert strict.mde_log2fc == pytest.approx(3.52, abs=0.02)
    assert strict.per_test_alpha == pytest.approx(0.8 * 300 * 0.05 / (14700 * 0.95))
    assert strict.to_dict()["alpha_basis"] == "jung2005"
    assert estimate_min_detectable_effect(n_donors_per_group=3, nominal_fdr=0.01) > default.mde_log2fc


def test_mde_at_half_power_uses_zero_power_quantile():
    expected = NormalDist().inv_cdf(0.975) * math.sqrt(2 * (0.01 + 0.5) / 4) / math.log(2)
    assert estimate_min_detectable_effect(n_donors_per_group=4, target_power=0.5) == pytest.approx(expected)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_donors_per_group": 0},
        {"n_donors_per_group": 1},
        {"n_donors_per_group": 2, "target_power": 1},
        {"n_donors_per_group": 2, "nominal_fdr": 0},
        {"n_donors_per_group": 2, "n_tests": 0},
        {"n_donors_per_group": 2, "n_tests": 1000, "n_true_effects": 1000},
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


@pytest.mark.parametrize("effect, regime", [
    (STRONG_EFFECT_LOG2FC, EffectSizeRegime.STRONG), (-5.0, EffectSizeRegime.STRONG),
    (2.0, EffectSizeRegime.MODERATE), (0.7, EffectSizeRegime.SUBTLE),
])
def test_regime_boundaries(effect, regime):
    assert classify_effect_size_regime(shrunk_log2fc=effect, base_mean=100) is regime


def test_raw_and_low_expression_effects_do_not_establish_magnitude():
    assert classify_effect_size_regime(9.0, base_mean=100) is None
    assert classify_effect_size_regime(shrunk_log2fc=9.0) is None
    assert classify_effect_size_regime(shrunk_log2fc=9.0, base_mean=1) is None
    assert classify_effect_size_regime(9.0, shrunk_log2fc=0.3, base_mean=100) is EffectSizeRegime.SUBTLE


def test_power_assessment_low_replication_carries_power_remedy():
    assessment = assess_statistical_power(n_donors_per_group=2, observed_log2fc=0.8)
    assert not assessment.sufficient_for_population_claims
    joined = " ".join(assessment.remedies).lower()
    assert "power" in joined
    assert any("log2fc" in w.lower() for w in assessment.warnings)


def test_power_assessment_subtle_effect_low_n_flags_regime_mismatch():
    assessment = assess_statistical_power(n_donors_per_group=2, shrunk_log2fc=0.3, base_mean=50)
    assert any("subtle" in w.lower() for w in assessment.warnings)


def test_strong_effect_with_limited_replication_is_cohort_specific():
    assessment = assess_statistical_power(n_donors_per_group=2, shrunk_log2fc=6.0, base_mean=50)
    assert not assessment.sufficient_for_population_claims
    assert any("strong" in w.lower() for w in assessment.warnings)
    assert any("cohort-specific" in r.lower() or "descriptive" in r.lower() for r in assessment.remedies)


def test_power_assessment_well_powered_design_has_no_warnings():
    assessment = assess_statistical_power(
        n_donors_per_group=12, shrunk_log2fc=2.0, base_mean=100, dispersion=0.2, cells_per_sample=500
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


def test_doublet_advisory_uses_reviewed_platform_and_cell_loading():
    from evals.annotation_calibration_fixture import synthetic_annotation_context, synthetic_annotation_registry

    profile = next(p for p in synthetic_annotation_registry().profiles if p.metric == "doublet_rate")
    profiles = [
        replace(profile, profile_id="low_load", threshold=0.05, cells_loaded_range=(1, 2000)),
        replace(profile, profile_id="high_load", threshold=0.12, cells_loaded_range=(2001, 6000)),
    ]
    registry = CalibrationRegistry.from_dict({"profiles": [p.to_dict() for p in profiles]})
    for load, flagged, basis in [(1000, True, "low_load"), (5000, False, "high_load"), (8000, False, "screening_advisory")]:
        result = assess_doublet_risk(0.08, calibration_context=synthetic_annotation_context(cells_loaded=load),
                                    calibration_registry=registry)
        assert result.exceeds_threshold is flagged
        assert result.threshold_basis.startswith(basis)


def test_catalog_and_readme_reference_runtime_registry_thresholds():
    root = Path(__file__).resolve().parents[2]
    catalog = json.loads((root / "review/SCIENTIFIC_RULE_CATALOG.json").read_text(encoding="utf-8"))
    rules = {r["id"]: r for r in catalog["rules"]}
    readme = (root / "README.md").read_text(encoding="utf-8")
    for pointer in (rules["INV-001"]["effect_regime_threshold"], rules["INV-001"]["expression_floor"],
                    rules["INV-008"]["current_value"]["screening_advisory"]):
        path, key = pointer.split("#/statistical_thresholds/")
        registry = json.loads((root / path).read_text(encoding="utf-8"))
        assert registry["statistical_thresholds"][key] == STATISTICAL_THRESHOLDS[key]
        assert path in readme and key in readme
