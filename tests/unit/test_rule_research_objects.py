"""
Unit tests for BioNexus Scientific Rule Research Objects and Dual-Track Evaluation (BNS-019).
"""

from __future__ import annotations

import json
from pathlib import Path

from bionexus.rules.definitions import (
    get_canonical_rule_objects,
    get_rule_object,
)
from bionexus.rules.dual_track import (
    RuleEvaluationTruthPair,
    compute_cohens_kappa,
    compute_confusion_matrix,
    compute_empirical_metrics,
    compute_expected_calibration_error,
    compute_fpr_fnr,
)
from bionexus.rules.holdout_evaluator import (
    RuleHoldoutEvaluator,
)
from bionexus.rules.research_object import (
    ScientificRuleObject,
)


def test_canonical_scientific_rules_completeness():
    """Verify all 8 core rules are defined with mandatory research object fields."""
    rules = get_canonical_rule_objects()
    expected_ids = {
        "BFA-001",
        "BFA-001b",
        "BFA-002",
        "BFA-003",
        "BFA-004",
        "BFA-007",
        "BFA-008",
        "BFA-014",
    }
    assert expected_ids.issubset(rules.keys())

    for rid in expected_ids:
        rule = rules[rid]
        assert isinstance(rule, ScientificRuleObject)
        assert rule.rule_id == rid
        assert len(rule.name) > 5
        assert len(rule.version) >= 5  # e.g. "2.0.0"
        assert len(rule.applicability_conditions) >= 1
        assert rule.expected_benefit != ""
        assert rule.false_rejection_risk != ""
        assert rule.change_rationale != ""

        # Check citations
        assert len(rule.literature_citations) >= 1
        for cit in rule.literature_citations:
            assert cit.author != ""
            assert cit.year > 1900
            assert cit.title != ""
            assert cit.journal != ""
            assert cit.verification_status == "UNVERIFIED_BIBLIOGRAPHIC_REFERENCE"
            assert "zenodo.bionexus.trust" not in cit.doi

        # Check dual-track semantics
        dts = rule.dual_track_semantics
        assert dts.rule_flag_meaning != ""
        assert dts.expert_flaw_meaning != ""

        # Check serialization & markdown card
        d = rule.to_dict()
        assert d["rule_id"] == rid
        card = rule.to_markdown_card()
        assert f"# Scientific Rule Object Card: `{rid}`" in card
        assert "## 1. Scientific Proposition & Normative Purpose" in card
        assert "## 3. Dual-Track Epistemic Semantics" in card


def test_get_rule_object_lookup():
    """Verify lookup by canonical ID and alias."""
    r1 = get_rule_object("BFA-001")
    assert r1 is not None
    assert r1.rule_id == "BFA-001"

    # Alias lookup
    r2 = get_rule_object("pseudoreplication")
    assert r2 is not None
    assert r2.rule_id == "BFA-001"

    # Non-existent
    assert get_rule_object("NON_EXISTENT_RULE_XYZ") is None


def test_dual_track_metrics_computation():
    """Verify confusion matrix, FPR, FNR, ECE, and Cohen's Kappa formulas."""
    pairs = [
        RuleEvaluationTruthPair(
            case_id="c1", rule_id="BFA-001", rule_flagged=True, rule_severity="BLOCKER",
            rule_confidence=0.95, expert_confirmed_flaw=True, expert_rationale="Flaw", adjudication_authority="Board"
        ),
        RuleEvaluationTruthPair(
            case_id="c2", rule_id="BFA-001", rule_flagged=True, rule_severity="BLOCKER",
            rule_confidence=0.90, expert_confirmed_flaw=True, expert_rationale="Flaw", adjudication_authority="Board"
        ),
        RuleEvaluationTruthPair(
            case_id="c3", rule_id="BFA-001", rule_flagged=False, rule_severity="NONE",
            rule_confidence=0.95, expert_confirmed_flaw=False, expert_rationale="Sound", adjudication_authority="Board"
        ),
        RuleEvaluationTruthPair(
            case_id="c4", rule_id="BFA-001", rule_flagged=False, rule_severity="NONE",
            rule_confidence=0.92, expert_confirmed_flaw=False, expert_rationale="Sound", adjudication_authority="Board"
        ),
    ]

    cm = compute_confusion_matrix(pairs)
    assert cm == {"tp": 2, "fp": 0, "tn": 2, "fn": 0}

    fpr, fnr = compute_fpr_fnr(pairs)
    assert fpr == 0.0
    assert fnr == 0.0

    kappa = compute_cohens_kappa(pairs)
    assert kappa == 1.0

    ece = compute_expected_calibration_error(pairs)
    assert ece >= 0.0

    metrics = compute_empirical_metrics(pairs, holdout_hash="test_sha256")
    assert metrics.sample_size == 4
    assert metrics.false_positive_rate == 0.0
    assert metrics.false_negative_rate == 0.0
    assert metrics.expert_concordance == 1.0
    assert metrics.cohens_kappa == 1.0
    assert metrics.holdout_cohort_hash == "test_sha256"


def test_holdout_evaluator_execution(tmp_path: Path):
    """Verify RuleHoldoutEvaluator on the frozen benchmark."""
    evaluator = RuleHoldoutEvaluator()
    data, sha256 = evaluator.load_benchmark()

    assert len(sha256) == 64
    assert data["benchmark_version"] == "1.0.0"
    assert len(data["cases"]) >= 12

    result = evaluator.run_evaluation()
    assert result.total_cases == len(data["cases"])
    assert result.holdout_sha256 == sha256
    assert result.overall_metrics.false_positive_rate <= 0.05
    assert result.overall_metrics.false_negative_rate <= 0.05
    assert result.overall_metrics.expert_concordance >= 0.95
    assert result.overall_metrics.cohens_kappa >= 0.80

    # Write calibration card
    json_path, md_path = evaluator.write_calibration_card(result, out_dir=tmp_path)
    assert json_path.is_file()
    assert md_path.is_file()

    with open(json_path, "r", encoding="utf-8") as f:
        card_data = json.load(f)
    assert card_data["benchmark_version"] == "1.0.0"
    assert "overall_metrics" in card_data
    assert "per_rule_metrics" in card_data

    md_content = md_path.read_text(encoding="utf-8")
    assert "# BioNexus Developer Rule Rehearsal Card" in md_content
    assert "NOT_ESTIMABLE" in md_content
    assert card_data["production_audit_executed"] is False
    assert result.overall_metrics.expected_calibration_error is None
    assert all(r.empirical_metrics is None for r in get_canonical_rule_objects().values())
