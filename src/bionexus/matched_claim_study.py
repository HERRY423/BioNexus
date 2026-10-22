"""Offline matched-condition claim study checks; never creates research observations.

Extends de_external_study's frozen cohort and five-category cost accounting.
Reported effects are descriptive. Neither matching nor file hashes authenticate
execution, humans, randomization, or scientific truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

from bionexus.de_external_study import (
    _hash,
    _index,
    _load,
    _text,
    _time,
    digest,
    observation_template,
    score_study,
    template,
    validate_plan,
)
from bionexus.pilot_costs import ARMS, COST_FIELDS

PROTOCOL_SCHEMA = "bionexus.matched-claim-protocol.v1"
CONDITION_FIELDS = (
    "model_snapshot", "host_version", "tools_sha256", "environment_sha256",
    "generation_config_sha256", "common_prompt_sha256", "resource_budget_sha256",
)
ENDPOINT_FIELDS = (
    "minimum_unsupported_reduction", "maximum_valid_retention_loss",
    "minimum_valid_retention", "minimum_minutes_saved_per_task",
)


def validate_matched_plan(plan: dict) -> dict:
    cases = validate_plan(plan)
    protocol = plan.get("matched_protocol")
    if not isinstance(protocol, dict) or protocol.get("schema") != PROTOCOL_SCHEMA:
        raise ValueError("matched_protocol required")
    conditions = protocol.get("shared_conditions")
    if not isinstance(conditions, dict) or set(conditions) != set(CONDITION_FIELDS):
        raise ValueError("declare all shared_conditions exactly")
    for key, value in conditions.items():
        (_hash if key.endswith("sha256") else _text)(value)
    for key in ("allocation_sha256", "analysis_plan_sha256"):
        _hash(protocol.get(key))
    prompts = protocol.get("arm_prompt_sha256")
    if not isinstance(prompts, dict) or set(prompts) != set(ARMS):
        raise ValueError("both frozen arm prompts required")
    for value in prompts.values():
        _hash(value)
    endpoints = protocol.get("endpoints")
    if not isinstance(endpoints, dict) or set(endpoints) != set(ENDPOINT_FIELDS):
        raise ValueError("explicit prospective endpoint margins required")
    for key, value in endpoints.items():
        if type(value) not in (float, int) or not math.isfinite(value) or value < 0:
            raise ValueError("endpoint margins must be finite nonnegative numbers")
        if key != "minimum_minutes_saved_per_task" and value > 1:
            raise ValueError("rate margins must be in [0, 1]")
    if endpoints["minimum_valid_retention"] <= 0:
        raise ValueError("positive absolute retention floor required to reject hold-all")
    dataset_clusters = {}
    for case in cases.values():
        cluster = _text(case.get("study_cluster_id"))
        _hash(case.get("execution_evidence_sha256"))
        if dataset_clusters.setdefault(case["dataset_sha256"], cluster) != cluster:
            raise ValueError("one dataset cannot be split into independent study clusters")
        allocation = case.get("operators")
        if not isinstance(allocation, dict) or set(allocation) != set(ARMS):
            raise ValueError("freeze both operator allocations before outputs")
        for operator in allocation.values():
            _text(operator)
        if len(set(allocation.values())) != 2:
            raise ValueError("same-case human crossover is not supported")
    return protocol


def matched_template() -> dict:
    plan = template()
    plan["matched_protocol"] = {
        "schema": PROTOCOL_SCHEMA,
        "shared_conditions": dict.fromkeys(CONDITION_FIELDS),
        "arm_prompt_sha256": dict.fromkeys(ARMS),
        "allocation_sha256": None, "analysis_plan_sha256": None,
        "endpoints": dict.fromkeys(ENDPOINT_FIELDS),
    }
    return plan


def matched_observation_template(plan: dict) -> dict:
    validate_matched_plan(plan)
    observations = observation_template(plan)
    observations.update(artifacts={}, time_events=[])
    for case in observations["cases"]:
        case["time_logs_complete"] = dict.fromkeys(ARMS, False)
    return observations


def _verify_artifacts(required: set[str], artifacts: dict, root: Path | None) -> list[str]:
    if not isinstance(artifacts, dict):
        raise ValueError("artifacts must map SHA-256 to a relative file path")
    if root is None:
        return ["artifact_bytes_not_checked"]
    root = root.resolve(strict=True)
    missing = []
    for sha in sorted(required):
        _hash(sha)
        relative = artifacts.get(sha)
        if relative is None:
            missing.append(f"missing_artifact:{sha}")
            continue
        path = Path(_text(relative))
        if path.is_absolute():
            raise ValueError("artifact paths must be relative")
        resolved = (root / path).resolve()
        if not resolved.is_relative_to(root):
            raise ValueError("artifact path escapes evidence root")
        if not resolved.is_file():
            missing.append(f"missing_artifact:{sha}")
            continue
        hasher = hashlib.sha256()
        with resolved.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)
        if hasher.hexdigest() != sha:
            raise ValueError(f"artifact byte mismatch: {sha}")
    return missing


def _time_checks(plan: dict, observations: dict, observed: dict) -> list[str]:
    events = _index(observations.get("time_events", []), "event_id")
    cases = {c["case_id"]: c for c in plan["cases"]}
    totals: dict[tuple, float] = defaultdict(float)
    intervals: dict[str, list] = defaultdict(list)
    participants: dict[tuple, set] = defaultdict(set)
    for event in events.values():
        cid, arm, category = event.get("case_id"), event.get("arm"), event.get("category")
        if cid not in cases or arm not in ARMS or category not in COST_FIELDS:
            raise ValueError("time event must name a registered case, arm and cost category")
        person = _text(event.get("person_id"))
        if event.get("source") != "HUMAN_ACTIVE_TIMER":
            raise ValueError("machine duration or retrospective estimate is not an active human timer")
        _hash(event.get("raw_log_sha256"))
        start, end = _time(event.get("started_at")), _time(event.get("ended_at"))
        if start < _time(plan["frozen_at"]) or end <= start:
            raise ValueError("invalid time event interval")
        output = observed.get(cid, {}).get("arms", {}).get(arm)
        if output is None:
            raise ValueError("time event requires its arm output (FAILED is allowed)")
        if end > _time(output["finished_at"]):
            raise ValueError("time event ends after final arm completion")
        if category != "installation":
            if start < _time(output["started_at"]):
                raise ValueError("review activity predates arm start")
            participants[cid, arm].add(person)
        intervals[person].append((start, end))
        totals[cid, arm, category] += (end - start).total_seconds() / 60
    for person_intervals in intervals.values():
        ordered = sorted(person_intervals)
        if any(right[0] < left[1] for left, right in zip(ordered, ordered[1:])):
            raise ValueError("one person's timer intervals overlap; person-minutes double counted")
    blockers = []
    for cid, case in cases.items():
        for arm in ARMS:
            # The final decision maker also counts as exposed to this case.
            participants[cid, arm].add(case["operators"][arm])
            obs = observed.get(cid, {})
            if obs.get("time_logs_complete", {}).get(arm) is not True:
                blockers.append(f"{cid}:{arm}:incomplete_time_logs")
                continue
            costs = (obs.get("costs") or {}).get(arm, {})
            for category in COST_FIELDS:
                value = costs.get(category)
                if value is None:
                    blockers.append(f"{cid}:{arm}:{category}:unknown_cost")
                elif not math.isclose(totals[cid, arm, category], value, abs_tol=1e-6, rel_tol=1e-9):
                    raise ValueError("active timer events do not reconcile with reported person-minutes")
        if participants[cid, "baseline"] & participants[cid, "assisted"]:
            blockers.append(f"{cid}:human_exposed_to_both_arms")
        reviewers = {r["reviewer_id"] for r in observed.get(cid, {}).get("reference_reviews", [])}
        if reviewers & (participants[cid, "baseline"] | participants[cid, "assisted"]):
            blockers.append(f"{cid}:reference_reviewer_participated_in_arm")
    return blockers


def _effects(rows: list[dict]) -> dict:
    invalid = [r for r in rows if r["reference_label"] == "INVALID"]
    valid = [r for r in rows if r["reference_label"] == "VALID"]

    def accepted(group: list[dict], arm: str) -> float | None:
        return sum(r["decisions"][arm] == "ACCEPT" for r in group) / len(group) if group else None

    invalid_b, invalid_a = accepted(invalid, "baseline"), accepted(invalid, "assisted")
    valid_b, valid_a = accepted(valid, "baseline"), accepted(valid, "assisted")
    costs = [r["costs"]["minutes_saved"] for r in rows]
    return {
        "tasks": len(rows), "valid_tasks": len(valid), "invalid_tasks": len(invalid),
        "unsupported_reduction": invalid_b - invalid_a if invalid else None,
        "valid_retention_change": valid_a - valid_b if valid else None,
        "assisted_valid_retention": valid_a,
        "minutes_saved_per_task": sum(costs) / len(costs) if costs and all(c is not None for c in costs) else None,
    }


def score_matched_study(plan: dict, observations: dict, *, evidence_root: Path | None = None,
                        expected_plan_sha256: str | None = None) -> dict:
    protocol = validate_matched_plan(plan)
    base = score_study(plan, observations, expected_plan_sha256=expected_plan_sha256)
    observed = _index(observations["cases"], "case_id")
    blockers = [] if expected_plan_sha256 else ["externally_retained_plan_digest_not_provided"]
    required = {plan["source_sha256"], protocol["allocation_sha256"], protocol["analysis_plan_sha256"]}
    required.update(protocol["arm_prompt_sha256"].values())
    required.update(v for k, v in protocol["shared_conditions"].items() if k.endswith("sha256"))
    sessions = set()
    for case in plan["cases"]:
        cid = case["case_id"]
        required.update(case[k] for k in ("packet_sha256", "dataset_sha256", "execution_evidence_sha256"))
        obs = observed.get(cid, {})
        for review in obs.get("reference_reviews", []):
            required.add(review["evidence_sha256"])
        for arm in ARMS:
            output = obs.get("arms", {}).get(arm)
            if output is None:
                blockers.append(f"{cid}:{arm}:missing_output")
                continue
            if output.get("conditions") != protocol["shared_conditions"]:
                blockers.append(f"{cid}:{arm}:conditions_mismatch")
            for key, expected in (
                ("execution_evidence_sha256", case["execution_evidence_sha256"]),
                ("prompt_sha256", protocol["arm_prompt_sha256"][arm]),
                ("operator_id", case["operators"][arm]),
                ("source_sha256", plan["source_sha256"]),
            ):
                if output.get(key) != expected:
                    blockers.append(f"{cid}:{arm}:{key}_mismatch")
            if output.get("binding_enabled") is not (arm == "assisted"):
                blockers.append(f"{cid}:{arm}:wrong_intervention")
            session = _text(output.get("session_id"))
            if session in sessions or output.get("fresh_session") is not True:
                blockers.append(f"{cid}:{arm}:session_reuse")
            sessions.add(session)
            started, finished = _time(output.get("started_at")), _time(output["finished_at"])
            if started < _time(plan["frozen_at"]) or finished < started:
                raise ValueError("invalid arm execution interval")
            if any(_time(r["reviewed_at"]) >= started for r in obs.get("reference_reviews", [])):
                blockers.append(f"{cid}:{arm}:reference_not_frozen_before_start")
            required.add(output["artifact_sha256"])
            required.add(_hash(output.get("trace_sha256")))
    blockers.extend(_time_checks(plan, observations, observed))
    required.update(e["raw_log_sha256"] for e in observations.get("time_events", []))
    artifact_blockers = _verify_artifacts(required, observations.get("artifacts", {}), evidence_root)
    blockers.extend(artifact_blockers)
    if not artifact_blockers and evidence_root is not None:
        for event in observations.get("time_events", []):
            path = evidence_root / observations["artifacts"][event["raw_log_sha256"]]
            raw_event = _load(str(path))
            reported_event = {k: v for k, v in event.items() if k != "raw_log_sha256"}
            if digest(raw_event) != digest(reported_event):
                raise ValueError("raw timer log content differs from reported time event")
    rows = [r for r in base["cases"] if r["eligible_declared_holdout"]]
    if not rows:
        blockers.append("no_eligible_tasks")
    if any(r["reference_label"] == "UNRESOLVED" for r in rows):
        blockers.append("unresolved_reference")
    if base["cohort_person_minutes_saved"] is None:
        blockers.append("incomplete_cohort_costs")
    effects = _effects(rows)
    if not effects["valid_tasks"] or not effects["invalid_tasks"]:
        blockers.append("both_valid_and_invalid_tasks_required")
    margins = protocol["endpoints"]
    checks = None
    if not blockers:
        checks = {
            "unsupported_reduced": effects["unsupported_reduction"] > margins["minimum_unsupported_reduction"],
            "valid_retention_preserved": effects["valid_retention_change"] >= -margins["maximum_valid_retention_loss"],
            "valid_retention_floor_met": effects["assisted_valid_retention"] >= margins["minimum_valid_retention"],
            "human_cost_reduced": effects["minutes_saved_per_task"] > margins["minimum_minutes_saved_per_task"],
        }
    return {
        "schema": "bionexus.matched-claim-summary.v1", "study_id": plan["study_id"],
        "plan_sha256": digest(plan), "observations_sha256": digest(observations),
        "base_summary": base, "effects_descriptive": effects,
        "by_study_cluster": {cluster: _effects([r for r in rows if r["study_cluster_id"] == cluster])
                             for cluster in sorted({r["study_cluster_id"] for r in rows})},
        "comparison_blockers": sorted(set(blockers)), "sample_criteria": checks,
        "joint_sample_criteria_met": all(checks.values()) if checks is not None else None,
        "inferential_support": "NOT_ASSESSED", "causal_benefit": "NOT_ESTABLISHED",
        "external_validation": "NOT_ESTABLISHED", "scientific_authorization": "NONE",
        "limitations": [
            "This is frozen-candidate claim adjudication, not free-generation discovery recall.",
            "Effects are task-weighted descriptive differences, not noninferiority or superiority tests.",
            "Study clusters and participant allocation require independent audit; hashes cannot prove independence.",
            "Matching declarations and raw bytes cannot authenticate live model execution or human timing.",
            "Missing, failed and disputed cases are retained; do not infer success from partial effects.",
            "An external clustered analysis of randomized human review is required for causal benefit claims.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("template")
    init.add_argument("--plan")
    score = commands.add_parser("score")
    score.add_argument("plan")
    score.add_argument("observations")
    score.add_argument("--evidence-root", type=Path)
    score.add_argument("--expected-plan-sha256")
    for command in (init, score):
        command.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            result = matched_observation_template(_load(args.plan)) if args.plan else matched_template()
        else:
            result = score_matched_study(_load(args.plan), _load(args.observations),
                                         evidence_root=args.evidence_root,
                                         expected_plan_sha256=args.expected_plan_sha256)
        with Path(args.out).open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(1, f"Invalid matched study: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
