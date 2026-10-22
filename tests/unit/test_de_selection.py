"""Same final numbers, different disclosed selection histories and claim uses."""
from __future__ import annotations

import json

import pandas as pd
import pytest
from test_de_claim_conditions import package as condition_package

from bionexus.de.alternatives import _encode, _make_ref, _sha
from bionexus.de.selection import evaluate_selection_history, render_selection_history, seal_selection_history


def event(kind, **payload):
    return dict(actor_id="researcher", session_id="s1", kind=kind, payload=payload)


def planned(root, bid="primary", role="candidate", file="plan.json"):
    return event("branch_planned", branch_id=bid, role=role, plan=_make_ref(root, root / file))


def available(root, bid="primary"):
    return event("result_available", branch_id=bid, contract=_make_ref(root, root / "contract.json"))


def selected(bid="primary", basis="predeclared"):
    return event("result_selected", branch_id=bid, decision_basis=basis, reason="Report prespecified result")


@pytest.fixture
def study(tmp_path):
    root = condition_package.__wrapped__(tmp_path)
    contract = json.loads((root / "contract.json").read_text())
    model = json.loads((root / "model.json").read_text())
    plan = dict(schema_version="bionexus.de-selection-plan.v1", analysis=contract["analysis"], claims=contract["claims"],
                metadata_sha256=contract["artifacts"]["metadata"]["sha256"],
                model={k: model[k] for k in ("formula", "statistical_unit", "effect_measure")},
                selection_rule="report_all_planned_claims")
    (root / "plan.json").write_bytes(_encode(plan))
    meta = pd.read_csv(root / "metadata.csv")
    meta.rename(columns={"sample": "sample_id", "donor": "donor_id"})[["sample_id", "donor_id"]].to_csv(root / "members.csv", index=False)
    manifest = dict(scope_id="study-1", actor_ids=["researcher"], session_ids=["s1"], branch_inventory=["primary"],
                    capture_mode="prospective", coverage="complete_declared", gaps=[], synthetic=True,
                    datasets=[dict(dataset_id="discovery", role="discovery", identity_namespace="study-1",
                                   manifest=_make_ref(root, root / "members.csv"))])
    return root, manifest, [planned(root), available(root), event("result_viewed", branch_id="primary"), selected()]


def save(study):
    root, manifest, events = study
    value = seal_selection_history(manifest, events)
    (root / "history.json").write_bytes(_encode(value))
    return value


def run(study, **kwargs):
    save(study)
    return evaluate_selection_history(study[0] / "history.json", **kwargs)


def codes(report):
    return {f["code"] for f in report["findings"]}


def test_identical_final_artifact_distinguishes_selection_history(study):
    root, manifest, events = study
    before = (root / "results.csv").read_bytes()
    fixed = run(study)
    assert fixed["status"] == "PRE_RESULT_PLAN_RECORDED"
    assert fixed["confirmatory_use"] == "NOT_ESTABLISHED"
    manifest["branch_inventory"].append("screen")
    events[:0] = [planned(root, "screen"), available(root, "screen"), event("result_viewed", branch_id="screen"),
                  event("branch_discarded", branch_id="screen", decision_basis="result_informed", reason="Prefer primary")]
    adaptive = run(study)
    assert adaptive["status"] == "SELECTION_DEPENDENCE_RECORDED"
    assert adaptive["confirmatory_use"] == "EXPLORATORY_ONLY_FOR_RECORDED_SELECTION"
    assert "CHOICE_AFTER_RECORDED_EXPOSURE" in codes(adaptive)
    assert "RESULT_INFORMED_DISCARD" in codes(adaptive)
    assert fixed["selected_result_sha256"] == adaptive["selected_result_sha256"]
    assert fixed["selected_condition_review"] == adaptive["selected_condition_review"]
    assert (root / "results.csv").read_bytes() == before
    assert adaptive["recorded_branch_count"] == adaptive["declared_branch_count"] == 2
    assert adaptive["branches"][0]["disposition"] == "DISCARDED"


def test_missing_history_explicitly_not_assessed():
    report = evaluate_selection_history()
    assert report["status"] == "NOT_ASSESSED"
    assert report["confirmatory_use"] == "NOT_ESTABLISHED"
    assert "NOT_ASSESSED" in render_selection_history(report)
    with pytest.raises(ValueError, match="requires"):
        evaluate_selection_history(expected_head="0" * 64)


@pytest.mark.parametrize("change", [lambda m: m.update(coverage="partial"), lambda m: m.update(capture_mode="retrospective"),
                                     lambda m: m["gaps"].append("Prior session not captured")])
def test_coverage_cannot_be_recovered_from_a_clean_chain(study, change):
    change(study[1])
    r = run(study)
    assert r["status"] == "HISTORY_INCOMPLETE"
    assert r["capture_authentication"] == r["preregistration"] == "NOT_ESTABLISHED"


def test_anchor_detects_truncation_and_resealing_not_authenticity(study):
    root, manifest, events = study
    original = save(study)
    good = evaluate_selection_history(root / "history.json", expected_head=original["head_sha256"])
    assert good["integrity"] == "CONSISTENT_WITH_EXPECTED_HEAD"
    assert good["preregistration"] == "NOT_ESTABLISHED"
    events.pop()
    save(study)
    with pytest.raises(ValueError, match="expected head"):
        evaluate_selection_history(root / "history.json", expected_head=original["head_sha256"])
    assert evaluate_selection_history(root / "history.json")["status"] == "HISTORY_INCOMPLETE"


@pytest.mark.parametrize("mutation", [lambda h: h["events"][0].update(seq=9),
                                      lambda h: h["events"][0]["payload"].update(branch_id="hidden"),
                                      lambda h: h["manifest"].update(scope_id="replacement"),
                                      lambda h: h.update(head_sha256="0" * 64)])
def test_chain_tampering_rejected(study, mutation):
    h = save(study)
    mutation(h)
    (study[0] / "history.json").write_bytes(_encode(h))
    with pytest.raises(ValueError, match="chain"):
        evaluate_selection_history(study[0] / "history.json")


def test_results_available_is_not_the_same_as_viewed(study):
    root, manifest, events = study
    manifest["branch_inventory"].append("screen")
    events[:0] = [planned(root, "screen"), available(root, "screen"),
                  event("branch_discarded", branch_id="screen", decision_basis="operational", reason="Fit superseded")]
    report = run(study)
    assert "CHOICE_AFTER_RESULT_AVAILABLE" in codes(report)
    assert "CHOICE_AFTER_RECORDED_EXPOSURE" not in codes(report)
    assert report["confirmatory_use"] == "NOT_ESTABLISHED"


def test_plan_revision_retains_parent_reason_and_detects_deviation(study):
    root, _, events = study
    plan = json.loads((root / "plan.json").read_text())
    plan["claims"][0]["alpha"] = .1
    (root / "revised.json").write_bytes(_encode(plan))
    events.insert(1, event("plan_revised", branch_id="primary", plan=_make_ref(root, root / "revised.json"),
                           parent_sha256=_sha((root / "plan.json").read_bytes()), reason="Threshold changed"))
    r = run(study)
    assert "UNRECORDED_PLAN_DEVIATION" in codes(r)
    assert r["branches"][0]["revisions"][0]["reason"] == "Threshold changed"


@pytest.mark.parametrize("mutation", [
    lambda root, m, e: e.insert(1, planned(root)),
    lambda root, m, e: e.insert(1, event("result_viewed", branch_id="primary")),
    lambda root, m, e: e.insert(2, available(root)),
    lambda root, m, e: e.append(selected()),
    lambda root, m, e: e[0].update(actor_id="unobserved-actor"),
    lambda root, m, e: e[0].update(session_id="unobserved-session"),
    lambda root, m, e: e[1]["payload"].update(branch_id="unknown"),
    lambda root, m, e: e[0]["payload"].update(role="sensitivity"),
    lambda root, m, e: e.insert(2, event("plan_revised", branch_id="primary", plan=e[0]["payload"]["plan"], parent_sha256="0"*64, reason="late")),
])
def test_impossible_or_out_of_scope_event_sequences_rejected(study, mutation):
    mutation(*study)
    with pytest.raises(ValueError):
        run(study)


def test_missing_branches_and_dispositions_stay_in_denominator(study):
    root, manifest, events = study
    manifest["branch_inventory"] += ["hidden", "unfinished"]
    events.insert(0, planned(root, "unfinished"))
    r = run(study)
    assert {"BRANCH_INVENTORY_INCOMPLETE", "BRANCH_DISPOSITION_MISSING"} <= codes(r)
    assert r["declared_branch_count"] == 3
    assert r["recorded_branch_count"] == 2
    assert r["status"] == "HISTORY_INCOMPLETE"


def test_metadata_only_access_is_not_outcome_exposure(study):
    study[2].insert(0, event("data_accessed", dataset_id="discovery", access="metadata"))
    assert run(study)["status"] == "PRE_RESULT_PLAN_RECORDED"


def test_outcome_access_before_plan_is_exposure(study):
    study[2].insert(0, event("data_accessed", dataset_id="discovery", access="outcomes"))
    assert run(study)["status"] == "SELECTION_DEPENDENCE_RECORDED"


def holdout(study, *, overlap=False, namespace="study-1", alias=False):
    root, manifest, events = study
    pd.DataFrame(dict(sample_id=["s0" if overlap else "hs1"], donor_id=["d0" if overlap else "hd1"])).to_csv(root / "holdout.csv", index=False)
    manifest["datasets"].append(dict(dataset_id="validation", role="holdout", identity_namespace=namespace,
                                     manifest=_make_ref(root, root / "holdout.csv")))
    if alias:
        manifest["datasets"].append({**manifest["datasets"][-1], "dataset_id": "validation-renamed"})
    events.insert(-1, event("holdout_evaluated", dataset_id="validation", branch_id="primary"))


@pytest.mark.parametrize("mode,expected", [("overlap", "DISCOVERY_HOLDOUT_OVERLAP"), ("namespace", "HOLDOUT_IDENTITY_NOT_COMPARABLE"),
                                          ("reuse", "HOLDOUT_REUSED"), ("access", "HOLDOUT_OUTCOMES_EXPOSED")])
def test_holdout_aliases_reuse_exposure_and_identity_boundaries(study, mode, expected):
    holdout(study, overlap=mode=="overlap", namespace="other" if mode=="namespace" else "study-1", alias=True)
    if mode == "reuse":
        study[2].insert(-1, event("holdout_evaluated", dataset_id="validation-renamed", branch_id="primary"))
    if mode == "access":
        study[2].insert(1, event("data_accessed", dataset_id="validation-renamed", access="outcomes"))
    r = run(study)
    assert expected in codes(r)
    assert all(h["independence"] == "NOT_ESTABLISHED" for h in r["holdouts"])


def test_disjoint_holdout_is_not_independent_validation_certification(study):
    holdout(study)
    r = run(study)
    assert r["holdouts"][0]["issues"] == []
    assert r["confirmatory_use"] == r["preregistration"] == "NOT_ESTABLISHED"


def test_posthoc_sensitivity_does_not_reclassify_primary_as_selected(study):
    root, manifest, events = study
    manifest["branch_inventory"].append("sensitivity")
    events += [planned(root, "sensitivity", role="sensitivity"), available(root, "sensitivity"),
               event("result_viewed", branch_id="sensitivity"),
               event("branch_discarded", branch_id="sensitivity", decision_basis="predeclared", reason="Supplemental sensitivity result")]
    r = run(study)
    assert "CHOICE_AFTER_RECORDED_EXPOSURE" in codes(r)
    assert r["confirmatory_use"] == "NOT_ESTABLISHED"


def test_changed_audit_input_cannot_be_covered_by_unrelated_history(study):
    root = study[0]
    changed = pd.read_csv(root / "results.csv")
    changed["log2_fold_change"] = 99
    r = run(study, de_table=changed)
    assert "SELECTED_ARTIFACT_BINDING_NOT_ESTABLISHED" in codes(r)
    assert r["status"] == "HISTORY_INCOMPLETE"
    other = root / "other-contract.json"
    other.write_bytes(b"{}")
    with pytest.raises(ValueError, match="not the audited"):
        run(study, claim_contract=other)


@pytest.mark.parametrize("mode", ["digest", "escape", "extra", "duplicate-key", "nonfinite"])
def test_contract_bytes_and_strict_json(study, mode):
    root, _, events = study
    if mode == "digest":
        events[0]["payload"]["plan"]["sha256"] = "0" * 64
    elif mode == "escape":
        events[0]["payload"]["plan"]["path"] = "../escape.json"
    elif mode == "extra":
        events[0]["claimed_timestamp"] = "1900-01-01"
    else:
        (root / "history.json").write_text('{"x":1,"x":2}' if mode == "duplicate-key" else '{"x":NaN}')
        with pytest.raises(ValueError):
            evaluate_selection_history(root / "history.json")
        return
    with pytest.raises((ValueError, FileNotFoundError)):
        run(study)


def test_engine_and_renderers_preserve_unknown_and_fail_closed(study):
    from bionexus.de_audit import audit_differential_expression
    root = study[0]
    assert audit_differential_expression().to_dict()["selection_history"]["status"] == "NOT_ASSESSED"
    save(study)
    r = audit_differential_expression(claim_contract=root / "contract.json", selection_history=root / "history.json")
    assert r.selection_history["status"] == "PRE_RESULT_PLAN_RECORDED"
    assert "分析选择历史" in r.to_markdown()
    assert "分析选择历史" in r.summary_text(False)
    bad = audit_differential_expression(selection_history=root / "history.json", selection_expected_head="0"*64)
    assert bad.selection_history["status"] == "INVALID_HISTORY"
    assert not bad.passed
    assert next(c for c in bad.checks if c.check_id == "selection_history").status.value == "PARSE_FAILED"


def test_cli_bundle_includes_synthetic_history_and_verifies(study, capsys):
    from bionexus import cli
    from bionexus.de_bundle import verify_de_bundle
    root = study[0]
    save(study)
    out = root / "bundle"
    code = cli.main(["audit-de", "--claim-contract", str(root / "contract.json"), "--selection-history", str(root / "history.json"),
                     "--bundle", str(out), "--json"])
    assert code == 1  # A condition/history package alone does not meet all legacy audit evidence requirements.
    assert json.loads((out / "audit.json").read_text(encoding="utf-8"))["selection_history"]["synthetic"]
    assert "SYNTHETIC" in (out / "manifest.json").read_text(encoding="utf-8")
    assert "分析选择历史" in (out / "REVIEW.md").read_text(encoding="utf-8")
    assert verify_de_bundle(out)["status"] == "CONSISTENT"
    capsys.readouterr()


def test_explicit_result_informed_selection_and_engine_scope(study):
    from bionexus.de_audit import audit_differential_expression
    study[2][-1] = selected(basis="result_informed")
    r = run(study)
    assert "RESULT_INFORMED_SELECTION" in codes(r)
    audit = audit_differential_expression(selection_history=study[0] / "history.json")
    assert not audit.passed
    assert "探索性" in audit.claim_boundary.allowed_scope
    assert audit.selection_history["claims"][0]["condition_status"] == "SATISFIED"


@pytest.mark.parametrize("mode", ["duplicate", "badtable", "unknown", "not-holdout", "missing-discovery"])
def test_dataset_contract_rejects_or_preserves_missing_scope(study, mode):
    root, m, e = study
    if mode == "duplicate":
        m["datasets"] *= 2
    elif mode == "badtable":
        (root / "members.csv").write_text("sample_id,donor_id\ns,same\ns,other\n")
        m["datasets"][0]["manifest"] = _make_ref(root, root / "members.csv")
    elif mode == "unknown":
        e.insert(0, event("data_accessed", dataset_id="unknown", access="outcomes"))
    elif mode == "not-holdout":
        e.insert(1, event("holdout_evaluated", dataset_id="discovery", branch_id="primary"))
    else:
        m["datasets"] = []
        assert "DISCOVERY_MEMBERSHIP_NOT_BOUND" in codes(run(study))
        return
    with pytest.raises(ValueError):
        run(study)


def test_duplicate_claim_plan_rejected(study):
    root, _, events = study
    plan = json.loads((root / "plan.json").read_text())
    plan["claims"] *= 2
    (root / "plan.json").write_bytes(_encode(plan))
    events[0] = planned(root)
    with pytest.raises(ValueError, match="duplicate claim"):
        run(study)


def test_late_validation_read_is_disclosed_without_erasing_primary(study):
    holdout(study)
    study[2].append(event("data_accessed", dataset_id="validation", access="outcomes"))
    r = run(study)
    assert "HOLDOUT_OUTCOMES_EXPOSED" in codes(r)
    assert "HOLDOUT_EXPOSED_BEFORE_EVALUATION" not in codes(r)
    assert r["confirmatory_use"] == "NOT_ESTABLISHED"
    assert r["status"] == "PRE_RESULT_PLAN_RECORDED"


def test_alternative_plan_timing_is_bound_to_exact_artifact(study):
    from test_de_alternatives import make_plan
    from test_de_alternatives import study as alternative_study

    root, _, events = study
    altroot = root / "alternatives"
    altroot.mkdir()
    alternative_study.__wrapped__(altroot)
    make_plan(altroot)
    altpath = altroot / "plan.json"
    assert "ALTERNATIVE_PLAN_HISTORY_MISSING_OR_AMBIGUOUS" in codes(run(study, alternative_plan=altpath))
    events.append(event("alternative_plan_frozen", plan=_make_ref(root, altpath)))
    r = run(study, alternative_plan=altpath)
    assert r["alternative_plan_timing"] == "AFTER_RECORDED_EXPOSURE"
    assert r["confirmatory_use"] == "NOT_ESTABLISHED"
    events.insert(0, events.pop())
    assert run(study, alternative_plan=altpath)["alternative_plan_timing"] == "BEFORE_RECORDED_RESULTS"
    value = json.loads(altpath.read_text())
    value["claim_contract_sha256"] = "0" * 64
    altpath.write_bytes(_encode(value))
    events[0] = event("alternative_plan_frozen", plan=_make_ref(root, altpath))
    with pytest.raises(ValueError, match="same claim contract"):
        run(study, alternative_plan=altpath)


def test_missing_selected_artifact_is_not_an_assessed_history(study):
    root = study[0]
    (root / "results.csv").unlink()
    r = run(study)
    assert "SELECTED_ARTIFACT_BINDING_NOT_ESTABLISHED" in codes(r)
    assert r["status"] == "HISTORY_INCOMPLETE"
