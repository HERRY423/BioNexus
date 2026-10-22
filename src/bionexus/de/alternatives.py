"""Passive, frozen-plan DE sensitivity review over artifact-bound reruns.

The host performs the analyses. This module verifies the declared perturbation,
keeps every planned branch, and reports changes without a vote or truth score.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PureWindowsPath
from typing import Any

import jsonschema
import numpy as np
import pandas as pd

from bionexus.de.conditions import SAT, _json, _table, verify_de_claim_conditions

PLAN = "bionexus.de-alternative-plan.v1"
RUN = "bionexus.de-alternative-run.v1"
REVIEW = "bionexus.de-alternative-review.v1"
STRUCTURAL = ("artifact_results", "artifact_metadata", "artifact_design", "artifact_model", "model_binding",
              "sample_alignment", "design_encoding", "contrast_identity", "contrast_estimability", "model_rank",
              "statistical_unit", "result_identity")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _encode(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _validate(value: Any, definition: str) -> None:
    schema = _json((Path(__file__).parents[1] / "data/de-alternatives.v1.schema.json").read_bytes())
    try:
        jsonschema.Draft202012Validator({"$ref": f"#/$defs/{definition}", "$defs": schema["$defs"]}).validate(value)
    except jsonschema.ValidationError as exc:
        raise ValueError(f"Invalid {definition}: {exc.message}") from exc


def _ref(root: Path, ref: dict[str, str]) -> tuple[Path, bytes]:
    path = (root / ref["path"]).resolve()
    if (PureWindowsPath(ref["path"]).drive or "\\" in ref["path"] or Path(ref["path"]).is_absolute()
            or not path.is_relative_to(root.resolve())):
        raise ValueError("Artifact reference escapes its package directory")
    data = path.read_bytes()
    if _sha(data) != ref["sha256"]:
        raise ValueError(f"Artifact digest mismatch: {ref['path']}")
    return path, data


def _make_ref(root: Path, path: Path) -> dict[str, str]:
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Place the input package inside the plan directory before freezing it")
    return {"path": path.relative_to(root.resolve()).as_posix(), "sha256": _sha(path.read_bytes())}


def _load_run(root: Path, ref: dict[str, str]) -> dict[str, Any]:
    path, data = _ref(root, ref)
    record = _json(data)
    _validate(record, "run")
    contract_path, raw_contract = _ref(path.parent, record["contract"])
    contract = _json(raw_contract)
    review = verify_de_claim_conditions(contract_path)
    if review["contract_sha256"] != record["contract"]["sha256"]:
        raise ValueError("Contract changed during verification")
    artifacts = contract["artifacts"]
    tables = {}
    for role in ("metadata", "results", "design"):
        table_path, table_bytes = _ref(contract_path.parent, artifacts[role])
        tables[role] = _table(table_bytes, str(table_path))
    _, model_bytes = _ref(contract_path.parent, artifacts["model"])
    model = _json(model_bytes)
    for role in ("counts", "cells"):
        table_path, table_bytes = _ref(path.parent, record[role])
        tables[role] = _table(table_bytes, str(table_path))
    counts, cells, meta = tables["counts"], tables["cells"], tables["metadata"]
    sample = contract["metadata_columns"]["sample"]
    if ("sample_id" not in counts or counts.empty
            or not counts["sample_id"].is_unique or counts["sample_id"].eq("").any()
            or sample not in meta or not meta[sample].is_unique
            or set(counts["sample_id"]) != set(meta[sample])):
        raise ValueError("Count rows must map bijectively to model sample IDs")
    matrix = counts.drop(columns="sample_id").to_numpy(dtype=float)
    if (not np.isfinite(matrix).all() or np.any(matrix < 0) or np.any(matrix != np.floor(matrix))
            or np.any(matrix > 2**53 - 1)):
        raise ValueError("Counts must be finite, nonnegative exact integers within float64 exact range")
    if (set(cells.columns) != {"cell_id", "sample_id"} or cells.empty or cells.eq("").any().any()
            or not cells["cell_id"].is_unique or set(cells["sample_id"]) != set(meta[sample])):
        raise ValueError("Cell membership requires unique cell IDs and exactly the modeled samples")
    return dict(record=record, contract=contract, contract_path=contract_path, review=review, model=model, **tables)


def _checks(run: dict[str, Any], claim_id: str) -> dict[str, Any]:
    item = next(c for c in run["review"]["claims"] if c["claim"]["claim_id"] == claim_id)
    return {c["condition_id"]: c for c in item["conditions"]}


def _numbers(run: dict[str, Any], claim: dict[str, Any]) -> dict[str, float] | None:
    table, analysis = run["results"], run["contract"]["analysis"]
    selector = {"gene": claim["gene"], **analysis}
    if not set(selector) <= set(table.columns):
        return None
    mask = np.ones(len(table), dtype=bool)
    for key, value in selector.items():
        mask &= table[key].to_numpy() == value
    rows = table.loc[mask]
    if len(rows) != 1:
        return None
    try:
        result = {key: float(rows.iloc[0][key]) for key in
                  ("log2_fold_change", "padj", "ci_lower", "ci_upper", "ci_level")}
    except (KeyError, ValueError, TypeError, OverflowError):
        return None
    if (not all(np.isfinite(v) for v in result.values()) or not 0 <= result["padj"] <= 1
            or not 0 < result["ci_level"] < 1
            or not result["ci_lower"] <= result["log2_fold_change"] <= result["ci_upper"]):
        return None
    return result


def create_alternative_plan(baseline: str | Path, output: str | Path, *,
                            specifications: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Freeze all donor omissions plus explicitly justified method/filter alternatives.

    Output is exclusive-create. The digest binds content, not when results were
    first seen; this API never calls a plan preregistered or scientifically approved.
    """
    output, baseline = Path(output).resolve(), Path(baseline).resolve()
    base_ref = _make_ref(output.parent, baseline)
    base = _load_run(output.parent, base_ref)
    contract = base["contract"]
    if any(c["scope"] not in ("table_observation", "cohort_association") for c in contract["claims"]):
        raise ValueError("Sensitivity adapter supports table/cohort claims only")
    for claim in contract["claims"]:
        checks = _checks(base, claim["claim_id"])
        if (any(checks[k]["status"] != SAT for k in STRUCTURAL) or _numbers(base, claim) is None
                or claim["gene"] not in base["counts"].columns):
            raise ValueError("Baseline needs complete, structurally valid artifacts and finite effect/interval/padj")
    donor = contract["metadata_columns"]["donor"]
    donors = sorted(set(base["metadata"][donor]))
    specs = [dict(spec_id=f"lodo-{i:03d}", kind="leave_one_donor_out", donor_id=d,
                  rationale="Assess influence after removing every modeled observation of this donor.")
             for i, d in enumerate(donors, 1)]
    specs.extend(specifications or [])
    plan = dict(schema_version=PLAN, baseline=base_ref, specifications=specs,
                synthetic=base["record"]["synthetic"],
                claim_contract_sha256=base["record"]["contract"]["sha256"],
                selection_timing="NOT_VERIFIED", scientific_admissibility="REQUIRES_REVIEW")
    _validate(plan, "plan")
    _validate_specs(plan, base)
    with output.open("xb") as stream:
        stream.write(_encode(plan))
    return plan


def _validate_specs(plan: dict[str, Any], baseline: dict[str, Any]) -> None:
    specs = plan["specifications"]
    ids = [s["spec_id"] for s in specs]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate specification IDs")
    keys = []
    for spec in specs:
        payload = {k: v for k, v in spec.items() if k not in ("spec_id", "rationale")}
        keys.append(_encode(payload))
        if spec["kind"] == "method" and spec["analysis_spec"] == baseline["record"]["analysis_spec"]:
            raise ValueError("Method alternative duplicates baseline settings")
    if len(set(keys)) != len(keys):
        raise ValueError("Redundant specifications cannot multiply evidence")
    donor = baseline["contract"]["metadata_columns"]["donor"]
    expected = set(baseline["metadata"][donor])
    actual = [s["donor_id"] for s in specs if s["kind"] == "leave_one_donor_out"]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("Plan must retain exactly one omission for every baseline donor")
    if plan["claim_contract_sha256"] != baseline["record"]["contract"]["sha256"]:
        raise ValueError("Frozen baseline claim differs from the plan")
    if plan["synthetic"] != baseline["record"]["synthetic"]:
        raise ValueError("Synthetic evidence label differs from baseline")


def _frame_equal(left: pd.DataFrame, right: pd.DataFrame, key: str) -> bool:
    if set(left.columns) != set(right.columns) or not left[key].is_unique or not right[key].is_unique:
        return False
    if set(left[key]) != set(right[key]):
        return False
    return left.set_index(key).sort_index().sort_index(axis=1).equals(
        right.set_index(key).sort_index().sort_index(axis=1))


def _effective_specification(run: dict[str, Any]) -> str:
    """Deduplicate effective inputs/settings, even when filter parameters differ."""
    normalized = {}
    for role, key in (("counts", "sample_id"), ("cells", "cell_id"), ("design", "sample_id")):
        frame = run[role].set_index(key).sort_index().sort_index(axis=1)
        if role in ("counts", "design"):
            frame = frame.astype(float)
        normalized[role] = frame.to_dict(orient="split")
    return _sha(_encode({"inputs": normalized, "analysis_spec": run["record"]["analysis_spec"]}))


def _compatible(base: dict[str, Any], alt: dict[str, Any], spec: dict[str, Any]) -> tuple[str, list[str], dict[str, Any]]:
    """Verify only the declared alteration; semantic equivalence remains bounded."""
    bc, ac = base["contract"], alt["contract"]
    if (bc["analysis"] != ac["analysis"]
            or {c["claim_id"]: c for c in bc["claims"]} != {c["claim_id"]: c for c in ac["claims"]}
            or bc["metadata_columns"] != ac["metadata_columns"]):
        return "QUESTION_CHANGED", ["Gene, cell label, ordered comparison, scope or threshold changed."], {}
    bm, am = base["model"], alt["model"]
    for key in ("formula", "effect_measure", "statistical_unit"):
        if bm.get(key) != am.get(key):
            return "QUESTION_CHANGED", [f"Model target/encoding changed: {key}."], {}
    # Dropping a paired donor may require dropping its now-empty dummy column or
    # choosing another donor reference. The condition and other nuisance columns
    # must stay intact. The condition verifier validates the remaining encoding.
    removed = set(bm["design_columns"]) - set(am["design_columns"])
    donor_column = bc["metadata_columns"]["donor"]
    allowed = spec["kind"] == "leave_one_donor_out" and all(
        bm["encodings"][name].get("column") == donor_column for name in removed)
    encodings_match = (set(am["design_columns"]) <= set(bm["design_columns"])
                       and (not removed or allowed)
                       and am["encodings"] == {k: v for k, v in bm["encodings"].items() if k not in removed}
                       and am["contrast"] == {k: v for k, v in bm["contrast"].items() if k not in removed})
    if not encodings_match:
        return "QUESTION_CHANGED", ["Condition/adjustment encoding or contrast changed."], {}
    if base["record"]["synthetic"] != alt["record"]["synthetic"]:
        return "INVALID_ARTIFACTS", ["Synthetic evidence label changed."], {}
    expected_analysis = spec["analysis_spec"] if spec["kind"] == "method" else base["record"]["analysis_spec"]
    if alt["record"]["analysis_spec"] != expected_analysis:
        return "UNPLANNED_CHANGE", ["Returned method/settings differ from the frozen specification."], {}
    cols = bc["metadata_columns"]
    sid, donor = cols["sample"], cols["donor"]
    expected_meta = base["metadata"]
    if spec["kind"] == "leave_one_donor_out":
        expected_meta = expected_meta.loc[expected_meta[donor] != spec["donor_id"]]
    if not _frame_equal(expected_meta, alt["metadata"], sid):
        return "UNPLANNED_CHANGE", ["Retained sample/donor/covariate records differ from the specified perturbation."], {}
    samples = set(expected_meta[sid])
    expected_cells = base["cells"].loc[base["cells"]["sample_id"].isin(samples)]
    if not _frame_equal(expected_cells, alt["cells"], "cell_id"):
        return "QUESTION_CHANGED", ["Cell membership changed beyond the planned donor omission."], {}
    expected_design = base["design"].loc[base["design"]["sample_id"].isin(samples), ["sample_id", *am["design_columns"]]]
    # Numeric comparisons accept equivalent CSV encodings, but never row-position alignment.
    def numeric(frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        for col in result.columns:
            if col != "sample_id":
                result[col] = result[col].astype(float)
        return result
    if not _frame_equal(numeric(expected_design), numeric(alt["design"]), "sample_id"):
        return "UNPLANNED_CHANGE", ["Actual design values changed beyond the requested row subset."], {}
    counts = base["counts"].loc[base["counts"]["sample_id"].isin(samples)]
    genes = [c for c in counts.columns if c != "sample_id"]
    if spec["kind"] == "gene_filter":
        values = counts[genes].to_numpy(dtype=float)
        genes = [gene for gene, retain in zip(genes, (values >= spec["min_count"]).sum(axis=0) >= spec["min_samples"]) if retain]
    expected_counts = counts[["sample_id", *genes]]
    info = {"retained_samples": len(samples), "retained_donors": int(expected_meta[donor].nunique()),
            "baseline_genes": len(base["counts"].columns) - 1, "retained_genes": len(genes),
            "estimand_relation": "DONOR_INFLUENCE_DIAGNOSTIC" if spec["kind"] == "leave_one_donor_out"
            else "SAME_DECLARED_TARGET_WITHIN_ADAPTER",
            "input_equivalence": "SUPPLIED_COUNTS_AND_MEMBERSHIP_CHECKED",
            "fit_consumption_of_inputs": "NOT_AUTHENTICATED"}
    if not _frame_equal(numeric(expected_counts), numeric(alt["counts"]), "sample_id"):
        return "UNPLANNED_CHANGE", ["Retained gene universe or count values differ from the planned input."], info
    if spec["kind"] == "gene_filter" and len(genes) == len(base["counts"].columns) - 1:
        return "REDUNDANT_SPECIFICATION", ["Filter removes no genes; this is not additional evidence."], info
    return "COMPARABLE", [], info


def _changes(base: dict[str, float], alt: dict[str, float], alpha: float) -> dict[str, Any]:
    b, a = base["log2_fold_change"], alt["log2_fold_change"]
    same_level = base["ci_level"] == alt["ci_level"]
    width_b, width_a = base["ci_upper"] - base["ci_lower"], alt["ci_upper"] - alt["ci_lower"]
    if not all(np.isfinite(v) for v in (a - b, width_b, width_a, width_a - width_b)):
        raise ValueError("Effect/interval differences exceed the finite numeric range")
    return dict(effect_delta=a - b, direction_reversed=(b < 0 < a or a < 0 < b), direction_at_zero=a == 0 and b != 0,
                significance_lost=base["padj"] <= alpha < alt["padj"],
                significance_gained=alt["padj"] <= alpha < base["padj"],
                interval_crosses_zero=alt["ci_lower"] <= 0 <= alt["ci_upper"],
                interval_newly_crosses_zero=(alt["ci_lower"] <= 0 <= alt["ci_upper"]
                                             and not base["ci_lower"] <= 0 <= base["ci_upper"]),
                interval_level_changed=not same_level,
                interval_widened=(width_a > width_b) if same_level else None,
                interval_width_change=(width_a - width_b) if same_level else None,
                power_change="NOT_ESTIMATED", heterogeneity="NOT_TESTED")


def evaluate_alternative_plan(plan_path: str | Path, results_path: str | Path | None = None,
                              *, claim_contract: str | Path | None = None,
                              de_table: Any = None, sample_metadata: Any = None) -> dict[str, Any]:
    """Review every frozen slot. Incomplete/invalid runs never disappear from coverage."""
    plan_path = Path(plan_path).resolve()
    plan_bytes = plan_path.read_bytes()
    plan = _json(plan_bytes)
    _validate(plan, "plan")
    base = _load_run(plan_path.parent, plan["baseline"])
    _validate_specs(plan, base)
    if claim_contract is not None and _sha(Path(claim_contract).read_bytes()) != plan["claim_contract_sha256"]:
        raise ValueError("Audit claim contract differs from the sensitivity baseline")
    if de_table is not None or sample_metadata is not None:
        bound = verify_de_claim_conditions(base["contract_path"], de_table=de_table, sample_metadata=sample_metadata)
        if any(c["status"] != SAT for c in bound["claims"][0]["conditions"]
               if c["condition_id"] in ("artifact_results", "artifact_metadata")):
            raise ValueError("Audit inputs differ from the sensitivity baseline")
    results: dict[str, Any] = {"runs": []}
    results_root = plan_path.parent
    results_digest = None
    if results_path is not None:
        result_file = Path(results_path).resolve()
        result_bytes = result_file.read_bytes()
        results = _json(result_bytes)
        _validate(results, "results")
        results_root, results_digest = result_file.parent, _sha(result_bytes)
        if results["plan_sha256"] != _sha(plan_bytes):
            raise ValueError("Results belong to a different frozen plan")
    ids = [r["spec_id"] for r in results["runs"]]
    if len(ids) != len(set(ids)) or not set(ids) <= {s["spec_id"] for s in plan["specifications"]}:
        raise ValueError("Duplicate or unplanned result slots")
    supplied = {r["spec_id"]: r for r in results["runs"]}
    branches = []
    seen_records: set[str] = set()
    seen_effective: set[str] = set()
    for spec in plan["specifications"]:
        row: dict[str, Any] = dict(specification=spec, status="MISSING", reasons=["No result supplied."], claims=[], comparison={})
        entry = supplied.get(spec["spec_id"])
        if entry is None or entry["status"] in ("pending", "failed"):
            if entry is not None:
                row.update(status=entry["status"].upper(), reasons=[entry["reason"]])
            branches.append(row)
            continue
        try:
            record_ref = entry["record"]
            if record_ref["sha256"] in seen_records:
                raise ValueError("One run record was reused for multiple specifications")
            seen_records.add(record_ref["sha256"])
            alt = _load_run(results_root, record_ref)
            status, reasons, comparison = _compatible(base, alt, spec)
            if status == "COMPARABLE":
                signature = _effective_specification(alt)
                if signature in seen_effective:
                    status, reasons = "REDUNDANT_SPECIFICATION", ["Different specification labels produced the same input/settings; retain but do not count twice."]
                seen_effective.add(signature)
            row.update(status=status, reasons=reasons, comparison=comparison, record_ref=record_ref,
                       condition_review=alt["review"])
            if status == "COMPARABLE":
                for claim in base["contract"]["claims"]:
                    checks = _checks(alt, claim["claim_id"])
                    invalid = [k for k in STRUCTURAL if checks[k]["status"] != SAT]
                    stats = _numbers(alt, claim)
                    baseline_stats = _numbers(base, claim)
                    baseline_checks = _checks(base, claim["claim_id"])
                    baseline_invalid = [k for k in STRUCTURAL if baseline_checks[k]["status"] != SAT]
                    if baseline_invalid or baseline_stats is None:
                        state = "BASELINE_NOT_ASSESSED"
                    elif checks["contrast_estimability"]["status"] == "UNSATISFIED":
                        state = "NOT_ESTIMABLE"
                    elif claim["gene"] not in alt["counts"].columns:
                        state = "TARGET_FILTERED_OUT"
                    elif invalid:
                        state = "INVALID_DESIGN" if any(checks[k]["status"] in ("UNSATISFIED", "CONFLICT") for k in invalid) else "NOT_ASSESSED"
                    elif stats is None:
                        state = "NOT_ASSESSED"
                    else:
                        state = "COMPARED"
                    row["claims"].append(dict(claim_id=claim["claim_id"], status=state,
                                              unmet_conditions=invalid, baseline_unmet_conditions=baseline_invalid,
                                              baseline=baseline_stats, alternative=stats,
                                              changes=_changes(baseline_stats, stats, claim["alpha"])
                                              if state == "COMPARED" and baseline_stats is not None and stats is not None else {}))
        except FileNotFoundError as exc:
            row.update(status="MISSING_ARTIFACTS", reasons=[str(exc)], claims=[])
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
            row.update(status="INVALID_ARTIFACTS", reasons=[str(exc)], claims=[])
        branches.append(row)
    summaries = []
    for claim in base["contract"]["claims"]:
        comparisons = []
        unresolved = []
        events = []
        for branch in branches:
            result = next((r for r in branch["claims"] if r["claim_id"] == claim["claim_id"]), None)
            if result is None or result["status"] != "COMPARED":
                unresolved.append(dict(spec_id=branch["specification"]["spec_id"],
                                       status=result["status"] if result else branch["status"]))
                continue
            changes = result["changes"]
            comparisons.append(result)
            tags = [key for key in ("direction_reversed", "direction_at_zero", "significance_lost", "significance_gained",
                                    "interval_newly_crosses_zero", "interval_widened", "interval_level_changed") if changes[key]]
            if tags:
                events.append(dict(spec_id=branch["specification"]["spec_id"], kind=branch["specification"]["kind"],
                                   donor_id=branch["specification"].get("donor_id"), observations=tags))
        direction_changes = [e for e in events if "direction_reversed" in e["observations"] or "direction_at_zero" in e["observations"]]
        status = ("DIRECTION_SENSITIVE" if direction_changes else "INCOMPLETE" if unresolved
                  else "THRESHOLD_OR_UNCERTAINTY_SENSITIVE" if events else "DIRECTION_AND_THRESHOLDS_RETAINED_WITHIN_PLAN")
        summaries.append(dict(claim_id=claim["claim_id"], status=status, planned=len(branches), compared=len(comparisons),
                              baseline_result=_numbers(base, claim),
                              baseline_condition_status=next(c["status"] for c in base["review"]["claims"]
                                                             if c["claim"]["claim_id"] == claim["claim_id"]),
                              complete=len(unresolved) == 0, unresolved=unresolved, dependencies=events,
                              effect_range=[min(r["alternative"]["log2_fold_change"] for r in comparisons),
                                            max(r["alternative"]["log2_fold_change"] for r in comparisons)] if comparisons else None,
                              interpretation="Direction changes are descriptive sensitivity. Loss of significance is not refutation; power and heterogeneity were not tested."))
    return dict(schema_version=REVIEW, plan_sha256=_sha(plan_bytes), results_sha256=results_digest,
                verifier_sha256=_sha(Path(__file__).read_bytes()), synthetic=plan["synthetic"],
                schema_sha256=_sha((Path(__file__).parents[1] / "data/de-alternatives.v1.schema.json").read_bytes()),
                baseline_condition_review=base["review"], branches=branches, claims=summaries,
                complete=all(c["complete"] for c in summaries), scientific_authorization="NONE",
                analysis_execution_verification="NOT_PERFORMED", scientific_admissibility="REQUIRES_REVIEW",
                selection_timing="NOT_VERIFIED", joint_inference="NOT_PERFORMED",
                limitations=["Results describe only the frozen specifications; no robustness probability or majority vote.",
                             "Shared samples are not independent replications. No p-values are pooled.",
                             "LODO perturbs the analyzed cohort and diagnoses donor influence, not identical empirical estimands.",
                             "Record consistency does not prove the exported counts/cells were used in a fit.",
                             "Statistical validity, model adequacy and the declared common scientific target still need review.",
                             "Permutation/null testing is unsupported without a validated exchangeability adapter."])


def render_alternatives(report: dict[str, Any]) -> str:
    lines = ["## 合理替代分析下的结论变化", "", "范围：冻结方案内的产物比较；不证明普遍稳健性或科学正确性。", ""]
    if report["synthetic"]:
        lines += ["**合成工程示例，不得计入真实研究或实验室收益。**", ""]
    for claim in report["claims"]:
        lines += [f"### {claim['claim_id']} — {claim['status']}",
                  f"已比较 {claim['compared']} / 计划 {claim['planned']}；完整：{claim['complete']}。",
                  f"原声明必要条件：{claim['baseline_condition_status']}（与敏感性判定分开）。", ""]
        for event in claim["dependencies"]:
            label = f"剔除供体 {event['donor_id']}" if event["donor_id"] else event["spec_id"]
            labels = {"direction_reversed": "方向翻转", "direction_at_zero": "点估计变为零",
                      "significance_lost": "失去显著性", "significance_gained": "达到显著性阈值",
                      "interval_newly_crosses_zero": "区间开始包含零", "interval_widened": "区间变宽",
                      "interval_level_changed": "置信水平改变"}
            lines.append(f"- {label}：{', '.join(labels[k] for k in event['observations'])}。")
        for pending in claim["unresolved"]:
            lines.append(f"- 未完成可比检查 {pending['spec_id']}：{pending['status']}。")
        lines += ["", "失去显著性不等于结论被推翻；功效变化及供体异质性均未检验。", ""]
        lines += ["| 分支 | log2 效应 | 置信区间 | 调整 P 值 | 可比状态 |",
                  "| --- | --- | --- | --- | --- |"]
        baseline_written = False
        for branch in report["branches"]:
            result = next((r for r in branch["claims"] if r["claim_id"] == claim["claim_id"]), None)
            if result is None:
                continue
            for name, stats in [("baseline", result["baseline"]), (branch["specification"]["spec_id"], result["alternative"])]:
                if stats is None or (name == "baseline" and baseline_written):
                    continue
                state = "原分析" if name == "baseline" else result["status"]
                lines.append(f"| {name} | {stats['log2_fold_change']:.4g} | "
                             f"[{stats['ci_lower']:.4g}, {stats['ci_upper']:.4g}] ({stats['ci_level']:.1%}) | "
                             f"{stats['padj']:.4g} | {state} |")
                if name == "baseline":
                    baseline_written = True
        lines.append("")
    lines += ["| 分支 | 状态 | 说明 |", "| --- | --- | --- |"]
    for branch in report["branches"]:
        explanation = "; ".join(branch["reasons"]).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {branch['specification']['spec_id']} | {branch['status']} | {explanation} |")
    return "\n".join(lines)
