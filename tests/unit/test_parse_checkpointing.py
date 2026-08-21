from __future__ import annotations

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from scripts.extract_parse_natural_pseudobulk import bounded_cell_id_chunks, bounded_exact_range_batches
from scripts.freeze_pseudobulk_blinded_packet import _blinded_adata_issues


def test_bounded_cell_id_chunks_preserve_exact_ordered_coverage():
    ids = np.array([50, 1, 2, 3, 20, 21, 22, 22, 100], dtype=np.int64)
    chunks = bounded_cell_id_chunks(ids, max_cells=3, max_span=10)
    observed = np.concatenate(chunks)
    assert np.array_equal(observed, np.unique(ids))
    assert all(len(chunk) <= 3 for chunk in chunks)
    assert all(int(chunk[-1] - chunk[0] + 1) <= 10 for chunk in chunks)


def test_bounded_cell_id_chunks_reject_invalid_limits():
    with pytest.raises(ValueError, match="must be positive"):
        bounded_cell_id_chunks(np.array([1]), max_cells=0, max_span=10)


def test_exact_range_batches_do_not_scan_numeric_gaps():
    ids = np.array([1, 2, 3, 1000, 1001, 5000, 5001, 5002], dtype=np.int64)
    batches = bounded_exact_range_batches(ids, max_cells=6, max_ranges=2, max_range_span=10)
    observed = np.concatenate([selected for selected, _ranges in batches])
    ranges = [item for _selected, batch_ranges in batches for item in batch_ranges]
    assert np.array_equal(observed, ids)
    assert ranges == [(1, 3), (1000, 1001), (5000, 5002)]
    assert all(len(batch_ranges) <= 2 for _selected, batch_ranges in batches)


def test_blinded_packet_gate_rejects_condition_semantics(tmp_path):
    obs = pd.DataFrame(
        {
            "opaque_subject_id": [f"S{i // 2:02d}" for i in range(24)],
            "opaque_arm_id": ["IFN-beta", "PBS"] * 12,
            "n_cells": [1] * 24,
        },
        index=[f"sample_{i}" for i in range(24)],
    )
    adata = ad.AnnData(X=sparse.csr_matrix(np.ones((24, 2), dtype=np.uint32)), obs=obs)
    path = tmp_path / "leaky.h5ad"
    adata.write_h5ad(path)
    issues = _blinded_adata_issues(path, expected_cells=24)
    assert any("leaks condition semantics" in issue for issue in issues)
