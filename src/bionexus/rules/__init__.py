"""
BioNexus Scientific Rules Subpackage (BNS-019).

Exports paper-grade scientific rule research objects, dual-track truth models,
frozen holdout benchmark evaluators, and context-conditioned epistemic ladder comparisons.
"""

from __future__ import annotations

from bionexus.rules.definitions import (
    CANONICAL_SCIENTIFIC_RULES,
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
    HoldoutEvaluationResult,
    RuleHoldoutEvaluator,
    evaluate_single_case,
)
from bionexus.rules.ladder_comparison import (
    PolicyComparisonSummary,
    PolicyEvaluationRecord,
    compute_decision_curve_net_benefit,
    compute_policy_metrics,
    evaluate_ladder_policy,
    evaluate_static_policy,
    run_ladder_vs_static_comparison,
)
from bionexus.rules.research_object import (
    CitationRef,
    RuleDualTrackSemantics,
    RuleEmpiricalMetrics,
    ScientificRuleObject,
)

__all__ = [
    # Research Object Models
    "CitationRef",
    "RuleEmpiricalMetrics",
    "RuleDualTrackSemantics",
    "ScientificRuleObject",
    # Dual-Track Truth Models & Metrics
    "RuleEvaluationTruthPair",
    "compute_confusion_matrix",
    "compute_fpr_fnr",
    "compute_expected_calibration_error",
    "compute_cohens_kappa",
    "compute_empirical_metrics",
    # Canonical Definitions
    "CANONICAL_SCIENTIFIC_RULES",
    "get_canonical_rule_objects",
    "get_rule_object",
    # Holdout Evaluation
    "HoldoutEvaluationResult",
    "RuleHoldoutEvaluator",
    "evaluate_single_case",
    # Ladder Comparison
    "PolicyEvaluationRecord",
    "PolicyComparisonSummary",
    "evaluate_static_policy",
    "evaluate_ladder_policy",
    "compute_policy_metrics",
    "compute_decision_curve_net_benefit",
    "run_ladder_vs_static_comparison",
]
