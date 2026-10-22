"""Acceptance cases: identical DE tables, different designs and evidence coverage."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from bionexus.de.conditions import contrast_diagnostics, render_conditions, verify_de_claim_conditions


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def seal(root):
    contract = json.loads((root / "contract.json").read_text())
    model = json.loads((root / "model.json").read_text())
    for role in ("results", "metadata", "design"):
        spec = contract["artifacts"][role]
        digest = hashlib.sha256((root / spec["path"]).read_bytes()).hexdigest()
        spec["sha256"] = digest
        model["artifact_sha256"][role] = digest
    write_json(root / "model.json", model)
    contract["artifacts"]["model"]["sha256"] = hashlib.sha256((root / "model.json").read_bytes()).hexdigest()
    write_json(root / "contract.json", contract)
    return root / "contract.json"


@pytest.fixture
def package(tmp_path):
    metadata = pd.DataFrame({"sample": [f"s{i}" for i in range(6)], "donor": [f"d{i}" for i in range(6)],
                             "condition": ["control"] * 3 + ["disease"] * 3,
                             "batch": ["a", "b", "a", "b", "a", "b"]})
    metadata.to_csv(tmp_path / "metadata.csv", index=False)
    pd.DataFrame({"sample_id": metadata["sample"], "Intercept": 1,
                  "disease": [0, 0, 0, 1, 1, 1], "batch_b": [0, 1, 0, 1, 0, 1]}).to_csv(tmp_path / "design.csv", index=False)
    pd.DataFrame([dict(gene="X", cell_type="T", numerator="disease", denominator="control",
                       log2_fold_change=1.2, padj=0.01, ci_lower=0.4, ci_upper=2., ci_level=0.95)]).to_csv(
                           tmp_path / "results.csv", index=False)
    model = dict(schema_version="bionexus.de-model-record.v1", artifact_sha256={k: "0" * 64 for k in ("results", "metadata", "design")},
                 cell_type="T", numerator="disease", denominator="control", effect_measure="log2_fold_change",
                 fit_status="converged", formula="~ 1 + condition + batch", statistical_unit="independent_donor",
                 design_columns=["Intercept", "disease", "batch_b"],
                 encodings={"Intercept": {"kind": "intercept"},
                            "disease": {"kind": "categorical", "column": "condition", "level": "disease"},
                            "batch_b": {"kind": "categorical", "column": "batch", "level": "b"}},
                 contrast={"Intercept": 0, "disease": 1, "batch_b": 0})
    write_json(tmp_path / "model.json", model)
    contract = dict(schema_version="bionexus.de-claim-conditions.v1",
                    analysis=dict(cell_type="T", numerator="disease", denominator="control"),
                    metadata_columns=dict(sample="sample", donor="donor", condition="condition"),
                    artifacts={k: dict(path=f"{k}.{'json' if k == 'model' else 'csv'}", sha256="0" * 64)
                               for k in ("results", "metadata", "design", "model")},
                    claims=[dict(claim_id="X-T", gene="X", direction="up", scope="cohort_association", alpha=0.05)])
    write_json(tmp_path / "contract.json", contract)
    seal(tmp_path)
    return tmp_path


def run(root):
    return verify_de_claim_conditions(root / "contract.json")


def conditions(report):
    return {c["condition_id"]: c for c in report["claims"][0]["conditions"]}


def change_json(root, filename, update):
    value = json.loads((root / filename).read_text())
    update(value)
    write_json(root / filename, value)


def change_table(root, filename, update):
    frame = pd.read_csv(root / filename)
    update(frame)
    frame.to_csv(root / filename, index=False)


def test_valid_package_retains_non_authorization(package):
    report = run(package)
    assert report["status"] == "SATISFIED"
    assert report["scientific_authorization"] == "NONE"
    assert report["analysis_execution_verification"] == "NOT_PERFORMED"
    variants = report["claims"][0]["scope_assessments"]
    assert [v["status"] for v in variants] == ["SATISFIED", "SATISFIED", "NOT_ASSESSED", "NOT_ASSESSED"]
    assert conditions(report)["contrast_estimability"]["observed"]["rank"] == 3
    assert "ARTIFACT_EXTRACTED / SATISFIED" in render_conditions(report)


def test_same_result_confounded_design_changes_claim_support(package):
    original_results = (package / "results.csv").read_bytes()
    change_table(package, "metadata.csv", lambda df: df.__setitem__("batch", ["a"] * 3 + ["b"] * 3))
    change_table(package, "design.csv", lambda df: df.__setitem__("batch_b", [0] * 3 + [1] * 3))
    seal(package)
    report = run(package)
    assert (package / "results.csv").read_bytes() == original_results
    checks = conditions(report)
    assert checks["design_encoding"]["status"] == "SATISFIED"
    assert checks["contrast_estimability"]["status"] == "UNSATISFIED"
    assert report["status"] == "UNSATISFIED"
    assert report["claims"][0]["scope_assessments"][0]["status"] == "SATISFIED"


def test_estimability_is_not_synonym_for_full_rank():
    x = np.array([[1, 0, 0], [1, 1, 1], [1, 2, 2], [1, 3, 3]])
    assert contrast_diagnostics(x, np.array([0, 1, 1]))["estimable"]
    assert not contrast_diagnostics(x, np.array([0, 1, 0]))["estimable"]
    assert not contrast_diagnostics(x, np.array([0, 1, 1]))["full_rank"]


def test_contrast_diagnostics_invariant_under_column_units():
    x = np.array([[1, 0, 0], [1, 1, 1], [1, 2, 2], [1, 3, 3]])
    scales = np.array([1, 1e9, 1e-9])
    assert contrast_diagnostics(x * scales, np.array([0, 1, 1]) * scales)["estimable"]


@pytest.mark.parametrize("x,c", [([[1, 2]], [0]), ([[1, float("nan")]], [0, 1]), ([[1, 2]], [0, 0])])
def test_invalid_numeric_design_rejected(x, c):
    with pytest.raises(ValueError):
        contrast_diagnostics(np.array(x), np.array(c))


@pytest.mark.parametrize("role", ["metadata", "design", "model", "results"])
def test_missing_artifacts_are_not_assessed(package, role):
    change_json(package, "contract.json", lambda c: c["artifacts"].pop(role))
    report = run(package)
    assert conditions(report)[f"artifact_{role}"]["source"] == "MISSING"
    assert report["status"] == "NOT_ASSESSED"


def test_missing_design_does_not_borrow_researcher_flags(package):
    (package / "design.csv").unlink()
    change_json(package, "contract.json", lambda c: c.update(declarations={"population_transport": "Reviewed and representative"}))
    report = run(package)
    assert report["status"] == "NOT_ASSESSED"
    assert conditions(report)["contrast_estimability"]["status"] == "NOT_ASSESSED"
    assert conditions(report)["population_transport"]["source"] == "RESEARCHER_DECLARED"
    assert conditions(report)["population_transport"]["status"] == "NOT_ASSESSED"


@pytest.mark.parametrize("field,value,expected", [
    ("log2_fold_change", -1.2, "UNSATISFIED"), ("log2_fold_change", "NaN", "NOT_ASSESSED"),
    ("ci_lower", -0.2, "UNSATISFIED"), ("ci_lower", 1.5, "CONFLICT"),
    ("ci_level", 0.80, "UNSATISFIED"), ("padj", 0.4, "UNSATISFIED"), ("padj", -0.1, "CONFLICT")])
def test_result_direction_uncertainty_and_significance(package, field, value, expected):
    change_table(package, "results.csv", lambda df: df.__setitem__(field, value))
    seal(package)
    checks = conditions(run(package))
    key = "effect_direction" if field == "log2_fold_change" else "adjusted_significance" if field == "padj" else "effect_uncertainty"
    assert checks[key]["status"] == expected


def test_missing_interval_is_not_invented_from_pvalue(package):
    change_table(package, "results.csv", lambda df: df.drop(columns=["ci_lower", "ci_upper"], inplace=True))
    seal(package)
    assert run(package)["status"] == "NOT_ASSESSED"


def test_shuffled_metadata_aligned_by_sample_identifier(package):
    df = pd.read_csv(package / "metadata.csv")
    df.iloc[::-1].to_csv(package / "metadata.csv", index=False)
    seal(package)
    assert run(package)["status"] == "SATISFIED"


@pytest.mark.parametrize("kind", ["reversed_contrast", "wrong_matrix", "duplicate_sample", "repeated_donor", "wrong_formula", "failed_fit"])
def test_adversarial_designs(package, kind):
    if kind == "reversed_contrast":
        change_json(package, "model.json", lambda m: m["contrast"].update(disease=-1))
        key, expected = "contrast_identity", "CONFLICT"
    elif kind == "wrong_matrix":
        change_table(package, "design.csv", lambda df: df.__setitem__("disease", [1, 1, 1, 0, 0, 0]))
        key, expected = "design_encoding", "CONFLICT"
    elif kind == "duplicate_sample":
        change_table(package, "metadata.csv", lambda df: df.__setitem__("sample", ["s0"] * 6))
        key, expected = "sample_alignment", "CONFLICT"
    elif kind == "repeated_donor":
        change_table(package, "metadata.csv", lambda df: df.__setitem__("donor", ["d0", "d1", "d2"] * 2))
        key, expected = "statistical_unit", "UNSATISFIED"
    elif kind == "wrong_formula":
        change_json(package, "model.json", lambda m: m.update(formula="~1+condition*batch"))
        key, expected = "design_encoding", "NOT_ASSESSED"
    else:
        change_json(package, "model.json", lambda m: m.update(fit_status="failed"))
        key, expected = "model_binding", "CONFLICT"
    seal(package)
    assert conditions(run(package))[key]["status"] == expected
    assert run(package)["status"] != "SATISFIED"


def test_paired_donor_fixed_effect_supported(package):
    change_table(package, "metadata.csv", lambda df: df.__setitem__("donor", ["d0", "d1", "d2"] * 2))
    change_table(package, "design.csv", lambda df: df.drop(columns=["batch_b"], inplace=True))
    design = pd.read_csv(package / "design.csv")
    design["donor_1"], design["donor_2"] = [0, 1, 0] * 2, [0, 0, 1] * 2
    design.to_csv(package / "design.csv", index=False)
    def paired(m):
        m.update(formula="~1+condition+donor", statistical_unit="paired_donor_fixed_effect",
                 design_columns=["Intercept", "disease", "donor_1", "donor_2"])
        del m["encodings"]["batch_b"]
        del m["contrast"]["batch_b"]
        for i in (1, 2):
            m["encodings"][f"donor_{i}"] = dict(kind="categorical", column="donor", level=f"d{i}")
            m["contrast"][f"donor_{i}"] = 0
    change_json(package, "model.json", paired)
    seal(package)
    assert run(package)["status"] == "SATISFIED"
    assert conditions(run(package))["statistical_unit"]["observed"]["unique_donors"] == 3


def test_tampering_and_input_substitution_are_conflicts(package):
    alternate = package / "alternate.csv"
    alternate.write_text("gene\nY\n")
    report = verify_de_claim_conditions(package / "contract.json", de_table=alternate)
    assert report["status"] == "CONFLICT"
    with (package / "results.csv").open("a") as stream:
        stream.write("\n")
    assert run(package)["status"] == "CONFLICT"


def test_file_deletion_missing_not_failed_science(package):
    (package / "metadata.csv").unlink()
    assert conditions(run(package))["artifact_metadata"]["status"] == "NOT_ASSESSED"


@pytest.mark.parametrize("path", ["../outside.csv", "C:/outside.csv"])
def test_package_paths_cannot_escape(package, path):
    change_json(package, "contract.json", lambda c: c["artifacts"]["results"].update(path=path))
    assert run(package)["status"] == "CONFLICT"


def test_duplicate_json_and_unsupported_schema_rejected(package):
    (package / "contract.json").write_text('{"schema_version":1,"schema_version":2}')
    with pytest.raises(ValueError, match="Duplicate"):
        run(package)


def test_distinct_genes_assessed_separately(package):
    def second(c):
        claim = copy.deepcopy(c["claims"][0])
        claim.update(claim_id="Y-T", gene="Y")
        c["claims"].append(claim)
    change_json(package, "contract.json", second)
    report = run(package)
    assert [c["status"] for c in report["claims"]] == ["SATISFIED", "NOT_ASSESSED"]


def test_causal_request_preserves_cohort_and_table_statements(package):
    change_json(package, "contract.json", lambda c: c["claims"][0].update(scope="causal_effect"))
    report = run(package)
    assert report["status"] == "NOT_ASSESSED"
    assert len(report["claims"][0]["supported_statements"]) == 2


def test_api_audit_and_reports_include_executable_conditions(package):
    from bionexus.de_audit import audit_differential_expression
    result = audit_differential_expression(de_table=package / "results.csv", sample_metadata=package / "metadata.csv",
                                          claim_contract=package / "contract.json")
    assert result.to_dict()["claim_conditions"]["status"] == "SATISFIED"
    assert "X-T" in result.to_markdown()
    assert "X-T" in result.summary_text(use_color=False)
    # A validated narrow contract does not override missing legacy execution evidence.
    assert not result.passed


def test_invalid_contract_blocks_audit(package):
    from bionexus.de_audit import audit_differential_expression
    (package / "contract.json").write_text("{}")
    result = audit_differential_expression(claim_contract=package / "contract.json")
    assert not result.passed
    assert any(c.check_id == "claim_conditions" and c.status.value == "PARSE_FAILED" for c in result.checks)


def test_cli_contract_bundle_roundtrip(package, capsys):
    from bionexus.cli import main
    from bionexus.de_bundle import verify_de_bundle
    bundle = package / "review"
    code = main(["audit-de", "--de-table", str(package / "results.csv"), "--sample-sheet", str(package / "metadata.csv"),
                 "--claim-contract", str(package / "contract.json"), "--bundle", str(bundle), "--json"])
    assert code == 1  # existing broader audit still lacks its execution evidence
    assert '"claim_conditions"' in capsys.readouterr().out
    assert json.loads((bundle / "audit.json").read_text(encoding="utf-8"))["claim_conditions"]["status"] == "SATISFIED"
    assert "X-T" in (bundle / "audit-full.md").read_text(encoding="utf-8")
    assert "未提供；当前仅审阅产物与证据缺口。" not in (bundle / "REVIEW.md").read_text(encoding="utf-8")
    assert verify_de_bundle(bundle)["status"] == "CONSISTENT"


@pytest.mark.parametrize("change,condition,expected", [
    ("duplicate_result", "result_identity", "CONFLICT"),
    ("wrong_cell_type", "result_identity", "NOT_ASSESSED"),
    ("empty_donor", "sample_alignment", "CONFLICT"),
    ("nonfinite_design", "contrast_estimability", "NOT_ASSESSED"),
    ("missing_contrast_weight", "contrast_estimability", "NOT_ASSESSED"),
    ("unsupported_unit", "model_binding", "NOT_ASSESSED"),
])
def test_additional_fail_closed_inputs(package, change, condition, expected):
    if change == "duplicate_result":
        df = pd.read_csv(package / "results.csv")
        pd.concat([df, df]).to_csv(package / "results.csv", index=False)
    elif change == "wrong_cell_type":
        change_table(package, "results.csv", lambda df: df.__setitem__("cell_type", "B"))
    elif change == "empty_donor":
        change_table(package, "metadata.csv", lambda df: df.__setitem__("donor", ""))
    elif change == "nonfinite_design":
        change_table(package, "design.csv", lambda df: df.__setitem__("disease", "inf"))
    elif change == "missing_contrast_weight":
        change_json(package, "model.json", lambda m: m["contrast"].pop("disease"))
    else:
        change_json(package, "model.json", lambda m: m.update(statistical_unit="cells_are_donors"))
    seal(package)
    report = run(package)
    assert conditions(report)[condition]["status"] == expected
    assert report["status"] != "SATISFIED"


def test_zero_residual_degrees_of_freedom_not_supported():
    result = contrast_diagnostics(np.eye(3), np.array([1, -1, 0]))
    assert result["estimable"] and result["full_rank"]
    assert result["residual_df"] == 0


def test_extreme_numeric_inputs_never_emit_nonfinite_diagnostics():
    result = contrast_diagnostics(np.array([[1e300, 0], [1e300, 1e300], [1e300, 0]]), np.array([0, 1e300]))
    assert result["estimable"]
    json.dumps(result, allow_nan=False)


def test_duplicate_table_columns_fail_closed(package):
    (package / "design.csv").write_text("sample_id,x,x\ns0,1,1\n")
    seal(package)
    report = run(package)
    assert conditions(report)["artifact_design"]["status"] == "NOT_ASSESSED"


@pytest.mark.parametrize("mutation", ["schema", "duplicate_ids", "same_groups", "boolean_alpha", "extra_flag"])
def test_contract_cannot_silently_accept_ambiguous_fields(package, mutation):
    def mutate(c):
        if mutation == "schema":
            c["schema_version"] = "future.v9"
        elif mutation == "duplicate_ids":
            c["claims"].append(copy.deepcopy(c["claims"][0]))
        elif mutation == "same_groups":
            c["analysis"]["denominator"] = c["analysis"]["numerator"]
        elif mutation == "boolean_alpha":
            c["claims"][0]["alpha"] = True
        else:
            c["is_confounded"] = False
    change_json(package, "contract.json", mutate)
    with pytest.raises(ValueError):
        run(package)


def test_contract_negative_findings_reach_audit_gate(package):
    from bionexus.de_audit import audit_differential_expression
    change_json(package, "model.json", lambda m: m["contrast"].update(disease=-1))
    seal(package)
    result = audit_differential_expression(claim_contract=package / "contract.json")
    assert not result.passed
    assert any(f.rule_id == "BFA-009" for f in result.findings)
    assert any(c.check_id == "claim_conditions:X-T" and c.required_for_pass for c in result.checks)


def test_anndata_metadata_cannot_be_replaced_by_contract_file(package):
    from types import SimpleNamespace

    from bionexus.de_audit import audit_differential_expression
    adata = SimpleNamespace(obs=pd.read_csv(package / "metadata.csv"), uns={})
    result = audit_differential_expression(adata=adata, sample_metadata=package / "metadata.csv",
                                          claim_contract=package / "contract.json")
    assert result.claim_conditions["status"] == "CONFLICT"


def test_shipped_examples_replay_with_identical_result_bytes():
    root = Path(__file__).resolve().parents[2] / "examples" / "de-claim-conditions"
    outputs = [verify_de_claim_conditions(root / name / "contract.json")
               for name in ("valid", "confounded", "missing-design")]
    assert [r["status"] for r in outputs] == ["SATISFIED", "UNSATISFIED", "NOT_ASSESSED"]
    results = [(root / name / "results.csv").read_bytes() for name in ("valid", "confounded", "missing-design")]
    assert results[0] == results[1] == results[2]
