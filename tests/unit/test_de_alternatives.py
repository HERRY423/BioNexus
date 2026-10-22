"""Frozen-denominator, input-preserving DE alternative-analysis acceptance tests."""
from __future__ import annotations

import copy
import hashlib
import json
import shutil

import pandas as pd
import pytest
from test_de_claim_conditions import change_json, change_table, package, seal, write_json

from bionexus.de.alternatives import create_alternative_plan, evaluate_alternative_plan, render_alternatives


def ref(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def reseal(root):
    seal(root)
    record = json.loads((root / "run.json").read_text())
    for role, filename in (("contract", "contract.json"), ("counts", "counts.csv"), ("cells", "cells.csv")):
        record[role] = ref(root, root / filename)
    write_json(root / "run.json", record)


@pytest.fixture
def study(tmp_path):
    base = tmp_path / "baseline"
    base.mkdir()
    package.__wrapped__(base)
    meta = pd.read_csv(base / "metadata.csv")
    pd.DataFrame(dict(sample_id=meta["sample"], X=[10, 11, 9, 21, 19, 20], Y=[0] * 6)).to_csv(base / "counts.csv", index=False)
    pd.DataFrame([dict(cell_id=f"{s}-c{i}", sample_id=s) for s in meta["sample"] for i in range(2)]).to_csv(base / "cells.csv", index=False)
    record = dict(schema_version="bionexus.de-alternative-run.v1", synthetic=True,
                  analysis_spec=dict(method="DESeq2", version="fixture", normalization="median_ratio",
                                     test="Wald", p_adjustment="BH"),
                  **{role: ref(base, base / name) for role, name in (("contract", "contract.json"), ("counts", "counts.csv"), ("cells", "cells.csv"))})
    write_json(base / "run.json", record)
    return tmp_path


def make_plan(root, extras=None):
    return create_alternative_plan(root / "baseline/run.json", root / "plan.json", specifications=extras)


def add_run(root, spec, *, effect=1.2, padj=0.01, low=0.4, high=2.):
    base, target = root / "baseline", root / spec["spec_id"]
    shutil.copytree(base, target)
    if spec["kind"] == "leave_one_donor_out":
        meta = pd.read_csv(target / "metadata.csv")
        meta = meta.loc[meta.donor != spec["donor_id"]]
        meta.to_csv(target / "metadata.csv", index=False)
        for filename in ("design.csv", "counts.csv", "cells.csv"):
            frame = pd.read_csv(target / filename)
            frame.loc[frame.sample_id.isin(meta["sample"])].to_csv(target / filename, index=False)
        model = json.loads((target / "model.json").read_text())
        # Re-reference only paired-donor nuisance columns when a donor is removed.
        if model["statistical_unit"] == "paired_donor_fixed_effect":
            donor_enc = {k: v for k, v in model["encodings"].items() if v.get("column") == "donor"}
            retained = set(meta.donor)
            remove = {k for k, v in donor_enc.items() if v["level"] not in retained}
            if {v["level"] for k, v in donor_enc.items() if k not in remove} == retained:
                remove.add(sorted(k for k in donor_enc if k not in remove)[0])
            model["design_columns"] = [k for k in model["design_columns"] if k not in remove]
            for k in remove:
                del model["encodings"][k]
                del model["contrast"][k]
            frame = pd.read_csv(target / "design.csv").drop(columns=list(remove))
            frame.to_csv(target / "design.csv", index=False)
            write_json(target / "model.json", model)
    elif spec["kind"] == "method":
        change_json(target, "run.json", lambda r: r.update(analysis_spec=spec["analysis_spec"]))
    elif spec["kind"] == "gene_filter":
        frame = pd.read_csv(target / "counts.csv")
        genes = [g for g in frame.columns if g != "sample_id"]
        keep = [g for g in genes if (frame[g] >= spec["min_count"]).sum() >= spec["min_samples"]]
        frame[["sample_id", *keep]].to_csv(target / "counts.csv", index=False)
        result = pd.read_csv(target / "results.csv")
        result.loc[result.gene.isin(keep)].to_csv(target / "results.csv", index=False)
    result = pd.read_csv(target / "results.csv")
    result["log2_fold_change"], result["padj"], result["ci_lower"], result["ci_upper"] = effect, padj, low, high
    result.to_csv(target / "results.csv", index=False)
    reseal(target)
    return dict(spec_id=spec["spec_id"], status="completed", record=ref(root, target / "run.json"))


def results(root, entries):
    value = dict(schema_version="bionexus.de-alternative-results.v1",
                 plan_sha256=ref(root, root / "plan.json")["sha256"], runs=entries)
    write_json(root / "runs.json", value)


def run(root):
    return evaluate_alternative_plan(root / "plan.json", root / "runs.json")


def method_spec():
    return dict(spec_id="method-ql", kind="method", rationale="Declared same target; scientific equivalence needs review.",
                analysis_spec=dict(method="edgeR", version="fixture", normalization="TMM", test="QLF", p_adjustment="BH"))


def test_plan_generates_every_donor_and_never_executes(study):
    plan = make_plan(study)
    assert len(plan["specifications"]) == 6
    assert {s["donor_id"] for s in plan["specifications"]} == {f"d{i}" for i in range(6)}
    assert plan["selection_timing"] == "NOT_VERIFIED"
    report = evaluate_alternative_plan(study / "plan.json")
    assert report["claims"][0]["status"] == "INCOMPLETE"
    assert report["claims"][0]["compared"] == 0
    assert len(report["branches"]) == 6
    with pytest.raises(FileExistsError):
        make_plan(study)


def test_complete_comparison_is_neither_voting_nor_scientific_authority(study):
    plan = make_plan(study)
    results(study, [add_run(study, s) for s in plan["specifications"]])
    report = run(study)
    assert report["claims"][0]["status"] == "DIRECTION_AND_THRESHOLDS_RETAINED_WITHIN_PLAN"
    assert report["complete"]
    assert report["scientific_authorization"] == "NONE"
    assert report["joint_inference"] == "NOT_PERFORMED"
    assert all(b["comparison"]["estimand_relation"] == "DONOR_INFLUENCE_DIAGNOSTIC" for b in report["branches"])


def test_direction_flip_identifies_specific_donor_even_with_other_runs_missing(study):
    plan = make_plan(study)
    results(study, [add_run(study, plan["specifications"][0], effect=-0.4, padj=0.2, low=-1., high=0.2)])
    report = run(study)
    summary = report["claims"][0]
    assert summary["status"] == "DIRECTION_SENSITIVE"
    assert not summary["complete"] and summary["planned"] == 6 and summary["compared"] == 1
    assert summary["dependencies"][0]["donor_id"] == "d0"
    assert "剔除供体 d0" in render_alternatives(report)
    assert "direction_reversed" in summary["dependencies"][0]["observations"]


def test_lost_significance_and_wider_interval_are_not_direction_reversal(study):
    plan = make_plan(study)
    entries = [add_run(study, s, padj=0.2, low=-0.2, high=2.6) for s in plan["specifications"]]
    results(study, entries)
    report = run(study)
    change = report["branches"][0]["claims"][0]["changes"]
    assert change["significance_lost"] and change["interval_widened"] and not change["direction_reversed"]
    assert change["power_change"] == "NOT_ESTIMATED"
    assert report["claims"][0]["status"] == "THRESHOLD_OR_UNCERTAINTY_SENSITIVE"


@pytest.mark.parametrize("status", ["pending", "failed"])
def test_failed_pending_and_absent_slots_stay_in_denominator(study, status):
    plan = make_plan(study)
    results(study, [dict(spec_id=plan["specifications"][0]["spec_id"], status=status, reason="No successful fit.")])
    report = run(study)
    assert report["branches"][0]["status"] == status.upper()
    assert report["claims"][0]["planned"] == len(report["claims"][0]["unresolved"]) == 6


@pytest.mark.parametrize("mutation,expected", [
    ("wrong_samples", "UNPLANNED_CHANGE"), ("changed_cells", "QUESTION_CHANGED"),
    ("changed_counts", "UNPLANNED_CHANGE"), ("changed_method", "UNPLANNED_CHANGE"),
    ("changed_claim", "QUESTION_CHANGED"), ("changed_formula", "QUESTION_CHANGED"),
    ("changed_alpha", "QUESTION_CHANGED"), ("changed_synthetic", "INVALID_ARTIFACTS"),
])
def test_unplanned_changes_cannot_be_pooled(study, mutation, expected):
    plan = make_plan(study)
    spec = plan["specifications"][0]
    entry = add_run(study, spec)
    target = study / spec["spec_id"]
    if mutation == "wrong_samples":
        # Self-consistent artifacts remove d1 instead of the planned d0.
        for filename in ("metadata.csv", "counts.csv", "cells.csv", "design.csv"):
            df = pd.read_csv(target / filename).replace({"s1": "s0", "d1": "d0", "s1-c0": "s0-c0", "s1-c1": "s0-c1"})
            df.to_csv(target / filename, index=False)
    elif mutation == "changed_cells":
        change_table(target, "cells.csv", lambda df: df.__setitem__("cell_id", [f"new{i}" for i in range(len(df))]))
    elif mutation == "changed_counts":
        change_table(target, "counts.csv", lambda df: df.__setitem__("X", 999))
    elif mutation == "changed_method":
        change_json(target, "run.json", lambda r: r["analysis_spec"].update(normalization="other"))
    elif mutation == "changed_claim":
        change_json(target, "contract.json", lambda c: c["analysis"].update(cell_type="B"))
    elif mutation == "changed_formula":
        change_json(target, "model.json", lambda m: m.update(formula="~1+condition"))
    elif mutation == "changed_alpha":
        change_json(target, "contract.json", lambda c: c["claims"][0].update(alpha=0.5))
    else:
        change_json(target, "run.json", lambda r: r.update(synthetic=False))
    reseal(target)
    entry["record"] = ref(study, target / "run.json")
    results(study, [entry])
    report = run(study)
    assert report["branches"][0]["status"] == expected
    assert report["claims"][0]["compared"] == 0


def test_method_and_filter_alternatives_preserve_explicit_scientific_target(study):
    extras = [method_spec(), dict(spec_id="filter", kind="gene_filter", min_count=1, min_samples=2,
                                 rationale="Remove unexpressed genes within the initial gene universe.")]
    plan = make_plan(study, extras)
    results(study, [add_run(study, s) for s in plan["specifications"]])
    report = run(study)
    assert report["complete"] and report["claims"][0]["compared"] == 8
    assert report["branches"][-1]["comparison"]["retained_genes"] == 1


def test_filtered_target_is_unresolved_not_zero_effect(study):
    spec = dict(spec_id="filter", kind="gene_filter", min_count=100, min_samples=2, rationale="Boundary test.")
    # Keep another gene so the run has a valid nonempty gene universe.
    change_table(study / "baseline", "counts.csv", lambda df: df.__setitem__("Y", 200))
    reseal(study / "baseline")
    plan = make_plan(study, [spec])
    results(study, [add_run(study, plan["specifications"][-1])])
    report = run(study)
    assert report["branches"][-1]["claims"][0]["status"] == "TARGET_FILTERED_OUT"
    assert report["claims"][0]["effect_range"] is None


def test_numerically_duplicate_filter_is_not_extra_evidence(study):
    change_table(study / "baseline", "counts.csv", lambda df: df.__setitem__("Y", 20))
    reseal(study / "baseline")
    spec = dict(spec_id="filter", kind="gene_filter", min_count=1, min_samples=2, rationale="Boundary test.")
    plan = make_plan(study, [spec])
    results(study, [add_run(study, plan["specifications"][-1])])
    assert run(study)["branches"][-1]["status"] == "REDUNDANT_SPECIFICATION"


@pytest.mark.parametrize("case", ["duplicate_specs", "duplicate_ids", "unchanged_method"])
def test_redundant_or_ambiguous_plans_rejected(study, case):
    extra = method_spec()
    extras = [extra, copy.deepcopy(extra)]
    if case == "duplicate_specs":
        extras[1]["spec_id"] = "different-name"
    elif case == "unchanged_method":
        extras = [extra]
        extra["analysis_spec"] = json.loads((study / "baseline/run.json").read_text())["analysis_spec"]
    with pytest.raises(ValueError):
        make_plan(study, extras)


@pytest.mark.parametrize("case", ["wrong_digest", "duplicate_run", "unknown_run", "omit_planned_donor"])
def test_results_and_plan_cannot_silently_change_denominators(study, case):
    plan = make_plan(study)
    entry = add_run(study, plan["specifications"][0])
    results(study, [entry])
    if case == "wrong_digest":
        change_json(study, "runs.json", lambda r: r.update(plan_sha256="0" * 64))
    elif case == "duplicate_run":
        change_json(study, "runs.json", lambda r: r["runs"].append(entry))
    elif case == "unknown_run":
        change_json(study, "runs.json", lambda r: r["runs"][0].update(spec_id="invented"))
    else:
        change_json(study, "plan.json", lambda p: p["specifications"].pop())
    with pytest.raises(ValueError):
        run(study)


@pytest.mark.parametrize("case", ["tamper", "missing", "path_escape", "noninteger_counts", "duplicate_cell"])
def test_bad_artifacts_are_retained_as_unresolved_slots(study, case):
    plan = make_plan(study)
    entry = add_run(study, plan["specifications"][0])
    target = study / entry["spec_id"]
    if case == "tamper":
        with (target / "counts.csv").open("a") as stream:
            stream.write("\n")
    elif case == "missing":
        (target / "counts.csv").unlink()
    elif case == "path_escape":
        entry["record"]["path"] = "../outside.json"
    elif case == "noninteger_counts":
        change_table(target, "counts.csv", lambda df: df.__setitem__("X", 1.1))
        reseal(target)
        entry["record"] = ref(study, target / "run.json")
    else:
        change_table(target, "cells.csv", lambda df: df.__setitem__("cell_id", "duplicate"))
        reseal(target)
        entry["record"] = ref(study, target / "run.json")
    results(study, [entry])
    report = run(study)
    assert report["branches"][0]["status"] in ("MISSING_ARTIFACTS", "INVALID_ARTIFACTS")
    assert report["claims"][0]["planned"] == 6


def test_paired_donor_omission_retains_pairs_and_valid_reference_recoding(study):
    base = study / "baseline"
    change_table(base, "metadata.csv", lambda df: df.__setitem__("donor", ["d0", "d1", "d2"] * 2))
    frame = pd.read_csv(base / "design.csv").drop(columns=["batch_b"])
    frame["donor_1"], frame["donor_2"] = [0, 1, 0] * 2, [0, 0, 1] * 2
    frame.to_csv(base / "design.csv", index=False)
    def paired(m):
        m.update(formula="~1+condition+donor", statistical_unit="paired_donor_fixed_effect",
                 design_columns=["Intercept", "disease", "donor_1", "donor_2"])
        del m["encodings"]["batch_b"]
        del m["contrast"]["batch_b"]
        for i in (1, 2):
            m["encodings"][f"donor_{i}"] = dict(kind="categorical", column="donor", level=f"d{i}")
            m["contrast"][f"donor_{i}"] = 0
    change_json(base, "model.json", paired)
    reseal(base)
    plan = make_plan(study)
    results(study, [add_run(study, s) for s in plan["specifications"]])
    report = run(study)
    assert len(report["branches"]) == 3 and report["complete"]
    assert all(b["comparison"]["retained_samples"] == 4 for b in report["branches"])


def test_nonestimable_omission_is_not_direction_reversal(study):
    base = study / "baseline"
    # d0 is the only cross-batch bridge; its omission makes batch == condition.
    change_table(base, "metadata.csv", lambda df: df.__setitem__("batch", ["b", "a", "a", "b", "b", "b"]))
    change_table(base, "design.csv", lambda df: df.__setitem__("batch_b", [1, 0, 0, 1, 1, 1]))
    reseal(base)
    plan = make_plan(study)
    results(study, [add_run(study, plan["specifications"][0])])
    report = run(study)
    assert report["branches"][0]["claims"][0]["status"] == "NOT_ESTIMABLE"
    assert report["branches"][0]["claims"][0]["changes"] == {}


def test_audit_integration_and_synthetic_bundle_label(study, capsys):
    from bionexus.cli import main
    from bionexus.de_audit import audit_differential_expression
    from bionexus.de_bundle import verify_de_bundle
    assert main(["de-alternatives-plan", str(study / "baseline/run.json"), "--out", str(study / "plan.json")]) == 0
    plan = json.loads((study / "plan.json").read_text())
    results(study, [add_run(study, s) for s in plan["specifications"]])
    bundle = study / "review"
    assert main(["audit-de", "--alternative-plan", str(study / "plan.json"), "--alternative-runs", str(study / "runs.json"),
                 "--bundle", str(bundle), "--json"]) == 1
    assert '"alternative_analysis"' in capsys.readouterr().out
    assert "合成" in (bundle / "REVIEW.md").read_text(encoding="utf-8")
    assert "lodo-001" in (bundle / "audit-full.md").read_text(encoding="utf-8")
    assert verify_de_bundle(bundle)["status"] == "CONSISTENT"
    audited = audit_differential_expression(alternative_plan=study / "plan.json")
    assert not audited.passed
    assert "合理替代分析" in audited.summary_text(use_color=False)


def test_audit_rejects_runs_without_plan(study):
    from bionexus.de_audit import audit_differential_expression
    audited = audit_differential_expression(alternative_runs=study / "absent.json")
    assert not audited.passed
    assert any(c.status.value == "PARSE_FAILED" for c in audited.checks)


def test_audit_cannot_substitute_other_baseline_contract(study):
    make_plan(study)
    other = study / "other.json"
    other.write_text("{}")
    with pytest.raises(ValueError, match="baseline"):
        evaluate_alternative_plan(study / "plan.json", claim_contract=other)


def test_filter_may_remove_all_genes_without_imputing_zero_effect(study):
    spec = dict(spec_id="filter-all", kind="gene_filter", min_count=1000, min_samples=2, rationale="Boundary case.")
    plan = make_plan(study, [spec])
    results(study, [add_run(study, plan["specifications"][-1])])
    report = run(study)
    assert report["branches"][-1]["claims"][0]["status"] == "TARGET_FILTERED_OUT"


@pytest.mark.parametrize("change", ["missing_interval", "changed_interval_level", "shuffled_rows"])
def test_interval_coverage_and_row_order(study, change):
    plan = make_plan(study)
    entry = add_run(study, plan["specifications"][0])
    target = study / entry["spec_id"]
    if change == "missing_interval":
        change_table(target, "results.csv", lambda df: df.drop(columns="ci_lower", inplace=True))
    elif change == "changed_interval_level":
        change_table(target, "results.csv", lambda df: df.__setitem__("ci_level", .99))
    else:
        for name in ("design.csv", "metadata.csv", "cells.csv", "counts.csv"):
            df = pd.read_csv(target / name)
            df.iloc[::-1].to_csv(target / name, index=False)
    reseal(target)
    entry["record"] = ref(study, target / "run.json")
    results(study, [entry])
    result = run(study)["branches"][0]["claims"][0]
    if change == "missing_interval":
        assert result["status"] == "NOT_ASSESSED" and not result["changes"]
    elif change == "changed_interval_level":
        assert result["changes"]["interval_level_changed"] and result["changes"]["interval_widened"] is None
    else:
        assert result["status"] == "COMPARED"


def test_same_nonsignificant_interval_is_not_new_sensitivity(study):
    base = study / "baseline"
    change_table(base, "results.csv", lambda df: df.__setitem__("ci_lower", -.2))
    change_table(base, "results.csv", lambda df: df.__setitem__("padj", .2))
    reseal(base)
    plan = make_plan(study)
    results(study, [add_run(study, s, padj=.2, low=-.2) for s in plan["specifications"]])
    report = run(study)
    assert not report["claims"][0]["dependencies"]
    assert report["baseline_condition_review"]["status"] == "UNSATISFIED"


def test_multiple_claims_have_separate_comparison_coverage(study):
    base = study / "baseline"
    df = pd.read_csv(base / "results.csv")
    other = df.copy()
    other["gene"] = "Y"
    pd.concat([df, other]).to_csv(base / "results.csv", index=False)
    change_json(base, "contract.json", lambda c: c["claims"].append(dict(claim_id="Y-T", gene="Y", direction="up", scope="cohort_association", alpha=.05)))
    reseal(base)
    plan = make_plan(study)
    entry = add_run(study, plan["specifications"][0])
    target = study / entry["spec_id"]
    df = pd.read_csv(target / "results.csv")
    df.loc[df.gene == "Y", "ci_upper"] = float("nan")
    df.to_csv(target / "results.csv", index=False)
    reseal(target)
    entry["record"] = ref(study, target / "run.json")
    results(study, [entry])
    report = run(study)
    assert [c["compared"] for c in report["claims"]] == [1, 0]


def test_other_audit_input_cannot_inherit_sensitivity_report(study):
    make_plan(study)
    substitute = study / "substitute.csv"
    substitute.write_text("gene\nFAKE\n")
    with pytest.raises(ValueError, match="inputs"):
        evaluate_alternative_plan(study / "plan.json", de_table=substitute)


def test_plan_creation_rejects_baseline_outside_package(study):
    inside = study / "inner"
    inside.mkdir()
    with pytest.raises(ValueError, match="inside"):
        create_alternative_plan(study / "baseline/run.json", inside / "plan.json")


def test_different_filter_parameters_with_same_effective_inputs_not_counted_twice(study):
    specs = [dict(spec_id=f"filter-{i}", kind="gene_filter", min_count=i, min_samples=2, rationale="Boundary.")
             for i in (1, 2)]
    plan = make_plan(study, specs)
    entries = [add_run(study, s, effect=1.2 + i / 100) for i, s in enumerate(plan["specifications"][-2:])]
    results(study, entries)
    report = run(study)
    assert report["branches"][-1]["status"] == "REDUNDANT_SPECIFICATION"
    assert report["claims"][0]["compared"] == 1


def test_reused_run_record_stays_visible_as_unresolved(study):
    plan = make_plan(study)
    entry = add_run(study, plan["specifications"][0])
    duplicate = copy.deepcopy(entry)
    duplicate["spec_id"] = plan["specifications"][1]["spec_id"]
    results(study, [entry, duplicate])
    report = run(study)
    assert report["branches"][1]["status"] == "INVALID_ARTIFACTS"
    assert report["claims"][0]["compared"] == 1
