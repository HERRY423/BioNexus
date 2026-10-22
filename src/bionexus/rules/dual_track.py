"""Descriptive comparisons against caller-supplied labels, with explicit missingness.

Two fields in a JSON object do not establish independent adjudication. Metrics
are not scientific authorization and identity strings do not authenticate people.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from bionexus.rules.research_object import RuleEmpiricalMetrics


@dataclass
class RuleEvaluationTruthPair:
    """Policy verdict and a supplied reference label, without identity verification."""

    case_id: str
    rule_id: str
    rule_flagged: bool
    rule_severity: str  # "BLOCKER", "HIGH_IMPACT", "ADVISORY", "NONE"
    rule_confidence: Optional[float]  # [0.0, 1.0]
    expert_confirmed_flaw: Optional[bool]  # True if domain experts or physical ground truth confirm scientific flaw
    expert_rationale: str
    adjudication_authority: str
    context: Dict[str, Any] = field(default_factory=dict)
    adjudication_status: str = "UNVERIFIED_CALLER_LABEL"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_confusion_matrix(pairs: List[RuleEvaluationTruthPair]) -> Dict[str, int]:
    """
    Compute binary confusion matrix:
    - TP: Rule flagged defect AND Expert confirmed flaw
    - FP: Rule flagged defect AND Expert determined scientifically sound / valid exploratory
    - TN: Rule did not flag AND Expert determined scientifically sound
    - FN: Rule did not flag AND Expert determined flawed (Missed flaw)
    """
    tp = sum(1 for p in pairs if p.rule_flagged and p.expert_confirmed_flaw is True)
    fp = sum(1 for p in pairs if p.rule_flagged and p.expert_confirmed_flaw is False)
    tn = sum(1 for p in pairs if not p.rule_flagged and p.expert_confirmed_flaw is False)
    fn = sum(1 for p in pairs if not p.rule_flagged and p.expert_confirmed_flaw is True)
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def compute_fpr_fnr(pairs: List[RuleEvaluationTruthPair]) -> Tuple[Optional[float], Optional[float]]:
    """
    Compute False Positive Rate (False Alarm) and False Negative Rate (Miss Rate):
    - FPR = FP / (FP + TN)
    - FNR = FN / (FN + TP)
    """
    cm = compute_confusion_matrix(pairs)
    fp, tn, fn, tp = cm["fp"], cm["tn"], cm["fn"], cm["tp"]

    fpr = float(fp / (fp + tn)) if (fp + tn) > 0 else None
    fnr = float(fn / (fn + tp)) if (fn + tp) > 0 else None
    return fpr, fnr


def compute_expected_calibration_error(
    pairs: List[RuleEvaluationTruthPair],
    n_bins: int = 5,
) -> Optional[float]:
    """
    Compute Expected Calibration Error (ECE) across confidence bins.

    Partition [0, 1] into n_bins intervals. In each bin, compare average
    rule confidence to empirical accuracy (how often rule prediction matches truth).
    """
    if not pairs or any(p.rule_confidence is None or p.expert_confirmed_flaw is None for p in pairs):
        return None
    if n_bins < 1 or any(not math.isfinite(p.rule_confidence) or not 0 <= p.rule_confidence <= 1 for p in pairs):
        raise ValueError("confidence must be a finite probability and bins positive")

    # Predictions: 1 if confidence >= 0.5 else 0
    # Correct if (p.rule_flagged == p.expert_confirmed_flaw)
    bin_boundaries = [i / float(n_bins) for i in range(n_bins + 1)]
    total_n = len(pairs)
    ece = 0.0

    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]

        bin_pairs = [
            p for p in pairs
            if (bin_lower <= p.rule_confidence < bin_upper)
            or (i == n_bins - 1 and p.rule_confidence == bin_upper)
        ]

        if not bin_pairs:
            continue

        bin_size = len(bin_pairs)
        avg_confidence = sum(p.rule_confidence for p in bin_pairs) / float(bin_size)
        # Accuracy: did the rule verdict match expert truth?
        correct_count = sum(1 for p in bin_pairs if p.rule_flagged == p.expert_confirmed_flaw)
        accuracy = correct_count / float(bin_size)

        ece += (bin_size / float(total_n)) * abs(accuracy - avg_confidence)

    return float(ece)


def compute_cohens_kappa(pairs: List[RuleEvaluationTruthPair]) -> Optional[float]:
    """
    Compute Cohen's Kappa coefficient between rule flag and expert adjudication.

    Kappa measures inter-rater agreement adjusted for chance agreement:
    kappa = (P_o - P_e) / (1 - P_e)
    """
    pairs = [p for p in pairs if p.expert_confirmed_flaw is not None]
    n = len(pairs)
    if n == 0:
        return None

    cm = compute_confusion_matrix(pairs)
    tp, fp, tn, fn = cm["tp"], cm["fp"], cm["tn"], cm["fn"]

    # Observed agreement
    p_o = (tp + tn) / float(n)

    # Expected agreement by chance
    # P_yes_rule = (tp + fp) / n, P_yes_expert = (tp + fn) / n
    # P_no_rule = (tn + fn) / n, P_no_expert = (tn + fp) / n
    p_yes_rule = (tp + fp) / float(n)
    p_yes_expert = (tp + fn) / float(n)
    p_no_rule = (tn + fn) / float(n)
    p_no_expert = (tn + fp) / float(n)

    p_e = (p_yes_rule * p_yes_expert) + (p_no_rule * p_no_expert)

    if math.isclose(p_e, 1.0, rel_tol=1e-9):
        return None  # Chance agreement denominator is zero for a single class.

    kappa = (p_o - p_e) / (1.0 - p_e)
    return float(kappa)


def compute_empirical_metrics(
    pairs: List[RuleEvaluationTruthPair],
    holdout_hash: str = "",
) -> RuleEmpiricalMetrics:
    """Aggregate a list of evaluation truth pairs into RuleEmpiricalMetrics."""
    n = len(pairs)
    if n == 0:
        return RuleEmpiricalMetrics(
            holdout_cohort_hash=holdout_hash,
            evaluation_date=datetime.now(timezone.utc).isoformat(),
        )

    cm = compute_confusion_matrix(pairs)
    fpr, fnr = compute_fpr_fnr(pairs)
    ece = compute_expected_calibration_error(pairs)
    kappa = compute_cohens_kappa(pairs)
    n_labeled = sum(cm.values())
    concordance = (cm["tp"] + cm["tn"]) / n_labeled if n_labeled else None

    return RuleEmpiricalMetrics(
        sample_size=n,
        n_labeled_cases=n_labeled,
        true_positives=cm["tp"],
        false_positives=cm["fp"],
        true_negatives=cm["tn"],
        false_negatives=cm["fn"],
        false_positive_rate=fpr,
        false_negative_rate=fnr,
        expected_calibration_error=ece,
        expert_concordance=concordance,
        cohens_kappa=kappa,
        holdout_cohort_hash=holdout_hash,
        evaluation_date=datetime.now(timezone.utc).isoformat(),
    )
