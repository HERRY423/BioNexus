"""Developer-case rule rehearsal, not independent holdout or product validation.

The reference labels and authority strings in the input are unverified. This
module is a local simplified policy evaluator, not the production DE audit path.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bionexus.rules.dual_track import (
    RuleEvaluationTruthPair,
    compute_empirical_metrics,
)
from bionexus.rules.research_object import RuleEmpiricalMetrics


@dataclass
class HoldoutEvaluationResult:
    """Comprehensive evaluation results on a frozen holdout benchmark."""

    benchmark_version: str
    holdout_sha256: str
    total_cases: int
    rule_pairs: List[RuleEvaluationTruthPair]
    overall_metrics: RuleEmpiricalMetrics
    per_rule_metrics: Dict[str, RuleEmpiricalMetrics] = field(default_factory=dict)
    calibration_timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "benchmark_version": self.benchmark_version,
            "evidence_kind": "DEVELOPER_CASE_FIXTURE",
            "scientific_authorization": "NONE",
            "independent_validation_status": "NOT_ESTABLISHED",
            "production_audit_executed": False,
            "calibration_status": "NOT_ESTIMABLE",
            "holdout_sha256": self.holdout_sha256,
            "total_cases": self.total_cases,
            "overall_metrics": self.overall_metrics.to_dict(),
            "per_rule_metrics": {
                k: v.to_dict() for k, v in self.per_rule_metrics.items()
            },
            "calibration_timestamp": self.calibration_timestamp,
            "cases_evaluated": [p.to_dict() for p in self.rule_pairs],
        }


def evaluate_single_case(case: Dict[str, Any]) -> RuleEvaluationTruthPair:
    """
    Evaluate a holdout case against BioNexus scientific rules.

    Produces a RuleEvaluationTruthPair linking algorithmic verdict with expert truth.
    """
    case_id = case["case_id"]
    target_rule_id = case.get("target_rule_id", "BFA-001")
    n_donors = case.get("n_donors", 1)
    aggregation = case.get("aggregation", "cell")
    design_type = case.get("design_type", "")
    stat_model = case.get("statistical_model", "")
    fdr_controlled = case.get("fdr_controlled", True)
    batch_confounded = case.get("batch_confounded", False)
    dominant_donor_fraction = case.get("dominant_donor_fraction", 0.0)
    input_matrix_type = case.get("input_matrix_type", "raw_nonnegative_integer_counts")
    claim_text = case.get("claim_text", "")
    claim_intent = case.get("claim_intent", "POPULATION_INFERENCE")

    expert_flaw = case.get("expert_confirmed_flaw")
    if expert_flaw is not None and not isinstance(expert_flaw, bool):
        raise ValueError("reference flaw label must be boolean or missing")
    expert_rationale = case.get("expert_rationale", "")
    authority = case.get("adjudication_authority", "UNVERIFIED_CALLER_LABEL")

    rule_flagged = False
    severity = "NONE"
    confidence = None

    # Specific rule evaluations
    if target_rule_id == "BFA-001":
        # Cell-level pseudoreplication
        if (design_type == "cell_level_pooled" or aggregation == "cell") and claim_intent == "POPULATION_INFERENCE":
            rule_flagged = True
            severity = "BLOCKER"
            confidence = None
        else:
            rule_flagged = False
            confidence = None

    elif target_rule_id == "BFA-001b":
        # Low N / N=2 boundary with Epistemic Ladder
        if n_donors == 2:
            # Under Context Ladder:
            # If claim_intent is EXPLORATORY_COHORT with strong effect, do NOT flag as a fatal flaw!
            # It receives HIGH_IMPACT advisory with EXPLORATORY_COHORT bounds.
            if claim_intent == "EXPLORATORY_COHORT" and case.get("observed_effect_regime") == "STRONG":
                rule_flagged = False  # Permitted as valid exploratory under ladder
                severity = "ADVISORY"
                confidence = None
            else:
                rule_flagged = True
                severity = "HIGH_IMPACT"
                confidence = None
        elif n_donors == 3 and case.get("observed_effect_regime") == "SUBTLE" and claim_intent == "POPULATION_INFERENCE":
            # Power mismatch on subtle effect
            rule_flagged = True
            severity = "HIGH_IMPACT"
            confidence = None
        else:
            rule_flagged = False
            confidence = None

    elif target_rule_id == "BFA-002":
        # Count matrix integrity
        if "log1p" in input_matrix_type or "continuous" in input_matrix_type:
            rule_flagged = True
            severity = "BLOCKER"
            confidence = None
        else:
            rule_flagged = False
            confidence = None

    elif target_rule_id == "BFA-003":
        # FDR & multiple testing
        if claim_intent == "NEGATIVE_RESULT_FREEZE":
            # Honest negative result is not flagged
            rule_flagged = False
            confidence = None
        elif not fdr_controlled:
            rule_flagged = True
            severity = "HIGH_IMPACT"
            confidence = None
        else:
            rule_flagged = False
            confidence = None

    elif target_rule_id == "BFA-004":
        # Batch confounding
        if batch_confounded:
            rule_flagged = True
            severity = "BLOCKER"
            confidence = None
        else:
            rule_flagged = False
            confidence = None

    elif target_rule_id == "BFA-007":
        # Single-donor dominance
        if dominant_donor_fraction >= 0.70:
            rule_flagged = True
            severity = "HIGH_IMPACT"
            confidence = None
        else:
            rule_flagged = False
            confidence = None

    elif target_rule_id == "BFA-008":
        # Causal overclaim
        if claim_intent == "CAUSAL_MECHANISM":
            rule_flagged = True
            severity = "HIGH_IMPACT"
            confidence = None
        else:
            rule_flagged = False
            confidence = None

    elif target_rule_id == "BFA-014":
        # Execution binding hallucination
        if "PyDESeq2" in claim_text and "wilcoxon" in stat_model:
            rule_flagged = True
            severity = "BLOCKER"
            confidence = None
        else:
            rule_flagged = False
            confidence = None

    else:
        raise ValueError(f"Unsupported rule: {target_rule_id}")

    return RuleEvaluationTruthPair(
        case_id=case_id,
        rule_id=target_rule_id,
        rule_flagged=rule_flagged,
        rule_severity=severity,
        rule_confidence=confidence,
        expert_confirmed_flaw=expert_flaw,
        expert_rationale=expert_rationale,
        adjudication_authority=authority,
        context={
            "n_donors": n_donors,
            "aggregation": aggregation,
            "design_type": design_type,
            "claim_intent": claim_intent,
        },
    )


class RuleHoldoutEvaluator:
    """Evaluates rules against a frozen benchmark and produces publication calibration cards."""

    def __init__(self, benchmark_path: Optional[Path | str] = None) -> None:
        if benchmark_path is None:
            benchmark_path = Path(__file__).resolve().parent.parent.parent.parent / "validation" / "rules" / "frozen_holdout_benchmark.json"
        self.benchmark_path = Path(benchmark_path)

    def load_benchmark(self) -> Tuple[Dict[str, Any], str]:
        """Load benchmark JSON and compute its cryptographic SHA-256 fingerprint."""
        if not self.benchmark_path.is_file():
            raise FileNotFoundError(f"Frozen benchmark not found at {self.benchmark_path}")
        raw_bytes = self.benchmark_path.read_bytes()
        sha256 = hashlib.sha256(raw_bytes).hexdigest()
        data = json.loads(raw_bytes.decode("utf-8"))
        return data, sha256

    def run_evaluation(self) -> HoldoutEvaluationResult:
        """Run evaluation over all cases in the frozen benchmark."""
        data, holdout_hash = self.load_benchmark()
        cases = data.get("cases", [])
        if not isinstance(cases, list) or any(not isinstance(c, dict) or not c.get("case_id") for c in cases):
            raise ValueError("cases must be objects with case identifiers")
        if len({c["case_id"] for c in cases}) != len(cases):
            raise ValueError("duplicate case identifiers")
        version = data.get("benchmark_version", "1.0.0")

        truth_pairs: List[RuleEvaluationTruthPair] = []
        for c in cases:
            pair = evaluate_single_case(c)
            truth_pairs.append(pair)

        # Compute overall metrics
        overall = compute_empirical_metrics(truth_pairs, holdout_hash=holdout_hash)

        # Compute per-rule metrics
        per_rule: Dict[str, RuleEmpiricalMetrics] = {}
        rule_ids = sorted({p.rule_id for p in truth_pairs})
        for rid in rule_ids:
            rule_subset = [p for p in truth_pairs if p.rule_id == rid]
            per_rule[rid] = compute_empirical_metrics(rule_subset, holdout_hash=holdout_hash)

        # Rehearsal metrics must not populate canonical scientific calibration.
        timestamp = datetime.now(timezone.utc).isoformat()
        return HoldoutEvaluationResult(
            benchmark_version=version,
            holdout_sha256=holdout_hash,
            total_cases=len(cases),
            rule_pairs=truth_pairs,
            overall_metrics=overall,
            per_rule_metrics=per_rule,
            calibration_timestamp=timestamp,
        )

    def write_calibration_card(
        self, result: HoldoutEvaluationResult, out_dir: Optional[Path | str] = None,
    ) -> Tuple[Path, Path]:
        """Write new descriptive rehearsal cards, never replace prior evidence."""
        out = Path(out_dir) if out_dir is not None else self.benchmark_path.parent
        out.mkdir(parents=True, exist_ok=True)
        json_path, md_path = out / "CALIBRATION_CARD.json", out / "CALIBRATION_CARD.md"
        if json_path.exists() or md_path.exists():
            raise FileExistsError("Existing cards must be preserved; choose a new output directory")
        with json_path.open("x", encoding="utf-8") as handle:
            json.dump(result.to_dict(), handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        lines = ["# BioNexus Developer Rule Rehearsal Card", "",
                 "Evidence: DEVELOPER_CASE_FIXTURE. Independent validation and scientific authorization: NONE.",
                 "Reference authority strings are unverified. Production audit was not executed.",
                 "Probabilistic calibration: NOT_ESTIMABLE; no measured probabilities were supplied.", "",
                 f"Cases: {result.total_cases}; input SHA-256: {result.holdout_sha256}", "",
                 "## Descriptive reference-label metrics", "", "```json",
                 json.dumps(result.overall_metrics.to_dict(), indent=2), "```", "",
                 "Missing denominators are null/NOT_ESTIMABLE; no performance threshold is certified.", ""]
        with md_path.open("x", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
        return json_path, md_path
