"""Synthetic artifact checks; these receipts do not attest to a real DE fit."""
import hashlib

import numpy as np
import pandas as pd
import pytest

from bionexus.de.rules.table_rules import _audit_de_table
from bionexus.de_audit import audit_differential_expression


def _audit(tmp_path, pvalues, adjusted, claim=None):
    table = tmp_path / "results.csv"
    pd.DataFrame({"gene": [f"G{i}" for i in range(len(pvalues))],
                  "log2FoldChange": [1.5] * len(pvalues),
                  "pvalue": pvalues, "padj": adjusted}).to_csv(table, index=False)
    donors = [f"D{i}" for i in range(6)]
    receipt = {"statistical_unit": "donor", "method": "pydeseq2",
               "fit_status": "CONVERGED", "design": "~ condition",
               "design_matrix_columns": ["Intercept", "condition[T.T]"],
               "n_donors": 6, "donor_ids": donors,
               "result_sha256": hashlib.sha256(table.read_bytes()).hexdigest()}
    return audit_differential_expression(
        sample_metadata=pd.DataFrame({"donor_id": donors, "condition": ["Control"] * 3 + ["Disease"] * 3}),
        de_table=table, execution_record=receipt, claim_text=claim)


@pytest.mark.parametrize("claim", [None, "No genes were significant after FDR correction."])
@pytest.mark.parametrize("pvalues,adjusted", [
    ([np.nan, np.nan], [np.nan, np.nan]),
    ([.01, .02], [np.nan, np.nan]),
    ([np.nan, np.nan], [.04, .05]),
    (["oops", "oops"], ["oops", "oops"]),
    ([.01, .02], [.04, "oops"]),
    ([float("inf"), .02], [.04, .05]),
    ([.01, .02], [float("-inf"), .05]),
    ([-.01, .02], [.04, .05]),
    ([.01, .02], [1.1, .05]),
])
def test_unusable_probabilities_never_pass(tmp_path, pvalues, adjusted, claim):
    result = _audit(tmp_path, pvalues, adjusted, claim)
    assert not result.passed
    assert result.overall_status != "ROBUST_PASS"
    check = next(c for c in result.checks if c.check_id == "fdr_and_testing")
    assert check.status.value != "ASSESSED"
    assert check.required_for_pass


@pytest.mark.parametrize("pvalues,adjusted", [
    ([.01, .02], [.04, .05]),
    ([.01, np.nan], [.04, np.nan]),
    ([.01, .02], [.04, np.nan]),
    ([0., 1.], [0., 1.]),
    (["0.01", "0.02"], ["0.04", "0.05"]),
])
def test_estimable_values_and_partial_na_keep_valid_path(tmp_path, pvalues, adjusted):
    result = _audit(tmp_path, pvalues, adjusted)
    assert result.passed, result.to_dict()
    check = next(c for c in result.checks if c.check_id == "fdr_and_testing")
    assert "missing=" in check.summary


def test_in_memory_numeric_strings_use_numeric_comparisons_without_mutation():
    table = pd.DataFrame({"pvalue": ["0.01"] * 101, "padj": ["0.9"] * 101})
    original = table.copy(deep=True)
    findings, decisions, checks = [], [], []
    _audit_de_table(table, findings, decisions, checks)
    assert any(f.rule_id == "BFA-003b" for f in findings)
    pd.testing.assert_frame_equal(original, table)


def test_boolean_probabilities_are_not_numeric_estimates():
    findings, decisions, checks = [], [], []
    _audit_de_table(pd.DataFrame({"pvalue": [True], "padj": [False]}), findings, decisions, checks)
    assert checks[0].status.value == "PARSE_FAILED"


@pytest.mark.parametrize("column", ["pvalue", "padj"])
@pytest.mark.parametrize("value", [.03 + .2j, 1j, .03 + 0j])
def test_complex_probabilities_are_not_real_estimates(column, value):
    table = pd.DataFrame({"pvalue": [.02], "padj": [.04]})
    table[column] = [value]
    findings, decisions, checks = [], [], []
    _audit_de_table(table, findings, decisions, checks)
    assert checks[0].status.value == "PARSE_FAILED"
    assert checks[0].required_for_pass


@pytest.mark.parametrize("column", ["pvalue", "padj"])
@pytest.mark.parametrize("value", [np.bool_(True), np.bool_(False)])
def test_numpy_booleans_in_mixed_object_column_are_rejected(column, value):
    table = pd.DataFrame({"pvalue": [.02, .03, None], "padj": [.04, .06, None]})
    table[column] = pd.Series([.04, value, None], dtype=object)
    findings, decisions, checks = [], [], []
    _audit_de_table(table, findings, decisions, checks)
    assert checks[0].status.value == "PARSE_FAILED"
    assert checks[0].required_for_pass
