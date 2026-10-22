"""Passive review of declared analysis-choice histories, never preregistration certification.

Order is the supplied event sequence, not a trusted clock. A hash chain binds bytes;
it cannot establish that every result exposure, actor or analysis was recorded.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import jsonschema

from bionexus.de.alternatives import _encode, _ref, _sha
from bionexus.de.conditions import _json, _table, verify_de_claim_conditions

HISTORY = "bionexus.de-selection-history.v1"
PLAN = "bionexus.de-selection-plan.v1"
SCHEMA = Path(__file__).parents[1] / "data/de-selection.v1.schema.json"


def _validate(value: Any, definition: str) -> None:
    schema = _json(SCHEMA.read_bytes())
    try:
        jsonschema.Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]}).validate(value)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Invalid selection {definition}: {exc.message}") from exc


def seal_selection_history(manifest: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Package a host export in memory; does NOT establish when events occurred.

    The caller must retain raw logs and an independent head if available. No file
    is mutated and no chat, data collection, execution or network call is started.
    """
    _validate(manifest, "manifest")
    previous = _sha(_encode(manifest))
    sealed = []
    for seq, event in enumerate(events, 1):
        _validate(event, "event")
        record = {**copy.deepcopy(event), "seq": seq, "previous_sha256": previous}
        previous = _sha(_encode(record))
        sealed.append({**record, "event_sha256": previous})
    return {"schema_version": HISTORY, "manifest": copy.deepcopy(manifest), "events": sealed, "head_sha256": previous}


def _verify_chain(history: dict[str, Any], expected_head: str | None) -> None:
    _validate(history, "history")
    events = [{k: v for k, v in e.items() if k not in ("seq", "previous_sha256", "event_sha256")}
              for e in history["events"]]
    if seal_selection_history(history["manifest"], events) != history:
        raise ValueError("Selection event chain is inconsistent")
    if expected_head is not None and expected_head != history["head_sha256"]:
        raise ValueError("Selection history differs from the caller's expected head")


def _load_plan(root: Path, ref: dict[str, str]) -> dict[str, Any]:
    _, data = _ref(root, ref)
    plan = _json(data)
    _validate(plan, "plan")
    ids = [c["claim_id"] for c in plan["claims"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Selection plan has duplicate claim IDs")
    return plan


def _matches_plan(root: Path, ref: dict[str, str], plan: dict[str, Any]) -> tuple[bool, dict[str, Any], Path]:
    path, data = _ref(root, ref)
    contract = _json(data)
    review = verify_de_claim_conditions(path)
    # Requiring valid contract syntax here is separate from requiring its scientific
    # conditions to pass: a negative result must remain in the branch inventory.
    _, model_data = _ref(path.parent, contract["artifacts"]["model"])
    model = _json(model_data)
    actual = dict(analysis=contract["analysis"], claims=contract["claims"],
                  metadata_sha256=contract["artifacts"]["metadata"]["sha256"],
                  model={k: model[k] for k in plan["model"]})
    expected = {k: plan[k] for k in actual}
    actual["claims"] = sorted(actual["claims"], key=lambda c: c["claim_id"])
    expected["claims"] = sorted(expected["claims"], key=lambda c: c["claim_id"])
    return actual == expected, review, path


def _datasets(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    datasets: dict[str, Any] = {}
    for item in manifest["datasets"]:
        did = item["dataset_id"]
        if did in datasets:
            raise ValueError("Duplicate dataset ID")
        path, data = _ref(root, item["manifest"])
        table = _table(data, str(path))
        if (set(table.columns) != {"sample_id", "donor_id"} or table.empty
                or not table["sample_id"].is_unique or table.eq("").any().any()):
            raise ValueError("Dataset manifest requires unique sample_id and nonempty donor_id")
        datasets[did] = {**item, "donors": set(table.donor_id), "samples": set(table.sample_id),
                         "pairs": set(zip(table.sample_id, table.donor_id)), "accesses": [], "evaluations": []}
    return datasets


def evaluate_selection_history(
    history_path: str | Path | None = None, *, expected_head: str | None = None,
    claim_contract: str | Path | None = None, alternative_plan: str | Path | None = None,
    de_table: Any = None, sample_metadata: Any = None,
) -> dict[str, Any]:
    """Review an explicitly scoped export; absent histories remain NOT_ASSESSED."""
    report: dict[str, Any] = {
        "schema_version": "bionexus.de-selection-review.v1", "status": "NOT_ASSESSED",
        "confirmatory_use": "NOT_ESTABLISHED", "selection_history_coverage": "NOT_ASSESSED",
        "capture_authentication": "NOT_ESTABLISHED", "preregistration": "NOT_ESTABLISHED",
        "scientific_authorization": "NONE", "selective_inference_correction": "NOT_PERFORMED",
        "branches": [], "findings": [], "holdouts": [], "synthetic": False,
        "verifier_sha256": _sha(Path(__file__).read_bytes()), "schema_sha256": _sha(SCHEMA.read_bytes()),
        "limitations": [
            "Recorded order and declared coverage are not authenticated observation history or preregistration.",
            "Missing logs cannot establish absence of selection; hashes cannot detect omissions followed by resealing without an external head.",
            "Branch counts are disclosure denominators, not independent tests or a P-value correction factor.",
            "Exploratory reporting remains possible subject to the original claim-condition review; no biological truth or misconduct is inferred.",
            "Plan matching covers structured claims, comparison, cohort bytes, formula, unit and effect measure; software, normalization, filtering and full search-space completeness are not verified by this contract.",
        ],
    }
    if history_path is None:
        if expected_head is not None:
            raise ValueError("An expected head requires a selection history")
        return report
    path = Path(history_path).resolve()
    data = path.read_bytes()
    history = _json(data)
    _verify_chain(history, expected_head)
    manifest = history["manifest"]
    root = path.parent
    datasets = _datasets(root, manifest)
    branches: dict[str, Any] = {}
    findings: list[dict[str, Any]] = report["findings"]
    seen_results: list[int] = []
    seen_views: list[int] = []
    selection = None
    alternative_events: list[dict[str, Any]] = []

    def finding(code: str, seq: int, branch: str | None = None) -> None:
        findings.append({"code": code, "seq": seq, "branch_id": branch})

    for event in history["events"]:
        seq, kind, p = event["seq"], event["kind"], event["payload"]
        if event["actor_id"] not in manifest["actor_ids"] or event["session_id"] not in manifest["session_ids"]:
            raise ValueError("Event actor or session falls outside declared capture scope")
        bid = p.get("branch_id")
        if kind == "branch_planned":
            if bid in branches:
                raise ValueError("Branch IDs cannot be reused")
            plan = _load_plan(root, p["plan"])
            branches[bid] = dict(branch_id=bid, role=p["role"], plan=plan, plan_sha256=p["plan"]["sha256"], plan_seq=seq,
                                 revisions=[], result=None, viewed=False, disposition="UNRESOLVED", reason=None)
        elif kind == "alternative_plan_frozen":
            _, plan_data = _ref(root, p["plan"])
            from bionexus.de.alternatives import _validate as validate_alternative
            validate_alternative(_json(plan_data), "plan")
            alternative_events.append({"sha256": p["plan"]["sha256"], "seq": seq,
                                       "prior_results": list(seen_results), "prior_views": list(seen_views)})
        elif kind in ("data_accessed", "holdout_evaluated"):
            did = p["dataset_id"]
            if did not in datasets:
                raise ValueError("Event names an undeclared dataset")
            ds = datasets[did]
            if kind == "holdout_evaluated":
                if ds["role"] != "holdout" or bid not in branches:
                    raise ValueError("Holdout evaluation requires a holdout and an existing branch")
                ds["evaluations"].append(seq)
                seen_results.append(seq)
                seen_views.append(seq)  # Returned validation feedback is an exposure.
            elif p["access"] == "outcomes":
                ds["accesses"].append(seq)
                seen_views.append(seq)
        else:
            if bid not in branches:
                raise ValueError("Event names a branch before its plan")
            branch = branches[bid]
            if branch["disposition"] != "UNRESOLVED":
                raise ValueError("A disposed branch cannot be revised, exposed or selected again")
            if kind == "plan_revised":
                if branch["result"] is not None or p["parent_sha256"] != branch["plan_sha256"]:
                    raise ValueError("Revision requires the current plan and no existing result; create a new branch after fitting")
                branch["revisions"].append({"seq": seq, "parent_sha256": p["parent_sha256"],
                                            "plan_sha256": p["plan"]["sha256"], "reason": p["reason"]})
                branch.update(plan=_load_plan(root, p["plan"]), plan_sha256=p["plan"]["sha256"], plan_seq=seq)
            elif kind == "result_available":
                if branch["result"] is not None:
                    raise ValueError("Repeated results require distinct branches")
                matches, review, contract_path = _matches_plan(root, p["contract"], branch["plan"])
                branch.update(result=p["contract"], condition_review=review, contract_path=contract_path, result_seq=seq)
                if not matches:
                    finding("UNRECORDED_PLAN_DEVIATION", seq, bid)
                seen_results.append(seq)
            elif kind == "result_viewed":
                if branch["result"] is None:
                    raise ValueError("A result cannot be viewed before it is available")
                branch["viewed"] = True
                seen_views.append(seq)
            elif kind == "branch_discarded":
                branch.update(disposition="DISCARDED", reason=p["reason"])
                if branch["viewed"] or p["decision_basis"] == "result_informed":
                    finding("RESULT_INFORMED_DISCARD", seq, bid)
            elif kind == "result_selected":
                if selection is not None or branch["result"] is None or branch["role"] != "candidate":
                    raise ValueError("History requires exactly one final result selection with an available result")
                branch.update(disposition="SELECTED", reason=p["reason"])
                selection = bid
                if p["decision_basis"] == "result_informed":
                    finding("RESULT_INFORMED_SELECTION", seq, bid)
        if kind in ("branch_planned", "plan_revised", "alternative_plan_frozen"):
            if seen_views:
                finding("CHOICE_AFTER_RECORDED_EXPOSURE", seq, bid)
            elif seen_results:
                finding("CHOICE_AFTER_RESULT_AVAILABLE", seq, bid)

    if selection is None:
        finding("FINAL_SELECTION_MISSING", len(history["events"]))
    expected_branches = set(manifest["branch_inventory"])
    report["missing_branch_ids"] = sorted(expected_branches - set(branches))
    report["undeclared_branch_ids"] = sorted(set(branches) - expected_branches)
    if set(branches) != expected_branches:
        finding("BRANCH_INVENTORY_INCOMPLETE", len(history["events"]))
    for branch in branches.values():
        if branch["disposition"] == "UNRESOLVED":
            finding("BRANCH_DISPOSITION_MISSING", branch["plan_seq"], branch["branch_id"])
    if selection is not None:
        chosen = branches[selection]
        contract_path = chosen["contract_path"]
        contract_data = contract_path.read_bytes()
        if claim_contract is not None and Path(claim_contract).read_bytes() != contract_data:
            raise ValueError("Selected contract is not the audited claim contract")
        # Bind the selected artifact to the actual audit inputs, retaining all
        # original numerical conditions without changing effect sizes or P values.
        review = verify_de_claim_conditions(contract_path, de_table=de_table, sample_metadata=sample_metadata)
        if review["contract_sha256"] != chosen["result"]["sha256"]:
            raise ValueError("Selected contract changed during review")
        report["selected_condition_review"] = review
        for claim in review["claims"]:
            if any(c["status"] != "SATISFIED" for c in claim["conditions"]
                   if c["condition_id"] in ("artifact_results", "artifact_metadata", "artifact_design", "artifact_model", "model_binding")):
                finding("SELECTED_ARTIFACT_BINDING_NOT_ESTABLISHED", chosen["result_seq"], selection)
        report["selected_contract_sha256"] = chosen["result"]["sha256"]
        contract = _json(contract_data)
        report["selected_result_sha256"] = contract["artifacts"]["results"]["sha256"]
        mp, md = _ref(contract_path.parent, contract["artifacts"]["metadata"])
        meta = _table(md, str(mp))
        columns = contract["metadata_columns"]
        pairs = set(zip(meta[columns["sample"]], meta[columns["donor"]]))
        discovery = [d for d in datasets.values() if d["role"] == "discovery"]
        if not discovery or not any(pairs == d["pairs"] for d in discovery):
            finding("DISCOVERY_MEMBERSHIP_NOT_BOUND", chosen["plan_seq"], selection)

    for did, ds in datasets.items():
        if ds["role"] != "holdout":
            continue
        peers = [d for other, d in datasets.items() if other != did and
                 (d["identity_namespace"] == ds["identity_namespace"] or d["manifest"]["sha256"] == ds["manifest"]["sha256"])]
        overlapping = [d for d in peers if ds["donors"] & d["donors"] or ds["samples"] & d["samples"]]
        reused = sorted(set(ds["evaluations"] + [e for d in overlapping for e in d["evaluations"]]))
        accesses = sorted(set(ds["accesses"] + [e for d in overlapping for e in d["accesses"]]))
        issues = []
        if any(d["role"] == "discovery" for d in overlapping):
            issues.append("DISCOVERY_HOLDOUT_OVERLAP")
        if not any(d["role"] == "discovery" and d["identity_namespace"] == ds["identity_namespace"] for d in datasets.values()):
            issues.append("HOLDOUT_IDENTITY_NOT_COMPARABLE")
        if len(reused) > 1:
            issues.append("HOLDOUT_REUSED")
        if accesses:
            issues.append("HOLDOUT_OUTCOMES_EXPOSED")
            if not reused or accesses[0] < reused[0]:
                issues.append("HOLDOUT_EXPOSED_BEFORE_EVALUATION")
        if not ds["evaluations"]:
            issues.append("HOLDOUT_NOT_EVALUATED")
        report["holdouts"].append({"dataset_id": did, "issues": issues, "evaluation_events": reused,
                                    "outcome_access_events": accesses, "independence": "NOT_ESTABLISHED"})
        for code in issues:
            finding(code, (accesses or reused or [0])[0])

    report["alternative_plan_timing"] = "NOT_ASSESSED"
    if alternative_plan is not None:
        alternative_data = Path(alternative_plan).read_bytes()
        digest = _sha(alternative_data)
        if _json(alternative_data).get("claim_contract_sha256") != report.get("selected_contract_sha256"):
            raise ValueError("Alternative plan and selected result must bind the same claim contract")
        matching = [e for e in alternative_events if e["sha256"] == digest]
        if len(matching) != 1:
            finding("ALTERNATIVE_PLAN_HISTORY_MISSING_OR_AMBIGUOUS", 0)
        else:
            e = matching[0]
            report["alternative_plan_timing"] = ("AFTER_RECORDED_EXPOSURE" if e["prior_views"] else
                                                  "AFTER_RESULT_AVAILABLE" if e["prior_results"] else "BEFORE_RECORDED_RESULTS")

    complete_declared = (manifest["coverage"] == "complete_declared" and not manifest["gaps"]
                         and manifest["capture_mode"] == "prospective")
    codes = {f["code"] for f in findings}
    adverse_codes = {"CHOICE_AFTER_RECORDED_EXPOSURE", "RESULT_INFORMED_DISCARD", "RESULT_INFORMED_SELECTION",
                     "UNRECORDED_PLAN_DEVIATION", "DISCOVERY_HOLDOUT_OVERLAP", "HOLDOUT_REUSED", "HOLDOUT_EXPOSED_BEFORE_EVALUATION"}
    # Post-hoc sensitivity analyses do not retroactively turn a prespecified
    # primary result into an adaptively selected result. They remain disclosed.
    adverse = [f for f in findings if f["code"] in adverse_codes
               and (f["branch_id"] is None and f["code"] != "CHOICE_AFTER_RECORDED_EXPOSURE"
                    or branches.get(f["branch_id"], {}).get("role") == "candidate")]
    incomplete_codes = codes - adverse_codes - {"HOLDOUT_OUTCOMES_EXPOSED"}
    report["status"] = ("SELECTION_DEPENDENCE_RECORDED" if adverse else
                        "HISTORY_INCOMPLETE" if incomplete_codes or not complete_declared else "PRE_RESULT_PLAN_RECORDED")
    report["confirmatory_use"] = "EXPLORATORY_ONLY_FOR_RECORDED_SELECTION" if adverse else "NOT_ESTABLISHED"
    report["claims"] = [{"claim_id": c["claim"]["claim_id"], "condition_status": c["status"],
                          "selection_status": report["status"], "confirmatory_use": report["confirmatory_use"]}
                         for c in report.get("selected_condition_review", {}).get("claims", [])]
    report["selection_history_coverage"] = "DECLARED_COMPLETE_UNAUTHENTICATED" if complete_declared else "PARTIAL_OR_RETROSPECTIVE"
    report.update(history_sha256=_sha(data), head_sha256=history["head_sha256"],
                  integrity="CONSISTENT_WITH_EXPECTED_HEAD" if expected_head is not None else "INTERNALLY_CONSISTENT",
                  scope=manifest, synthetic=manifest["synthetic"], event_count=len(history["events"]),
                  declared_branch_count=len(expected_branches), recorded_branch_count=len(branches))
    for b in branches.values():
        report["branches"].append({k: v for k, v in b.items() if k not in ("plan", "condition_review", "contract_path")})
    report["disclosure_counts"] = {state.lower(): sum(b["disposition"] == state for b in branches.values())
                                   for state in ("SELECTED", "DISCARDED", "UNRESOLVED")}
    return report


def render_selection_history(report: dict[str, Any]) -> str:
    lines = ["### 分析选择历史", "", f"历史判断：{report['status']}；确认性用途：{report['confirmatory_use']}。",
             f"历史覆盖：{report['selection_history_coverage']}；预注册：NOT_ESTABLISHED。",
             "数值结果与选择历史分别评估；探索性结果可以如实报告。"]
    for branch in report["branches"]:
        lines.append(f"- 分支 {branch['branch_id']}：{branch['disposition']}；原因：{branch['reason'] or '未记录'}")
    for bid in report.get("missing_branch_ids", []):
        lines.append(f"- 分支 {bid}：清单中存在，但未提供事件。")
    for finding in report["findings"]:
        lines.append(f"- 事件 {finding['seq']}：{finding['code']}（{finding['branch_id'] or '研究范围'}）")
    lines += ["", "日志一致性不证明捕获完整或真实预注册；不按尝试次数自动校正 P 值。",
              "修复：披露计划变更、全部分支和暴露历史；确认性用途需另行评估独立、未暴露的验证及有效推断方案。"]
    return "\n".join(lines) + "\n"
