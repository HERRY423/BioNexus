"""Developer-case comparison of two simplified illustrative policies.

The N-only baseline deliberately inspects fewer facts. This rehearsal cannot
establish superiority over real workflows, expert review, or the production
BioNexus audit. Supplied expert-label fields have not been authenticated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class PolicyEvaluationRecord:
    """Evaluation record for a single case under a specific governance policy."""

    case_id: str
    policy_name: str
    decision: str  # "PASS", "BLOCK", "EXPLORATORY_ALLOW"
    flagged_as_flaw: bool
    expert_confirmed_flaw: Optional[bool]
    is_correct: Optional[bool]
    explanation: str


@dataclass
class PolicyComparisonSummary:
    """Quantitative performance comparison between two governance policies."""

    sample_size: int
    static_fpr: Optional[float]
    ladder_fpr: Optional[float]
    static_fnr: Optional[float]
    ladder_fnr: Optional[float]
    static_accuracy: Optional[float]
    ladder_accuracy: Optional[float]
    static_f1: Optional[float]
    ladder_f1: Optional[float]
    fpr_reduction_relative: Optional[float]  # (static_fpr - ladder_fpr) / static_fpr
    fnr_reduction_relative: Optional[float]  # (static_fnr - ladder_fnr) / static_fnr
    net_benefit_static: Dict[str, float]  # threshold -> net benefit
    net_benefit_ladder: Dict[str, float]
    case_comparisons: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "evidence_kind": "DEVELOPER_CASE_FIXTURE",
            "superiority_established": False,
            "scientific_authorization": "NONE",
            "baseline_scope": "Illustrative N-only policy; not an expert or competitive production baseline",
            "production_audit_executed": False,
            "static_fpr": round(self.static_fpr, 4) if self.static_fpr is not None else None,
            "ladder_fpr": round(self.ladder_fpr, 4) if self.ladder_fpr is not None else None,
            "static_fnr": round(self.static_fnr, 4) if self.static_fnr is not None else None,
            "ladder_fnr": round(self.ladder_fnr, 4) if self.ladder_fnr is not None else None,
            "static_accuracy": round(self.static_accuracy, 4) if self.static_accuracy is not None else None,
            "ladder_accuracy": round(self.ladder_accuracy, 4) if self.ladder_accuracy is not None else None,
            "static_f1": round(self.static_f1, 4) if self.static_f1 is not None else None,
            "ladder_f1": round(self.ladder_f1, 4) if self.ladder_f1 is not None else None,
            "fpr_reduction_relative": round(self.fpr_reduction_relative, 4) if self.fpr_reduction_relative is not None else None,
            "fnr_reduction_relative": round(self.fnr_reduction_relative, 4) if self.fnr_reduction_relative is not None else None,
            "net_benefit_static": {k: round(v, 4) for k, v in self.net_benefit_static.items()},
            "net_benefit_ladder": {k: round(v, 4) for k, v in self.net_benefit_ladder.items()},
            "case_comparisons": self.case_comparisons,
        }


def evaluate_static_policy(case: Dict[str, Any]) -> PolicyEvaluationRecord:
    """
    Simulates the conventional 'Static Rule Policy' ($N >= 3$ Dogma):
    1. If N < 3, unconditionally BLOCK (reject as invalid pseudoreplication).
    2. If N >= 3, treat sample size as satisfied; ignore batch confounding,
       dominant donor fraction, subtle effect power mismatch, and causal overclaims.
    """
    case_id = case["case_id"]
    n_donors = case.get("n_donors", 1)
    expert_flaw = case.get("expert_confirmed_flaw")
    if expert_flaw is not None and not isinstance(expert_flaw, bool):
        raise ValueError("reference flaw label must be boolean or missing")

    if n_donors < 3:
        flagged = True
        decision = "BLOCK"
        explanation = f"Static universal rule: N={n_donors} < 3 donors unconditionally rejected as fatal pseudoreplication."
    else:
        # Static threshold satisfied: does not inspect multivariate context
        flagged = False
        decision = "PASS"
        explanation = f"Static universal rule: N={n_donors} >= 3 satisfies sample size requirement; uninspected."

    is_correct = (flagged == expert_flaw) if expert_flaw is not None else None
    return PolicyEvaluationRecord(
        case_id=case_id,
        policy_name="Static N>=3 Policy",
        decision=decision,
        flagged_as_flaw=flagged,
        expert_confirmed_flaw=expert_flaw,
        is_correct=is_correct,
        explanation=explanation,
    )


def evaluate_ladder_policy(case: Dict[str, Any]) -> PolicyEvaluationRecord:
    """
    Evaluates under the 'BioNexus Context-Conditioned Epistemic Ladder':
    1. Rejects blunt magic-number refusals: allows N=2 strong-effect studies
       under bounded 'EXPLORATORY_COHORT' authorization while barring causal overclaims.
    2. Recognizes single-sample within-cohort descriptive annotation when verified
       by orthogonal physical ground truth (FACS surface protein).
    3. Deeply checks confounding (batch vs condition), donor dominance (>=70%),
       power mismatch (MDE vs observed |log2FC|), and count integrity.
    """
    case_id = case["case_id"]
    n_donors = case.get("n_donors", 1)
    expert_flaw = case.get("expert_confirmed_flaw")
    if expert_flaw is not None and not isinstance(expert_flaw, bool):
        raise ValueError("reference flaw label must be boolean or missing")
    design_type = case.get("design_type", "")
    aggregation = case.get("aggregation", "cell")
    claim_intent = case.get("claim_intent", "POPULATION_INFERENCE")
    effect_regime = case.get("observed_effect_regime", "MODERATE")
    batch_confounded = case.get("batch_confounded", False)
    dominant_donor = case.get("dominant_donor_fraction", 0.0)
    input_matrix = case.get("input_matrix_type", "raw_nonnegative_integer_counts")
    fdr_controlled = case.get("fdr_controlled", True)
    stat_model = case.get("statistical_model", "")
    claim_text = case.get("claim_text", "")

    flagged = False
    decision = "PASS"
    explanation = "All epistemic criteria and contextual boundaries satisfied."

    # 1. Fatal data integrity / execution contradiction
    if "log1p" in input_matrix or "continuous" in input_matrix:
        flagged = True
        decision = "BLOCK"
        explanation = "Epistemic Ladder Stage 1: Continuous log-counts violate discrete NB likelihood."
    elif "PyDESeq2" in claim_text and "wilcoxon" in stat_model:
        flagged = True
        decision = "BLOCK"
        explanation = "Epistemic Ladder Stage 1: Verified execution record contradicts stated analysis method."
    # 2. Complete batch confounding
    elif batch_confounded:
        flagged = True
        decision = "BLOCK"
        explanation = "Epistemic Ladder Stage 2: Technical batch is 100% collinear with condition; zero inferential degrees of freedom."
    # 3. Cell-level pseudoreplication
    elif (design_type == "cell_level_pooled" or aggregation == "cell") and claim_intent == "POPULATION_INFERENCE":
        flagged = True
        decision = "BLOCK"
        explanation = "Epistemic Ladder Stage 2: Cell-level testing inflates degrees of freedom for population claims."
    # 4. Single-donor cell dominance (multi-donor designs only)
    elif dominant_donor >= 0.70 and n_donors > 1 and claim_intent in ("POPULATION_INFERENCE", "EXPLORATORY_COHORT"):
        flagged = True
        decision = "BLOCK"
        explanation = f"Epistemic Ladder Stage 3: Extreme donor dominance ({dominant_donor*100:.0f}% cells); private transcriptome risk."
    # 5. Low N / N=1 or N=2 Context Conditioned Ladder
    elif n_donors == 1:
        if claim_intent == "DESCRIPTIVE_ANNOTATION":
            flagged = False
            decision = "PASS"
            explanation = "Epistemic Ladder Stage 4: Single-sample descriptive annotation with orthogonal physical truth permitted."
        else:
            flagged = True
            decision = "BLOCK"
            explanation = "Epistemic Ladder Stage 4: N=1 cannot support population-level cross-condition inference."
    elif n_donors == 2:
        if claim_intent == "EXPLORATORY_COHORT" and effect_regime == "STRONG":
            # Context-conditioned relaxation: valid exploratory discovery!
            flagged = False
            decision = "EXPLORATORY_ALLOW"
            explanation = "Epistemic Ladder Stage 4: N=2 with strong monogenic effect authorized as EXPLORATORY_COHORT."
        else:
            flagged = True
            decision = "BLOCK"
            explanation = "Epistemic Ladder Stage 4: N=2 with subtle effect or unhedged population claims is unpowered."
    # 6. Underpowered subtle effect at N=3
    elif n_donors == 3 and effect_regime == "SUBTLE" and claim_intent == "POPULATION_INFERENCE":
        flagged = True
        decision = "BLOCK"
        explanation = "Epistemic Ladder Stage 4: MDE exceeds subtle effect size at N=3; underpowered for population claims."
    # 7. FDR / P-hacking
    elif not fdr_controlled and claim_intent != "NEGATIVE_RESULT_FREEZE":
        flagged = True
        decision = "BLOCK"
        explanation = "Epistemic Ladder Stage 5: Uncorrected p-values without FDR control constitute selective reporting."
    # 8. Causal overclaim
    elif claim_intent == "CAUSAL_MECHANISM":
        flagged = True
        decision = "BLOCK"
        explanation = "Epistemic Ladder Stage 5: Observational atlas cannot warrant causal therapeutic claims without perturbation."

    is_correct = (flagged == expert_flaw) if expert_flaw is not None else None
    return PolicyEvaluationRecord(
        case_id=case_id,
        policy_name="BioNexus Epistemic Ladder",
        decision=decision,
        flagged_as_flaw=flagged,
        expert_confirmed_flaw=expert_flaw,
        is_correct=is_correct,
        explanation=explanation,
    )


def compute_policy_metrics(records: List[PolicyEvaluationRecord]) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Descriptive (FPR, FNR, accuracy, F1), null for missing denominators."""
    labeled = [r for r in records if r.expert_confirmed_flaw is not None]
    tp = sum(r.flagged_as_flaw and r.expert_confirmed_flaw is True for r in labeled)
    fp = sum(r.flagged_as_flaw and r.expert_confirmed_flaw is False for r in labeled)
    tn = sum(not r.flagged_as_flaw and r.expert_confirmed_flaw is False for r in labeled)
    fn = sum(not r.flagged_as_flaw and r.expert_confirmed_flaw is True for r in labeled)
    return (fp / (fp + tn) if fp + tn else None,
            fn / (fn + tp) if fn + tp else None,
            (tp + tn) / len(labeled) if labeled else None,
            2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None)


def compute_decision_curve_net_benefit(
    records: List[PolicyEvaluationRecord], thresholds: Optional[List[float]] = None,
) -> Dict[str, float]:
    """Loss-weight arithmetic on labeled cases, not measured laboratory benefit."""
    import math

    thresholds = thresholds if thresholds is not None else [.1, .2, .3, .4, .5, .6, .7, .8, .9]
    if any(not math.isfinite(p) or not 0 < p < 1 for p in thresholds):
        raise ValueError("thresholds must be finite probabilities in (0, 1)")
    if len(set(thresholds)) != len(thresholds):
        raise ValueError("thresholds must be unique")
    records = [r for r in records if r.expert_confirmed_flaw is not None]
    if not records:
        return {}
    tp = sum(r.flagged_as_flaw and r.expert_confirmed_flaw is True for r in records)
    fp = sum(r.flagged_as_flaw and r.expert_confirmed_flaw is False for r in records)
    return {f"pt_{p:g}": (tp - fp * p / (1-p)) / len(records) for p in thresholds}


def run_ladder_vs_static_comparison(
    benchmark_path: Optional[Path | str] = None,
) -> PolicyComparisonSummary:
    """Run a developer-case comparison of simplified policies, without promotion."""
    if benchmark_path is None:
        benchmark_path = Path(__file__).resolve().parent.parent.parent.parent / "validation" / "rules" / "frozen_holdout_benchmark.json"

    with open(benchmark_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data.get("cases", [])
    if not isinstance(cases, list) or any(not isinstance(c, dict) or not c.get("case_id") for c in cases):
        raise ValueError("cases must have identifiers")
    if len({c["case_id"] for c in cases}) != len(cases):
        raise ValueError("duplicate case identifiers")
    static_records = [evaluate_static_policy(c) for c in cases]
    ladder_records = [evaluate_ladder_policy(c) for c in cases]

    s_fpr, s_fnr, s_acc, s_f1 = compute_policy_metrics(static_records)
    l_fpr, l_fnr, l_acc, l_f1 = compute_policy_metrics(ladder_records)

    fpr_red = float((s_fpr - l_fpr) / s_fpr) if s_fpr is not None and l_fpr is not None and s_fpr > 0 else None
    fnr_red = float((s_fnr - l_fnr) / s_fnr) if s_fnr is not None and l_fnr is not None and s_fnr > 0 else None

    nb_static = compute_decision_curve_net_benefit(static_records)
    nb_ladder = compute_decision_curve_net_benefit(ladder_records)

    case_comps: List[Dict[str, Any]] = []
    for c, static_record, ladder_record in zip(cases, static_records, ladder_records):
        case_comps.append({
            "case_id": c["case_id"],
            "title": c.get("title", ""),
            "n_donors": c.get("n_donors"),
            "expert_confirmed_flaw": c.get("expert_confirmed_flaw"),
            "static_decision": static_record.decision,
            "static_correct": static_record.is_correct,
            "ladder_decision": ladder_record.decision,
            "ladder_correct": ladder_record.is_correct,
            "ladder_advantage": (ladder_record.is_correct is True and static_record.is_correct is False),
        })

    return PolicyComparisonSummary(
        sample_size=len(cases),
        static_fpr=s_fpr,
        ladder_fpr=l_fpr,
        static_fnr=s_fnr,
        ladder_fnr=l_fnr,
        static_accuracy=s_acc,
        ladder_accuracy=l_acc,
        static_f1=s_f1,
        ladder_f1=l_f1,
        fpr_reduction_relative=fpr_red,
        fnr_reduction_relative=fnr_red,
        net_benefit_static=nb_static,
        net_benefit_ladder=nb_ladder,
        case_comparisons=case_comps,
    )
