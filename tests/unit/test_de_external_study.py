"""Synthetic software tests, not externally adjudicated research outcomes."""
from copy import deepcopy

import pytest

from bionexus.de_external_study import digest, main, observation_template, score_study
from bionexus.pilot_costs import COST_FIELDS, empty_costs, summarize_costs


def study():
    plan = {"schema": "bionexus.de-external-plan.v1", "study_id": "TEST_ONLY",
            "intended_use": "test a bounded DE statement", "source_sha256": "a" * 64,
            "frozen_at": "2026-09-10T00:00:00Z", "developer_ids": ["developer"],
            "development_dataset_sha256": [], "cases": []}
    for index in range(4):
        plan["cases"].append({"case_id": f"case-{index}", "packet_sha256": str(index) * 64,
                              "dataset_sha256": "b" * 64, "task_family": "same_dataset",
                              "site_id": "TEST_SITE", "data_origin": "REAL_TASK",
                              "not_used_in_development": True})
    obs = observation_template(plan)
    obs["installation_totals"] = {"TEST_SITE": {"baseline": 40, "assisted": 20}}
    for index, case in enumerate(obs["cases"]):
        valid = index < 2
        case["reference_reviews"] = [
            {"reviewer_id": f"reviewer-{r}", "label": "VALID" if valid else "INVALID",
             "packet_sha256": str(index) * 64, "evidence_sha256": "e" * 64,
             "reviewed_at": "2026-09-10T01:00:00Z", "rationale": "software fixture, not science",
             "blinded_to_arms": True, "independent_of_development": True} for r in range(2)]
        case["arms"] = {arm: {"decision": ("HOLD" if valid else "ACCEPT") if arm == "baseline"
                               else ("ACCEPT" if valid else "HOLD"),
                               "operator_id": arm, "artifact_sha256": "c" * 64,
                               "packet_sha256": str(index) * 64,
                               "source_sha256": "a" * 64, "finished_at": "2026-09-10T02:00:00Z"}
                        for arm in ("baseline", "assisted")}
        case["costs"].update(comparison="PAIRED_SAME_CASE", allocation_note="charged once, disjoint person-minutes")
        for arm in ("baseline", "assisted"):
            case["costs"][arm] = dict.fromkeys(COST_FIELDS, 10 if arm == "baseline" else 5)
    return plan, obs


def test_joint_success_is_descriptive_never_external_proof():
    plan, obs = study()
    report = score_study(plan, obs, expected_plan_sha256=digest(plan))
    assert report["joint_error_reduction_observed"] is True
    assert report["cohort_person_minutes_saved"] == 100
    assert report["joint_quality_and_time_gain_observed"] is True
    assert report["net_benefit"] == report["external_validation"] == "NOT_ESTABLISHED"
    assert len(report["by_task_family"]) == 1  # four tasks are not four independent datasets


@pytest.mark.parametrize("decision", ["HOLD", "ACCEPT", "FAILED"])
def test_degenerate_policies_cannot_show_joint_success(decision):
    plan, obs = study()
    for case in obs["cases"]:
        case["arms"]["assisted"]["decision"] = decision
    report = score_study(plan, obs)
    assert report["joint_error_reduction_observed"] is False
    if decision == "FAILED":
        assert report["metrics"]["assisted"]["false_hold_rate"] == 1


def test_missing_task_stays_in_denominator_and_prevents_success():
    plan, obs = study()
    del obs["cases"][0]["arms"]["assisted"]
    report = score_study(plan, obs)
    assert report["metrics"]["assisted"]["valid_tasks"] == 2
    assert report["metrics"]["assisted"]["false_hold_rate_worst_case"] == 0.5
    assert report["joint_error_reduction_observed"] is None
    obs["cases"].pop()
    report = score_study(plan, obs)
    assert report["registered_tasks"] == 4
    assert report["unresolved_reference_tasks"] == 1


@pytest.mark.parametrize("change", ["disagreement", "developer", "operator", "late", "unblinded"])
def test_reference_problems_never_silently_adjudicated(change):
    plan, obs = study()
    reference = obs["cases"][0]["reference_reviews"][0]
    if change == "disagreement":
        reference["label"] = "INVALID"
    elif change in ("developer", "operator"):
        reference["reviewer_id"] = "developer" if change == "developer" else "baseline"
    elif change == "late":
        reference["reviewed_at"] = "2026-09-10T03:00:00Z"
    else:
        reference["blinded_to_arms"] = False
    report = score_study(plan, obs)
    assert report["unresolved_reference_tasks"] == 1
    assert report["joint_error_reduction_observed"] is None


@pytest.mark.parametrize("change", ["duplicate", "extra", "wrong_source", "wrong_packet", "anchor", "prefreeze"])
def test_integrity_and_cohort_changes_rejected(change):
    plan, obs = study()
    kwargs = {}
    if change == "duplicate":
        obs["cases"].append(deepcopy(obs["cases"][0]))
    elif change == "extra":
        obs["cases"][0]["case_id"] = "unregistered"
    elif change == "wrong_source":
        obs["cases"][0]["arms"]["assisted"]["source_sha256"] = "f" * 64
    elif change == "wrong_packet":
        obs["cases"][0]["reference_reviews"][0]["packet_sha256"] = "f" * 64
    elif change == "prefreeze":
        obs["cases"][0]["arms"]["assisted"]["finished_at"] = "2020-01-01T00:00:00Z"
    else:
        kwargs["expected_plan_sha256"] = "f" * 64
    with pytest.raises(ValueError):
        score_study(plan, obs, **kwargs)


def test_development_and_synthetic_excluded_but_retained():
    plan, obs = study()
    plan["cases"][0]["data_origin"] = "SYNTHETIC_DEMO"
    plan["cases"][1]["not_used_in_development"] = False
    obs["installation_totals"] = {}
    obs["plan_sha256"] = digest(plan)
    report = score_study(plan, obs)
    assert report["excluded_tasks"] == 2
    assert len(report["cases"]) == 4
    assert report["joint_error_reduction_observed"] is None  # no eligible valid references
    plan["development_dataset_sha256"] = ["b" * 64]
    obs["plan_sha256"] = digest(plan)
    assert score_study(plan, obs)["declared_holdout_tasks"] == 0


def test_all_costs_both_arms_negative_and_missing():
    plan, obs = study()
    obs["cases"][0]["costs"]["assisted"]["communication"] = 200
    report = score_study(plan, obs)
    assert report["cohort_person_minutes_saved"] == -95
    assert report["joint_quality_and_time_gain_observed"] is False
    obs["cases"][0]["costs"]["baseline"]["false_alarm_handling"] = None
    report = score_study(plan, obs)
    assert report["fully_costed_tasks"] == 3
    assert report["cohort_person_minutes_saved"] is None
    assert report["recorded_person_minutes_saved"] == 75


def test_installation_cannot_be_silently_amortized_out_of_cohort():
    plan, obs = study()
    obs["installation_totals"]["TEST_SITE"]["assisted"] = 200
    with pytest.raises(ValueError, match="reconcile"):
        score_study(plan, obs)
    obs["installation_totals"] = {}
    assert score_study(plan, obs)["cohort_person_minutes_saved"] is None


@pytest.mark.parametrize("value", [True, -1, float("inf"), float("nan"), "1"])
def test_invalid_costs_rejected(value):
    costs = empty_costs()
    costs["assisted"]["communication"] = value
    with pytest.raises(ValueError):
        summarize_costs(costs)


def test_cli_refuses_overwrite_and_duplicate_json_keys(tmp_path):
    out = tmp_path / "new.json"
    assert main(["template", "--out", str(out)]) == 0
    before = out.read_bytes()
    with pytest.raises(SystemExit):
        main(["template", "--out", str(out)])
    assert out.read_bytes() == before
    bad = tmp_path / "bad.json"
    bad.write_text('{"schema": 1, "schema": 2}', encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["template", "--plan", str(bad), "--out", str(tmp_path / "never.json")])
