"""Synthetic contract tests only: no real humans, executions or scientific labels."""
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from bionexus.de_external_study import digest
from bionexus.matched_claim_study import (
    CONDITION_FIELDS,
    main,
    matched_observation_template,
    matched_template,
    score_matched_study,
    validate_matched_plan,
)
from bionexus.pilot_costs import ARMS, COST_FIELDS


@pytest.fixture
def recorded(tmp_path):
    artifacts = {}

    def artifact(value):
        raw = json.dumps(value, sort_keys=True).encode()
        sha = hashlib.sha256(raw).hexdigest()
        (tmp_path / sha).write_bytes(raw)
        artifacts[sha] = sha
        return sha

    plan = matched_template()
    plan.update(study_id="TEST_ONLY", intended_use="fixture bounded statement",
                source_sha256=artifact("source"), frozen_at="2026-09-20T00:00:00Z",
                developer_ids=["fixture-developer"], development_dataset_sha256=[])
    protocol = plan["matched_protocol"]
    protocol["shared_conditions"] = {k: artifact(k) if k.endswith("sha256") else f"fixture-{k}"
                                     for k in CONDITION_FIELDS}
    protocol.update(arm_prompt_sha256={a: artifact(a) for a in ARMS},
                    allocation_sha256=artifact("allocation"), analysis_plan_sha256=artifact("analysis"),
                    endpoints={"minimum_unsupported_reduction": 0,
                               "maximum_valid_retention_loss": 0,
                               "minimum_valid_retention": 0.9,
                               "minimum_minutes_saved_per_task": 0})
    for i in range(4):
        plan["cases"].append({
            "case_id": f"case-{i}", "packet_sha256": artifact(f"packet-{i}"),
            "dataset_sha256": artifact(f"dataset-{i // 2}"), "study_cluster_id": f"study-{i // 2}",
            "execution_evidence_sha256": artifact(f"evidence-{i}"),
            "task_family": "fixture", "site_id": "fixture-site", "data_origin": "REAL_TASK",
            "not_used_in_development": True, "operators": {a: f"human-{i}-{a}" for a in ARMS},
        })
    obs = matched_observation_template(plan)
    obs["installation_totals"] = {"fixture-site": {"baseline": 4, "assisted": 2}}
    for i, (case, row) in enumerate(zip(plan["cases"], obs["cases"])):
        row["reference_reviews"] = [{
            "reviewer_id": f"reference-{r}", "label": "VALID" if i % 2 == 0 else "INVALID",
            "rationale": "software fixture, not a real scientific judgment",
            "packet_sha256": case["packet_sha256"], "evidence_sha256": artifact(f"reference-{i}-{r}"),
            "reviewed_at": "2026-09-20T01:00:00Z", "blinded_to_arms": True,
            "independent_of_development": True,
        } for r in range(2)]
        row["costs"].update(comparison="PAIRED_SAME_CASE", allocation_note="fixture disjoint costs")
        for arm in ARMS:
            start = datetime(2026, 9, 20, 2 + i, tzinfo=timezone.utc)
            amount = 1 if arm == "baseline" else 0.5
            row["time_logs_complete"][arm] = True
            row["costs"][arm] = dict.fromkeys(COST_FIELDS, amount)
            row["arms"][arm] = {
                "decision": "ACCEPT" if arm == "baseline" or i % 2 == 0 else "HOLD",
                "operator_id": case["operators"][arm], "artifact_sha256": artifact(f"output-{i}-{arm}"),
                "source_sha256": plan["source_sha256"], "packet_sha256": case["packet_sha256"],
                "execution_evidence_sha256": case["execution_evidence_sha256"],
                "conditions": deepcopy(protocol["shared_conditions"]),
                "prompt_sha256": protocol["arm_prompt_sha256"][arm], "binding_enabled": arm == "assisted",
                "session_id": f"session-{i}-{arm}", "fresh_session": True,
                "started_at": start.isoformat(), "finished_at": (start + timedelta(minutes=10)).isoformat(),
                "trace_sha256": artifact(f"trace-{i}-{arm}"),
            }
            for j, category in enumerate(COST_FIELDS):
                event = {"event_id": f"event-{i}-{arm}-{j}", "case_id": case["case_id"], "arm": arm,
                         "category": category, "person_id": case["operators"][arm],
                         "source": "HUMAN_ACTIVE_TIMER",
                         "started_at": (start + timedelta(minutes=j)).isoformat(),
                         "ended_at": (start + timedelta(minutes=j + amount)).isoformat()}
                event["raw_log_sha256"] = artifact(event)
                obs["time_events"].append(event)
    obs["artifacts"] = artifacts
    return plan, obs, tmp_path


def score(recorded):
    plan, obs, root = recorded
    return score_matched_study(plan, obs, evidence_root=root, expected_plan_sha256=digest(plan))


def test_preservation_does_not_require_improving_already_perfect_baseline(recorded):
    report = score(recorded)
    assert report["comparison_blockers"] == []
    assert report["base_summary"]["joint_error_reduction_observed"] is False
    assert report["joint_sample_criteria_met"] is True
    assert report["effects_descriptive"]["valid_retention_change"] == 0
    assert report["effects_descriptive"]["minutes_saved_per_task"] == 2.5
    assert len(report["by_study_cluster"]) == 2
    assert report["causal_benefit"] == report["external_validation"] == "NOT_ESTABLISHED"
    assert report["inferential_support"] == "NOT_ASSESSED"


@pytest.mark.parametrize("field", CONDITION_FIELDS)
def test_each_shared_condition_is_checked(recorded, field):
    recorded[1]["cases"][0]["arms"]["assisted"]["conditions"][field] = "different"
    report = score(recorded)
    assert report["joint_sample_criteria_met"] is None
    assert any("conditions_mismatch" in b for b in report["comparison_blockers"])


@pytest.mark.parametrize("decision", ["HOLD", "ACCEPT", "FAILED"])
def test_trivial_policies_cannot_pass_joint_gate(recorded, decision):
    for row in recorded[1]["cases"]:
        row["arms"]["assisted"]["decision"] = decision
    assert score(recorded)["joint_sample_criteria_met"] is False


def test_retention_loss_and_positive_margin_are_not_hidden(recorded):
    recorded[1]["cases"][0]["arms"]["assisted"]["decision"] = "HOLD"
    report = score(recorded)
    assert report["sample_criteria"]["unsupported_reduced"] is True
    assert report["sample_criteria"]["valid_retention_preserved"] is False
    assert report["joint_sample_criteria_met"] is False


def test_time_gain_must_exceed_prespecified_margin(recorded):
    plan, obs, _ = recorded
    plan["matched_protocol"]["endpoints"]["minimum_minutes_saved_per_task"] = 3
    obs["plan_sha256"] = digest(plan)
    assert score(recorded)["sample_criteria"]["human_cost_reduced"] is False


@pytest.mark.parametrize("change", ["late_reference", "session", "prompt", "evidence", "binding", "operator"])
def test_confounding_prevents_comparison(recorded, change):
    row = recorded[1]["cases"][0]
    output = row["arms"]["assisted"]
    if change == "late_reference":
        row["reference_reviews"][0]["reviewed_at"] = "2026-09-20T02:01:00Z"
    elif change == "session":
        output["session_id"] = row["arms"]["baseline"]["session_id"]
    elif change == "binding":
        output["binding_enabled"] = False
    else:
        field = {"prompt": "prompt_sha256", "evidence": "execution_evidence_sha256",
                 "operator": "operator_id"}[change]
        output[field] = "f" * 64
    assert score(recorded)["joint_sample_criteria_met"] is None


def test_missing_disputed_and_failed_tasks_are_not_dropped(recorded):
    plan, obs, _ = recorded
    obs["cases"][0]["reference_reviews"][0]["label"] = "UNRESOLVED"
    obs["cases"][1]["arms"].pop("assisted")
    obs["time_events"] = [e for e in obs["time_events"] if not
                          (e["case_id"] == "case-1" and e["arm"] == "assisted")]
    obs["cases"][1]["time_logs_complete"]["assisted"] = False
    obs["cases"][2]["arms"]["assisted"]["decision"] = "FAILED"
    report = score(recorded)
    assert report["base_summary"]["registered_tasks"] == len(plan["cases"]) == 4
    assert report["base_summary"]["unresolved_reference_tasks"] == 1
    assert report["base_summary"]["metrics"]["assisted"]["failures"] == 1
    assert report["joint_sample_criteria_met"] is None


@pytest.mark.parametrize("change", ["overlap", "wrong_total", "machine", "negative", "duplicate"])
def test_bad_timer_records_are_rejected(recorded, change):
    obs = recorded[1]
    event = obs["time_events"][0]
    if change == "overlap":
        obs["time_events"][1]["started_at"] = event["started_at"]
    elif change == "wrong_total":
        obs["cases"][0]["costs"]["baseline"]["review"] = 99
    elif change == "machine":
        event["source"] = "MACHINE_WALL_TIME"
    elif change == "negative":
        event["ended_at"] = event["started_at"]
    else:
        obs["time_events"].append(deepcopy(event))
    with pytest.raises(ValueError):
        score(recorded)


def test_missing_timer_does_not_become_zero(recorded):
    recorded[1]["cases"][0]["time_logs_complete"]["assisted"] = False
    assert score(recorded)["joint_sample_criteria_met"] is None


def test_reference_reviewer_cannot_also_review_an_arm(recorded):
    # Use a different interval to isolate exposure from overlap detection.
    _, obs, root = recorded
    event = obs["time_events"][1]
    event["person_id"] = "reference-0"
    raw = json.dumps({k: v for k, v in event.items() if k != "raw_log_sha256"}).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (root / sha).write_bytes(raw)
    obs["artifacts"][sha] = sha
    event["raw_log_sha256"] = sha
    assert "case-0:reference_reviewer_participated_in_arm" in score(recorded)["comparison_blockers"]


def test_raw_timer_content_must_match_reported_events(recorded):
    # Valid intervals and totals alone are insufficient if raw log disagrees.
    recorded[1]["time_events"][1]["person_id"] = "different-person"
    with pytest.raises(ValueError, match="raw timer log content"):
        score(recorded)


def test_hash_strings_alone_never_establish_matched_comparison(recorded):
    plan, obs, _ = recorded
    report = score_matched_study(plan, obs)
    assert report["joint_sample_criteria_met"] is None
    assert "artifact_bytes_not_checked" in report["comparison_blockers"]


@pytest.mark.parametrize("change", ["tamper", "escape", "absolute"])
def test_bad_artifact_bytes_or_paths_rejected(recorded, change):
    plan, obs, root = recorded
    sha = plan["source_sha256"]
    if change == "tamper":
        (root / sha).write_bytes(b"changed")
    elif change == "escape":
        obs["artifacts"][sha] = "../outside.json"
    else:
        obs["artifacts"][sha] = str(root / sha)
    with pytest.raises(ValueError):
        score(recorded)


def test_missing_artifacts_block_without_dropping_tasks(recorded):
    plan, obs, _ = recorded
    obs["artifacts"].pop(plan["source_sha256"])
    report = score(recorded)
    assert report["joint_sample_criteria_met"] is None
    assert report["effects_descriptive"]["tasks"] == 4


def test_one_dataset_cannot_be_split_into_independent_clusters(recorded):
    plan = recorded[0]
    plan["cases"][1]["study_cluster_id"] = "pretend-independent"
    with pytest.raises(ValueError, match="clusters"):
        validate_matched_plan(plan)


@pytest.mark.parametrize("value", [None, True, -1, float("nan"), 2])
def test_invalid_rate_margins_rejected(recorded, value):
    recorded[0]["matched_protocol"]["endpoints"]["maximum_valid_retention_loss"] = value
    with pytest.raises(ValueError):
        validate_matched_plan(recorded[0])


def test_template_has_no_invented_subjects_and_refuses_overwrite(tmp_path):
    out = tmp_path / "plan.json"
    assert main(["template", "--out", str(out)]) == 0
    before = out.read_bytes()
    assert json.loads(before)["cases"] == []
    with pytest.raises(SystemExit):
        main(["template", "--out", str(out)])
    assert out.read_bytes() == before


def test_cli_scores_frozen_records(recorded):
    plan, obs, root = recorded
    p, o, result = root / "plan.json", root / "observations.json", root / "summary.json"
    p.write_text(json.dumps(plan), encoding="utf-8")
    o.write_text(json.dumps(obs), encoding="utf-8")
    assert main(["score", str(p), str(o), "--evidence-root", str(root),
                 "--expected-plan-sha256", digest(plan), "--out", str(result)]) == 0
    assert json.loads(result.read_text())["joint_sample_criteria_met"] is True
