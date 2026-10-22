"""
Unit tests for Context-Conditioned Epistemic Ladder vs Static N>=3 Dogma Comparison (BNS-019).
"""

from __future__ import annotations

from bionexus.rules.ladder_comparison import (
    evaluate_ladder_policy,
    evaluate_static_policy,
    run_ladder_vs_static_comparison,
)


def test_exploratory_n2_distinction():
    """Verify that N=2 strong-effect exploratory pilot is blocked by Static but allowed by Ladder."""
    case_n2 = {
        "case_id": "test_case_rare_n2",
        "n_donors": 2,
        "dominant_donor_fraction": 0.5,
        "observed_effect_regime": "STRONG",
        "observed_log2fc": 6.5,
        "claim_intent": "EXPLORATORY_COHORT",
        "expert_confirmed_flaw": False,
        "input_matrix_type": "raw_nonnegative_integer_counts",
        "fdr_controlled": True,
        "batch_confounded": False,
    }

    static_res = evaluate_static_policy(case_n2)
    assert static_res.flagged_as_flaw is True
    assert static_res.decision == "BLOCK"
    assert static_res.is_correct is False  # False Positive (False Alarm / False Rejection)

    ladder_res = evaluate_ladder_policy(case_n2)
    assert ladder_res.flagged_as_flaw is False
    assert ladder_res.decision == "EXPLORATORY_ALLOW"
    assert ladder_res.is_correct is True   # True Negative (Permitted with bounded scope)


def test_static_policy_misses_insidious_flaws_at_n_ge_3():
    """Verify that Static N>=3 blindly passes fatal batch confounding and donor dominance."""
    # Complete batch confounding at N=4
    case_batch = {
        "case_id": "test_case_confounded",
        "n_donors": 4,
        "batch_confounded": True,
        "dominant_donor_fraction": 0.25,
        "observed_effect_regime": "MODERATE",
        "claim_intent": "POPULATION_INFERENCE",
        "expert_confirmed_flaw": True,
        "input_matrix_type": "raw_nonnegative_integer_counts",
        "fdr_controlled": True,
    }
    s_batch = evaluate_static_policy(case_batch)
    assert s_batch.flagged_as_flaw is False
    assert s_batch.decision == "PASS"
    assert s_batch.is_correct is False  # False Negative (Missed Flaw)

    l_batch = evaluate_ladder_policy(case_batch)
    assert l_batch.flagged_as_flaw is True
    assert l_batch.decision == "BLOCK"
    assert l_batch.is_correct is True   # True Positive (Caught Flaw)

    # 94% donor dominance at N=3
    case_dom = {
        "case_id": "test_case_dominance",
        "n_donors": 3,
        "batch_confounded": False,
        "dominant_donor_fraction": 0.94,
        "observed_effect_regime": "MODERATE",
        "claim_intent": "POPULATION_INFERENCE",
        "expert_confirmed_flaw": True,
        "input_matrix_type": "raw_nonnegative_integer_counts",
        "fdr_controlled": True,
    }
    s_dom = evaluate_static_policy(case_dom)
    assert s_dom.flagged_as_flaw is False
    assert s_dom.is_correct is False  # False Negative (Missed Flaw)

    l_dom = evaluate_ladder_policy(case_dom)
    assert l_dom.flagged_as_flaw is True
    assert l_dom.decision == "BLOCK"
    assert l_dom.is_correct is True   # True Positive (Caught Flaw)


def test_full_ladder_vs_static_benchmark_comparison():
    """Verify that Epistemic Ladder strictly outperforms Static N>=3 on the frozen holdout."""
    comp = run_ladder_vs_static_comparison()

    assert comp.sample_size >= 12
    # Ladder achieves low FPR and low FNR
    assert comp.ladder_fpr <= 0.05
    assert comp.ladder_fnr <= 0.05
    assert comp.ladder_accuracy >= 0.95
    assert comp.ladder_f1 >= 0.95

    # Static policy has high FPR and high FNR
    assert comp.static_fpr >= 0.25
    assert comp.static_fnr >= 0.50

    # Relative reduction in errors
    assert comp.fpr_reduction_relative >= 0.50
    assert comp.fnr_reduction_relative >= 0.50

    # Decision Curve Net Benefit strictly dominates
    for pt_key in comp.net_benefit_static:
        nb_static = comp.net_benefit_static[pt_key]
        nb_ladder = comp.net_benefit_ladder[pt_key]
        assert nb_ladder > nb_static, f"Ladder net benefit ({nb_ladder}) did not exceed static ({nb_static}) at {pt_key}"
