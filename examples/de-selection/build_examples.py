"""Create explicit synthetic/counterfactual histories; NEVER observed research logs.

Usage: python examples/de-selection/build_examples.py --out NEW_DIRECTORY
This does not fit DE models or prove that any plan preceded real research results.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path

import pandas as pd

from bionexus.de.selection import evaluate_selection_history, render_selection_history, seal_selection_history


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def ref(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def event(kind, **payload):
    return dict(actor_id="synthetic-researcher", session_id="synthetic-session", kind=kind, payload=payload)


def build(out):
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parents[1] / "de-claim-conditions/valid"
    cases = ("pre_result", "result_selected", "partial_capture", "holdout_reuse", "posthoc_sensitivity")
    rows = []
    for name in cases:
        root = out / name
        root.mkdir()
        for filename in ("contract.json", "model.json", "metadata.csv", "design.csv", "results.csv"):
            shutil.copyfile(source / filename, root / filename)
        contract = json.loads((root / "contract.json").read_text(encoding="utf-8"))
        model = json.loads((root / "model.json").read_text(encoding="utf-8"))
        plan = dict(schema_version="bionexus.de-selection-plan.v1", analysis=contract["analysis"], claims=contract["claims"],
                    metadata_sha256=contract["artifacts"]["metadata"]["sha256"],
                    model={k: model[k] for k in ("formula", "statistical_unit", "effect_measure")},
                    selection_rule="report_all_planned_claims")
        write(root / "plan.json", plan)
        meta = pd.read_csv(root / "metadata.csv", dtype=str)
        cols = contract["metadata_columns"]
        pd.DataFrame(dict(sample_id=meta[cols["sample"]], donor_id=meta[cols["donor"]])).to_csv(root / "members.csv", index=False)
        manifest = dict(scope_id="synthetic-same-final-result", actor_ids=["synthetic-researcher"],
                        session_ids=["synthetic-session"], branch_inventory=["primary"],
                        capture_mode="prospective", coverage="complete_declared", gaps=[], synthetic=True,
                        datasets=[dict(dataset_id="discovery", role="discovery", identity_namespace="synthetic-study",
                                       manifest=ref(root, root / "members.csv"))])

        def planned(bid, role="candidate"):
            return event("branch_planned", branch_id=bid, role=role, plan=ref(root, root / "plan.json"))

        def available(bid):
            return event("result_available", branch_id=bid, contract=ref(root, root / "contract.json"))

        events = [planned("primary"), available("primary"), event("result_viewed", branch_id="primary"),
                  event("result_selected", branch_id="primary", decision_basis="predeclared", reason="Report planned analysis")]
        if name == "result_selected":
            manifest["branch_inventory"].append("screen")
            # The history contrast is synthetic; even identical output bytes do
            # not make these attempts independent tests or evidence of execution.
            events[:0] = [planned("screen"), available("screen"), event("result_viewed", branch_id="screen"),
                          event("branch_discarded", branch_id="screen", decision_basis="result_informed", reason="Prior inspected branch not selected")]
            events[-1]["payload"]["decision_basis"] = "result_informed"
        elif name == "partial_capture":
            manifest.update(capture_mode="retrospective", coverage="partial", gaps=["Earlier notebook and agent sessions unavailable"])
            manifest["branch_inventory"].append("unobserved")
        elif name == "holdout_reuse":
            pd.DataFrame(dict(sample_id=["hs1"], donor_id=["hd1"])).to_csv(root / "holdout.csv", index=False)
            manifest["datasets"].append(dict(dataset_id="holdout", role="holdout", identity_namespace="synthetic-study",
                                             manifest=ref(root, root / "holdout.csv")))
            manifest["datasets"].append({**copy.deepcopy(manifest["datasets"][-1]), "dataset_id": "renamed-holdout"})
            events[3:3] = [event("holdout_evaluated", dataset_id=did, branch_id="primary") for did in ("holdout", "renamed-holdout")]
        elif name == "posthoc_sensitivity":
            manifest["branch_inventory"].append("sensitivity")
            events += [planned("sensitivity", role="sensitivity"), available("sensitivity"),
                       event("result_viewed", branch_id="sensitivity"),
                       event("branch_discarded", branch_id="sensitivity", decision_basis="predeclared", reason="Supplemental check, not candidate selection")]
        write(root / "history.json", seal_selection_history(manifest, events))
        report = evaluate_selection_history(root / "history.json", claim_contract=root / "contract.json")
        write(root / "review.json", report)
        (root / "REVIEW.md").write_text("# Synthetic scenario, not observed history\n\n" + render_selection_history(report), encoding="utf-8")
        rows.append(dict(scenario=name, status=report["status"], confirmatory_use=report["confirmatory_use"],
                         result_sha256=report["selected_result_sha256"], contract_sha256=report["selected_contract_sha256"],
                         history_sha256=report["history_sha256"], findings=[f["code"] for f in report["findings"]]))
    assert len({r["result_sha256"] for r in rows}) == len({r["contract_sha256"] for r in rows}) == 1
    write(out / "comparison.json", dict(synthetic=True, observed_research_history=False, analysis_execution="NOT_PERFORMED", cases=rows))
    lines = ["# 同一结果，不同选择历史（合成情景）", "", "以下记录是人为构造的反事实测试，不是研究者活动实录或真实预注册。",
             "五个情景的最终结果文件、声明合同逐字节相同；只改变选择历史。", "",
             "| 情景 | 历史判断 | 确认性用途 |", "|---|---|---|"]
    lines += [f"| [{r['scenario']}]({r['scenario']}/REVIEW.md) | {r['status']} | {r['confirmatory_use']} |" for r in rows]
    lines += ["", "没有情景获得科学授权。普通显著性仍来自原表；不推导选择后校正 P 值。",
              "未提供历史的真实分析仍为 NOT_ASSESSED，不能用这些合成事件补齐。"]
    (out / "COMPARISON.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    build(parser.parse_args().out.resolve())
