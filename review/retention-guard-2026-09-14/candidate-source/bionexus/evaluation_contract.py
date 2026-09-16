"""Strategy-neutral evaluation contracts for BioNexus reliability components.

Policies receive visible scientific context only.  Scorer-only truth is kept in
a distinct type and is never passed to a policy.  The harness evaluates bounded
outputs; it is not a tool selector, planner, agent, or benchmark platform.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class VisibleScenario:
    scenario_id: str
    claim: str
    observed_evidence: tuple[str, ...]
    unresolved_gaps: tuple[str, ...]
    available_actions: tuple[str, ...]
    competing_explanations: tuple[str, ...] = ()
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScorerGroundTruth:
    """Evaluator-only labels.  This object must never be supplied to a policy."""

    scenario_id: str
    target_gap_id: str
    acceptable_action_ids: frozenset[str]
    decision_changing_action_ids: frozenset[str]
    required_competing_explanations: frozenset[str] = frozenset()


@dataclass(frozen=True)
class PolicyOutput:
    target_gap_id: str | None
    action_id: str | None
    considered_explanations: tuple[str, ...] = ()
    claim_impact: str = ""
    abstained: bool = False
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaseScore:
    scenario_id: str
    target_gap_correct: bool
    action_acceptable: bool
    decision_changing_evidence_priority: bool
    competing_explanation_coverage: float
    unnecessary_action: bool
    review_artifact_completeness_proxy: float
    payload_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Policy = Callable[[VisibleScenario], PolicyOutput]


def _canonical_output(output: PolicyOutput) -> bytes:
    return json.dumps(output.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def evaluate_output(
    visible: VisibleScenario,
    truth: ScorerGroundTruth,
    output: PolicyOutput,
) -> CaseScore:
    """Score output content only; policy identity/name cannot affect results."""

    if visible.scenario_id != truth.scenario_id:
        raise ValueError("Visible scenario and scorer truth IDs do not match")
    visible_actions = set(visible.available_actions)
    if output.action_id is not None and output.action_id not in visible_actions:
        action_acceptable = False
    else:
        action_acceptable = output.action_id in truth.acceptable_action_ids
    required = truth.required_competing_explanations
    considered = set(output.considered_explanations)
    explanation_coverage = 1.0 if not required else len(required & considered) / len(required)
    required_review_fields = (
        bool(output.target_gap_id),
        bool(output.action_id) or output.abstained,
        bool(output.claim_impact.strip()),
        bool(output.rationale.strip()),
    )
    return CaseScore(
        scenario_id=visible.scenario_id,
        target_gap_correct=output.target_gap_id == truth.target_gap_id,
        action_acceptable=action_acceptable,
        decision_changing_evidence_priority=output.action_id in truth.decision_changing_action_ids,
        competing_explanation_coverage=explanation_coverage,
        unnecessary_action=(output.action_id is not None and output.action_id not in truth.decision_changing_action_ids),
        review_artifact_completeness_proxy=sum(required_review_fields) / len(required_review_fields),
        payload_bytes=len(_canonical_output(output)),
    )


def run_policy(policy: Policy, visible: VisibleScenario) -> PolicyOutput:
    output = policy(visible)
    if not isinstance(output, PolicyOutput):
        raise TypeError("Policies must return PolicyOutput")
    return output


def deterministic_replay(policy: Policy, visible: VisibleScenario, *, repeats: int = 3) -> bool:
    if repeats < 2:
        raise ValueError("Determinism requires at least two executions")
    outputs = [_canonical_output(run_policy(policy, visible)) for _ in range(repeats)]
    return all(value == outputs[0] for value in outputs[1:])


def hidden_truth_invariance(
    policy: Policy,
    visible: VisibleScenario,
    alternate_truths: Sequence[ScorerGroundTruth],
) -> bool:
    """Prove policy output is unchanged while evaluator-only labels vary.

    Truth objects are deliberately not passed to ``policy``.  Re-running for
    every perturbation also catches accidental dependence on mutable external
    state in ordinary policy adapters.
    """

    for truth in alternate_truths:
        if truth.scenario_id != visible.scenario_id:
            raise ValueError("All alternate truths must refer to the visible scenario")
    outputs = [_canonical_output(run_policy(policy, visible)) for _ in range(max(1, len(alternate_truths)))]
    return all(value == outputs[0] for value in outputs[1:])


def aggregate_scores(scores: Sequence[CaseScore]) -> dict[str, float | int]:
    if not scores:
        return {"case_count": 0}
    count = len(scores)

    def mean(attribute: str) -> float:
        return sum(float(getattr(score, attribute)) for score in scores) / count

    return {
        "case_count": count,
        "target_gap_accuracy": mean("target_gap_correct"),
        "acceptable_action_rate": mean("action_acceptable"),
        "decision_changing_evidence_priority_rate": mean("decision_changing_evidence_priority"),
        "competing_explanation_coverage": mean("competing_explanation_coverage"),
        "unnecessary_action_rate": mean("unnecessary_action"),
        "review_artifact_completeness_proxy": mean("review_artifact_completeness_proxy"),
        "mean_payload_bytes": mean("payload_bytes"),
    }


def export_split_dataset(
    visible_path: str,
    truth_path: str,
    visible_scenarios: Sequence[VisibleScenario],
    scorer_truth: Sequence[ScorerGroundTruth],
) -> None:
    """Write visible inputs and scorer-only labels to intentionally separate files."""

    visible_ids = [item.scenario_id for item in visible_scenarios]
    truth_ids = [item.scenario_id for item in scorer_truth]
    if len(set(visible_ids)) != len(visible_ids) or len(set(truth_ids)) != len(truth_ids):
        raise ValueError("Scenario IDs must be unique in each split")
    if set(visible_ids) != set(truth_ids):
        raise ValueError("Visible and scorer-only splits must contain the same scenario IDs")
    visible_payload = [asdict(item) for item in visible_scenarios]
    truth_payload = [
        {
            **asdict(item),
            "acceptable_action_ids": sorted(item.acceptable_action_ids),
            "decision_changing_action_ids": sorted(item.decision_changing_action_ids),
            "required_competing_explanations": sorted(item.required_competing_explanations),
        }
        for item in scorer_truth
    ]
    with open(visible_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(visible_payload, handle, sort_keys=True, ensure_ascii=False, indent=2)
        handle.write("\n")
    with open(truth_path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(truth_payload, handle, sort_keys=True, ensure_ascii=False, indent=2)
        handle.write("\n")
