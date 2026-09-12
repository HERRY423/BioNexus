"""Counterexamples for the passive DE reader without optional AnnData runtimes."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from bionexus.de_audit import CheckStatus, audit_differential_expression


@pytest.mark.parametrize("batches,confounded", [
    (["b1"] * 6, False),
    (["b1"] * 3 + ["b2"] * 3, True),
    (["b1", "b1", "b2", "b3", "b3", "b4"], True),
    (["b1", "b2", "b1", "b1", "b2", "b2"], False),
])
def test_batch_confounding_requires_batch_to_identify_condition(batches, confounded):
    metadata = pd.DataFrame({"donor_id": list("abcdef"),
                             "condition": ["control"] * 3 + ["treated"] * 3,
                             "batch": batches})
    result = audit_differential_expression(sample_metadata=metadata)
    assert any(f.rule_id == "BFA-004" for f in result.findings) is confounded


def test_unused_cell_type_category_is_not_an_observed_cluster():
    metadata = pd.DataFrame({"donor_id": list("abcdef"),
                             "condition": ["control"] * 3 + ["treated"] * 3,
                             "cell_type": pd.Categorical(["T"] * 6, categories=["T", "unused"])})
    result = audit_differential_expression(sample_metadata=metadata)
    assert not any(c.status == CheckStatus.PARSE_FAILED for c in result.checks)


def audit_matrix(matrix, **extra):
    data = SimpleNamespace(X=matrix, layers={}, raw=None, uns={},
                           obs=pd.DataFrame({"donor": ["d1", "d2", "d3", "d4"],
                                             "condition": ["a", "a", "b", "b"]}))
    for key, value in extra.items():
        setattr(data, key, value)
    result = audit_differential_expression(adata=data)
    check = next(c for c in result.checks if c.check_id == "input_count_type")
    return result, check


@pytest.mark.parametrize("bad", [-1., 0.25, float("nan"), float("inf")])
@pytest.mark.parametrize("as_sparse", [False, True])
def test_invalid_value_after_diagnostic_sample_is_never_a_pass(bad, as_sparse):
    counts = np.ones((4, 2000))
    counts[-1, -1] = bad
    result, check = audit_matrix(sparse.csr_matrix(counts) if as_sparse else counts)
    assert check.status == CheckStatus.ISSUE_FOUND
    assert any(f.rule_id == "BFA-002" for f in result.findings)
    assert not result.passed


@pytest.mark.parametrize("where", ["counts", "raw_layer", "raw"])
def test_layer_name_does_not_prove_valid_counts(where):
    matrix = np.full((4, 2), 0.3)
    extra = {"raw": SimpleNamespace(X=matrix)} if where == "raw" else {
        "layers": {"raw" if where == "raw_layer" else "counts": matrix}}
    _, check = audit_matrix(matrix, **extra)
    assert check.status == CheckStatus.ISSUE_FOUND


def test_invalid_explicit_counts_do_not_fall_back_to_integer_x():
    _, check = audit_matrix(np.ones((4, 2)), layers={"counts": np.full((4, 2), -1)})
    assert check.status == CheckStatus.ISSUE_FOUND


def test_valid_counts_layer_is_identified_without_claiming_analysis_used_it():
    _, check = audit_matrix(np.full((4, 2), 0.3), layers={"counts": np.ones((4, 2))})
    assert check.status == CheckStatus.ASSESSED
    assert "layers['counts']" in check.summary


def test_missing_matrix_is_not_assessed():
    _, check = audit_matrix(None)
    assert check.status == CheckStatus.MISSING_EVIDENCE


def test_empty_matrix_is_not_count_evidence():
    _, check = audit_matrix(np.empty((4, 0)))
    assert check.status == CheckStatus.ISSUE_FOUND
