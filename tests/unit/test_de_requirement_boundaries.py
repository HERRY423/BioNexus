"""Numerical counterexamples for the bounded DE requirement profile."""
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from bionexus.integrity import ScientificInputError, require_counts_layer, require_raw_count_matrix


def test_actual_counts_accept_integer_valued_float_and_sparse_inputs():
    counts = np.array([[0., 2.], [3., 0.]])
    for matrix in (counts, sparse.csr_matrix(counts)):
        assert require_raw_count_matrix(matrix)["integer_counts_verified"] is True


def test_actual_counts_reject_negative_nonfinite_and_transformed_values():
    for bad in (-1., float("nan"), float("inf"), 0.25):
        counts = np.ones((20, 20))
        counts[-1, -1] = bad
        for matrix in (counts, sparse.csr_matrix(counts)):
            with pytest.raises(ScientificInputError):
                require_raw_count_matrix(matrix)


def test_explicit_counts_layer_is_returned_without_substitution():
    counts = np.array([[1, 2], [3, 4]])
    data = SimpleNamespace(layers={"counts": counts}, X=np.log1p(counts))
    assert require_counts_layer(data) is counts


def test_missing_counts_layer_never_substitutes_even_integer_x():
    data = SimpleNamespace(layers={}, X=np.array([[1, 2], [3, 4]]))
    with pytest.raises(ScientificInputError, match="refusing to substitute"):
        require_counts_layer(data)
