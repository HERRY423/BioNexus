"""
Unit tests for Pseudobulk Inferential Warrant & Epistemic Boundary Engine.
"""

from __future__ import annotations

import pytest

from bionexus.claim_checker import audit_prohibited_claims
from bionexus.contracts import ConclusionMaturity
from bionexus.pseudobulk_warrant import (
    InferentialRegime,
    evaluate_pseudobulk_inferential_warrant,
)
from bionexus.statistical_rules import assess_statistical_power


def test_population_inference_regime():
    """Adequate replicate count and planning power permit population inference."""
    verdict = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=32,
        min_cells_per_sample=50,
        is_raw_counts=True,
    )
    assert verdict.regime == InferentialRegime.POPULATION_INFERENCE
    assert verdict.permitted is True
    assert verdict.population_claims_allowed is True
    assert verdict.causal_claims_allowed is False
    assert verdict.maturity_ceiling in (ConclusionMaturity.SUPPORTED, ConclusionMaturity.ROBUST)


def test_descriptive_only_regime():
    """N = 2 replicates caps inference at PRELIMINARY descriptive claims."""
    verdict = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=2,
        min_cells_per_sample=30,
        is_raw_counts=True,
    )
    assert verdict.regime == InferentialRegime.DESCRIPTIVE_ONLY
    assert verdict.permitted is True
    assert verdict.population_claims_allowed is False
    assert verdict.maturity_ceiling == ConclusionMaturity.PRELIMINARY
    assert len(verdict.warnings) > 0


def test_abstain_unreplicated_regime():
    """N = 1 (or zero donor metadata) strictly triggers ABSTAIN."""
    verdict_n1 = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=1,
        is_raw_counts=True,
    )
    assert verdict_n1.regime == InferentialRegime.ABSTAIN_UNREPLICATED
    assert verdict_n1.permitted is False
    assert verdict_n1.maturity_ceiling == ConclusionMaturity.ABSTAIN

    verdict_no_meta = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=5,
        has_donor_metadata=False,
        is_raw_counts=True,
    )
    assert verdict_no_meta.regime == InferentialRegime.ABSTAIN_UNREPLICATED
    assert verdict_no_meta.permitted is False


def test_abstain_non_integer_counts():
    """Normalized / log float inputs to count models strictly trigger ABSTAIN."""
    verdict = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=4,
        is_raw_counts=False,
    )
    assert verdict.regime == InferentialRegime.ABSTAIN_INVALID_INPUT
    assert verdict.permitted is False
    assert verdict.maturity_ceiling == ConclusionMaturity.ABSTAIN


def test_abstain_confounded_design():
    """100% confounded batch/donor and condition strictly triggers ABSTAIN."""
    verdict = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=4,
        is_confounded=True,
        is_raw_counts=True,
    )
    assert verdict.regime == InferentialRegime.ABSTAIN_CONFOUNDED
    assert verdict.permitted is False
    assert verdict.maturity_ceiling == ConclusionMaturity.ABSTAIN


def test_causal_language_interception():
    """Observational single-cell DE reports making causal claims are intercepted."""
    claim1 = "Marker p-values prove that treatment caused downregulation of gene X."
    audit1 = audit_prohibited_claims(claim1)
    assert audit1.passed is False
    assert any(v.violation_type.value == "CAUSAL_TREATMENT_DE_OVERCLAIM" for v in audit1.violations)

    claim2 = "Our pseudobulk analysis establishes a causal mechanism for lupus."
    audit2 = audit_prohibited_claims(claim2)
    assert audit2.passed is False

    compliant = "Pseudobulk DE identified differential expression associated with interferon stimulation (padj < 0.01)."
    audit_ok = audit_prohibited_claims(compliant)
    assert audit_ok.passed is True


@pytest.mark.parametrize(("intervention", "identified", "balanced", "fit", "allowed", "maturity"), [
    (False, True, True, True, False, ConclusionMaturity.SUPPORTED),
    (True, False, True, True, False, ConclusionMaturity.SUPPORTED),
    (True, True, False, True, False, ConclusionMaturity.SUPPORTED),
    (True, True, True, False, True, ConclusionMaturity.SUPPORTED),
    (True, True, True, True, True, ConclusionMaturity.ROBUST),
])
def test_causal_identification_and_fit_are_independent(intervention, identified, balanced, fit, allowed, maturity):
    verdict = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group=32, is_interventional=intervention, intervention_identified=identified,
        design_balanced_or_paired=balanced, dispersion_verified=fit,
    )
    assert verdict.regime == InferentialRegime.POPULATION_INFERENCE
    assert verdict.causal_claims_allowed is allowed
    assert verdict.maturity_ceiling == maturity


def test_low_power_caps_even_an_intervention_with_three_donors():
    verdict = evaluate_pseudobulk_inferential_warrant(
        n_donors_per_group={"case": 4, "reference": 3}, is_interventional=True, intervention_identified=True,
        design_balanced_or_paired=True, dispersion_verified=True,
    )
    assert verdict.maturity_ceiling == ConclusionMaturity.PRELIMINARY
    assert verdict.regime == InferentialRegime.DESCRIPTIVE_ONLY
    assert not verdict.causal_claims_allowed and not verdict.population_claims_allowed
    assert verdict.metrics["power"]["powered_for_regime"] == "STRONG"


def test_strong_effect_requires_expression_and_fitted_shrinkage():
    options = {"n_donors_per_group": 5, "cells_per_sample": 50}
    strong = assess_statistical_power(**options, shrunk_log2fc=-5, base_mean=100)
    verdict = evaluate_pseudobulk_inferential_warrant(n_donors_per_group=5, power=strong)
    assert verdict.population_claims_allowed
    raw = assess_statistical_power(**options, observed_log2fc=-5)
    assert not evaluate_pseudobulk_inferential_warrant(n_donors_per_group=5, power=raw).population_claims_allowed
    assert not evaluate_pseudobulk_inferential_warrant(n_donors_per_group=3, power=strong).population_claims_allowed


def test_detectable_regime_does_not_excuse_effect_below_design_mde():
    power = assess_statistical_power(n_donors_per_group=20, shrunk_log2fc=0.05, base_mean=100)
    assert not evaluate_pseudobulk_inferential_warrant(n_donors_per_group=20, power=power).population_claims_allowed


@pytest.mark.parametrize("lfc, ceiling", [(3, ConclusionMaturity.SUPPORTED), (1, ConclusionMaturity.PRELIMINARY)])
def test_numeric_mde_determines_detectability_within_moderate_regime(lfc, ceiling):
    power = assess_statistical_power(n_donors_per_group=10, dispersion=0.5, shrunk_log2fc=lfc, base_mean=100)
    assert power.mde_log2fc == pytest.approx(1.29, abs=0.01)
    verdict = evaluate_pseudobulk_inferential_warrant(n_donors_per_group=10, power=power)
    assert verdict.maturity_ceiling == ceiling


def test_named_arm_sizes_are_bound_to_the_audited_contrast():
    arms = {"case": 5, "control": 9}
    power = assess_statistical_power(n_by_group=arms, shrunk_log2fc=3, base_mean=100)
    assert evaluate_pseudobulk_inferential_warrant(n_donors_per_group=arms, power=power).population_claims_allowed
    verdict = evaluate_pseudobulk_inferential_warrant(n_donors_per_group={"case": 5, "control": 5}, power=power)
    assert not verdict.population_claims_allowed
