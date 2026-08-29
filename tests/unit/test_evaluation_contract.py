import json

from bionexus.evaluation_contract import (
    PolicyOutput,
    ScorerGroundTruth,
    VisibleScenario,
    aggregate_scores,
    deterministic_replay,
    evaluate_output,
    export_split_dataset,
    hidden_truth_invariance,
)


def _visible():
    return VisibleScenario(
        scenario_id="case-1",
        claim="A marker supports state X",
        observed_evidence=("marker overlap",),
        unresolved_gaps=("batch confounding", "alternative state"),
        available_actions=("batch-check", "more-markers"),
        competing_explanations=("state Y",),
    )


def _truth(target="batch confounding"):
    return ScorerGroundTruth(
        scenario_id="case-1",
        target_gap_id=target,
        acceptable_action_ids=frozenset({"batch-check"}),
        decision_changing_action_ids=frozenset({"batch-check"}),
        required_competing_explanations=frozenset({"state Y"}),
    )


def _policy(_scenario):
    return PolicyOutput(
        target_gap_id="batch confounding",
        action_id="batch-check",
        considered_explanations=("state Y",),
        claim_impact="Could reduce support for state X",
        rationale="Resolve a plausible confounder first",
    )


def test_policy_cannot_receive_scorer_truth_and_is_hidden_truth_invariant():
    seen_types = []

    def observing_policy(value):
        seen_types.append(type(value).__name__)
        return _policy(value)

    assert hidden_truth_invariance(observing_policy, _visible(), [_truth(), _truth("alternative state")])
    assert seen_types == ["VisibleScenario", "VisibleScenario"]


def test_score_depends_on_output_not_policy_name():
    visible = _visible()
    output = _policy(visible)
    baseline = evaluate_output(visible, _truth(), output)

    def frontier(_scenario):
        return output

    def keyword_baseline(_scenario):
        return output

    assert evaluate_output(visible, _truth(), frontier(visible)) == baseline
    assert evaluate_output(visible, _truth(), keyword_baseline(visible)) == baseline


def test_metrics_have_explicit_direction_and_proxy_name():
    score = evaluate_output(_visible(), _truth(), _policy(_visible()))
    aggregate = aggregate_scores([score])
    assert aggregate["target_gap_accuracy"] == 1.0
    assert aggregate["unnecessary_action_rate"] == 0.0
    assert aggregate["review_artifact_completeness_proxy"] == 1.0


def test_deterministic_replay_really_reruns_policy():
    calls = 0

    def unstable(_scenario):
        nonlocal calls
        calls += 1
        return PolicyOutput(target_gap_id=str(calls), action_id=None, abstained=True)

    assert deterministic_replay(_policy, _visible(), repeats=3)
    assert not deterministic_replay(unstable, _visible(), repeats=3)
    assert calls == 3


def test_dataset_export_physically_separates_visible_input_and_gold(tmp_path):
    visible_path = tmp_path / "visible.json"
    truth_path = tmp_path / "scorer-only.json"
    export_split_dataset(str(visible_path), str(truth_path), [_visible()], [_truth()])
    visible_payload = json.loads(visible_path.read_text(encoding="utf-8"))
    truth_payload = json.loads(truth_path.read_text(encoding="utf-8"))
    assert "target_gap_id" not in visible_payload[0]
    assert truth_payload[0]["target_gap_id"] == "batch confounding"
