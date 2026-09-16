"""Offline scoring of a frozen, caller-supplied external DE task cohort.

No task selection, analysis execution, rule tuning, identity verification or
scientific authorization. Labels are never supplied to the audited product.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from bionexus.pilot_costs import ARMS, empty_costs, summarize_costs

PLAN_SCHEMA = "bionexus.de-external-plan.v1"
OBS_SCHEMA = "bionexus.de-external-observations.v1"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("nonempty text required")
    return value


def _hash(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("lowercase SHA-256 required")
    return value


def _time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(_text(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamps require a timezone")
    return parsed


def _index(rows: Any, key: str) -> dict[str, dict]:
    if not isinstance(rows, list):
        raise ValueError(f"{key} records must be a list")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("records must be objects")
        identity = _text(row.get(key))
        if identity in result:
            raise ValueError(f"duplicate {key}: {identity}")
        result[identity] = row
    return result


def validate_plan(plan: dict) -> dict[str, dict]:
    if not isinstance(plan, dict):
        raise ValueError("plan must be an object")
    if plan.get("schema") != PLAN_SCHEMA:
        raise ValueError("unsupported plan schema")
    _text(plan.get("study_id"))
    _text(plan.get("intended_use"))
    _hash(plan.get("source_sha256"))
    _time(plan.get("frozen_at"))
    for key in ("developer_ids", "development_dataset_sha256"):
        values = plan.get(key)
        if not isinstance(values, list) or len(set(values)) != len(values):
            raise ValueError(f"{key} requires a unique explicit list")
        for value in values:
            (_hash if key.endswith("sha256") else _text)(value)
    if not plan["developer_ids"]:
        raise ValueError("declare the development team")
    cases = _index(plan.get("cases"), "case_id")
    seen = set()
    for case in cases.values():
        for key in ("task_family", "site_id"):
            _text(case.get(key))
        _hash(case.get("dataset_sha256"))
        packet = _hash(case.get("packet_sha256"))
        if packet in seen:
            raise ValueError("duplicate task packet; repeated execution is not a new task")
        seen.add(packet)
        if case.get("data_origin") not in ("REAL_TASK", "SYNTHETIC_DEMO"):
            raise ValueError("declare case data_origin")
        if type(case.get("not_used_in_development")) is not bool:
            raise ValueError("declare not_used_in_development explicitly")
    return cases


def _reference(case: dict, observation: dict, plan: dict) -> tuple[str, list[str]]:
    reviews = _index(observation.get("reference_reviews", []), "reviewer_id")
    reasons, labels = [], []
    operator_ids = {v.get("operator_id") for v in observation.get("arms", {}).values() if isinstance(v, dict)}
    for reviewer, review in reviews.items():
        label = review.get("label")
        if label not in ("VALID", "INVALID", "UNRESOLVED"):
            raise ValueError("reference label must be VALID, INVALID or UNRESOLVED")
        _text(review.get("rationale"))
        _hash(review.get("evidence_sha256"))
        if review.get("packet_sha256") != case["packet_sha256"]:
            raise ValueError("reference review is bound to a different task")
        at = _time(review.get("reviewed_at"))
        if at < _time(plan["frozen_at"]):
            raise ValueError("reference review predates cohort freeze")
        if (review.get("blinded_to_arms") is not True or review.get("independent_of_development") is not True
                or reviewer in plan["developer_ids"] or reviewer in operator_ids):
            reasons.append("reference_independence_not_declared")
        for arm in observation.get("arms", {}).values():
            if at > _time(arm["finished_at"]):
                reasons.append("reference_not_frozen_before_arm_output")
        labels.append(label)
    if len(reviews) < 2:
        reasons.append("fewer_than_two_reference_reviewers")
    if not labels or len(set(labels)) != 1 or "UNRESOLVED" in labels:
        reasons.append("reference_disagreement_or_missing")
    return (labels[0] if not reasons else "UNRESOLVED"), sorted(set(reasons))


def _metrics(cases: list[dict], arm: str) -> dict:
    invalid = [c for c in cases if c["reference_label"] == "INVALID"]
    valid = [c for c in cases if c["reference_label"] == "VALID"]
    def count(rows: list[dict], decisions: tuple) -> int:
        return sum(c["decisions"][arm] in decisions for c in rows)
    false_accepts = count(invalid, ("ACCEPT",))
    false_holds = count(valid, ("HOLD", "FAILED"))
    missing_invalid, missing_valid = count(invalid, ("MISSING",)), count(valid, ("MISSING",))
    return {"invalid_tasks": len(invalid), "valid_tasks": len(valid),
            "false_accepts": false_accepts, "false_holds_or_failures": false_holds,
            "valid_retained": count(valid, ("ACCEPT",)),
            "missing_invalid": missing_invalid, "missing_valid": missing_valid,
            "false_accept_rate": false_accepts / len(invalid) if invalid else None,
            "false_hold_rate": false_holds / len(valid) if valid else None,
            "false_accept_rate_worst_case": (false_accepts + missing_invalid) / len(invalid) if invalid else None,
            "false_hold_rate_worst_case": (false_holds + missing_valid) / len(valid) if valid else None,
            "failures": count(cases, ("FAILED",)), "missing": count(cases, ("MISSING",))}


def score_study(plan: dict, observations: dict, *, expected_plan_sha256: str | None = None) -> dict:
    registered = validate_plan(plan)
    if not isinstance(observations, dict):
        raise ValueError("observations must be an object")
    plan_hash = digest(plan)
    if expected_plan_sha256 is not None and _hash(expected_plan_sha256) != plan_hash:
        raise ValueError("externally retained plan digest mismatch")
    if observations.get("schema") != OBS_SCHEMA or observations.get("plan_sha256") != plan_hash:
        raise ValueError("observations do not bind this frozen plan")
    observed = _index(observations.get("cases"), "case_id")
    if set(observed) - set(registered):
        raise ValueError("unregistered observations cannot enter the cohort")
    rows = []
    for cid, case in registered.items():
        observation = observed.get(cid, {})
        decisions = dict.fromkeys(ARMS, "MISSING")
        arms = observation.get("arms", {})
        if not isinstance(arms, dict) or set(arms) - set(ARMS):
            raise ValueError("unknown comparison arm")
        for arm, output in arms.items():
            if not isinstance(output, dict):
                raise ValueError("arm output must be an object")
            if output.get("decision") not in ("ACCEPT", "HOLD", "FAILED"):
                raise ValueError("arm decision must be ACCEPT, HOLD or FAILED")
            _text(output.get("operator_id"))
            _hash(output.get("artifact_sha256"))
            if output.get("packet_sha256") != case["packet_sha256"]:
                raise ValueError("arm output is bound to a different task")
            if _time(output.get("finished_at")) < _time(plan["frozen_at"]):
                raise ValueError("arm output predates freeze")
            if arm == "assisted" and output.get("source_sha256") != plan["source_sha256"]:
                raise ValueError("assisted source differs from frozen source")
            decisions[arm] = output["decision"]
        label, reasons = _reference(case, observation, plan)
        if case["data_origin"] == "SYNTHETIC_DEMO":
            reasons.append("synthetic_demo")
        if not case["not_used_in_development"] or case["dataset_sha256"] in plan["development_dataset_sha256"]:
            reasons.append("development_overlap")
        eligible = "synthetic_demo" not in reasons and "development_overlap" not in reasons
        rows.append({**case, "eligible_declared_holdout": eligible,
                     "reference_label": label, "limitations": reasons, "decisions": decisions,
                     "costs": summarize_costs(observation.get("costs"))})
    holdout = [r for r in rows if r["eligible_declared_holdout"]]
    metrics = {arm: _metrics(holdout, arm) for arm in ARMS}
    costed = [r for r in holdout if r["costs"]["minutes_saved"] is not None]
    installations = observations.get("installation_totals", {})
    if not isinstance(installations, dict):
        raise ValueError("installation_totals must be a site-to-arms object")
    if set(installations) - {r["site_id"] for r in rows}:
        raise ValueError("installation totals contain an unregistered site")
    allocation_complete = bool(holdout) and len(costed) == len(holdout)
    for site in {r["site_id"] for r in holdout}:
        entries = installations.get(site, {})
        if not isinstance(entries, dict) or set(entries) - set(ARMS):
            raise ValueError("site installation totals require baseline and assisted")
        for arm in ARMS:
            value = entries.get(arm)
            if value is None:
                allocation_complete = False
                continue
            # Reuse strict numeric validation (including booleans and infinities).
            check = empty_costs()
            check[arm]["installation"] = value
            summarize_costs(check)
            allocated = [(observed.get(r["case_id"], {}).get("costs") or {}).get(arm, {}).get("installation")
                         for r in holdout if r["site_id"] == site]
            if all(v is not None for v in allocated) and abs(sum(allocated) - value) > 1e-8:
                raise ValueError(f"{site}.{arm} installation allocation does not reconcile with cohort total")
    delta = sum(r["costs"]["minutes_saved"] for r in costed) if costed else None
    complete = bool(holdout) and all(r["reference_label"] != "UNRESOLVED"
                                    and "MISSING" not in r["decisions"].values() for r in holdout)
    b, a = metrics["baseline"], metrics["assisted"]
    comparable = complete and b["invalid_tasks"] > 0 and b["valid_tasks"] > 0
    joint = (a["false_accepts"] < b["false_accepts"] and a["false_holds_or_failures"] < b["false_holds_or_failures"]) if comparable else None
    groups = {}
    for family in sorted({r["task_family"] for r in holdout}):
        subset = [r for r in holdout if r["task_family"] == family]
        groups[family] = {arm: _metrics(subset, arm) for arm in ARMS}
    return {"schema": "bionexus.de-external-summary.v1", "study_id": plan["study_id"],
            "plan_sha256": plan_hash, "observations_sha256": digest(observations),
            "plan_anchor": "MATCHED" if expected_plan_sha256 else "NOT_PROVIDED",
            "registered_tasks": len(rows), "declared_holdout_tasks": len(holdout),
            "reported_sites": len({r["site_id"] for r in holdout}),
            "dataset_groups": len({r["dataset_sha256"] for r in holdout}),
            "excluded_tasks": len(rows) - len(holdout),
            "unresolved_reference_tasks": sum(r["reference_label"] == "UNRESOLVED" for r in holdout),
            "metrics": metrics, "by_task_family": groups,
            "joint_error_reduction_observed": joint, "fully_costed_tasks": len(costed),
            "joint_quality_and_time_gain_observed": (joint and delta > 0) if joint is not None and allocation_complete else None,
            "recorded_person_minutes_saved": delta,
            "installation_allocation": "RECONCILED_DECLARATIONS" if allocation_complete else "INCOMPLETE",
            "cohort_person_minutes_saved": delta if allocation_complete else None,
            "external_validation": "NOT_ESTABLISHED", "net_benefit": "NOT_ESTABLISHED",
            "scientific_authorization": "NONE", "cases": rows,
            "limitations": ["Independence, blinding, timestamps and time logs are declarations, not authenticated evidence.",
                            "Unknown references are retained, not relabeled; failure is a lost valid conclusion when reference is valid.",
                            "Missing outputs remain in registered denominators with worst-case rates.",
                            "Rates are descriptive, not confidence intervals; correlated tasks are not independent replicates.",
                            "Person-minutes exclude money, compute and scientific harm; no total economic-benefit claim.",
                            "A local plan hash is not public preregistration; external verification uses trust_evidence/validation_network."]}


def template() -> dict:
    return {"schema": PLAN_SCHEMA, "study_id": None, "intended_use": None, "source_sha256": None,
            "frozen_at": None, "developer_ids": [], "development_dataset_sha256": [], "cases": []}


def observation_template(plan: dict) -> dict:
    validate_plan(plan)
    return {"schema": OBS_SCHEMA, "plan_sha256": digest(plan),
            "installation_totals": {site: dict.fromkeys(ARMS) for site in sorted({c["site_id"] for c in plan["cases"]})},
            "cases": [{"case_id": c["case_id"], "reference_reviews": [], "arms": {}, "costs": empty_costs()}
                      for c in plan["cases"]]}


def _load(path: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f"nonfinite JSON: {value}")
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique, parse_constant=invalid)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    digest(value)  # Reject exponent overflow, including in otherwise unused fields.
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("template")
    init.add_argument("--plan", help="create blank observations for an already frozen plan")
    score = sub.add_parser("score")
    score.add_argument("plan")
    score.add_argument("observations")
    score.add_argument("--expected-plan-sha256")
    for command in (init, score):
        command.add_argument("--out", required=True, help="new JSON file, refuses overwrite")
    args = parser.parse_args(argv)
    try:
        if args.command == "template":
            result = observation_template(_load(args.plan)) if args.plan else template()
        else:
            result = score_study(_load(args.plan), _load(args.observations), expected_plan_sha256=args.expected_plan_sha256)
        with Path(args.out).open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(1, f"Invalid study: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
