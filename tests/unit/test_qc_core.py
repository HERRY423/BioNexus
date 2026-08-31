"""
Unit tests for Single-Cell RNA-seq QC module.
Tests vectorized sparse calculations, MAD outlier filtering, doublet detection, and ambient RNA correction.
"""

import numpy as np
import pytest

pytest.importorskip("anndata", reason="single-cell QC test requires anndata")

from ambient_rna import correct_ambient_rna
from doublet_detection import run_doublet_detection, simulate_doublets
from qc_core import apply_hard_threshold, calculate_qc_metrics_chunked, calculate_qc_metrics_fast, detect_outliers_mad


def test_calculate_qc_metrics_fast(synthetic_anndata):
    """Test vectorized metric calculation on sparse matrix."""
    adata = synthetic_anndata.copy()
    calculate_qc_metrics_fast(adata, inplace=True)

    assert "total_counts" in adata.obs
    assert "n_genes_by_counts" in adata.obs
    assert "pct_counts_mt" in adata.obs
    assert "pct_counts_ribo" in adata.obs
    assert "pct_counts_hb" in adata.obs

    # Check metrics sanity
    assert (adata.obs["total_counts"] >= 0).all()
    assert (adata.obs["n_genes_by_counts"] >= 0).all()
    assert (adata.obs["pct_counts_mt"] >= 0).all()
    assert (adata.obs["pct_counts_mt"] <= 100).all()


def test_calculate_qc_metrics_chunked(synthetic_anndata):
    """Test chunked QC processing for large-scale / backed data."""
    adata = synthetic_anndata.copy()
    calculate_qc_metrics_chunked(adata, chunk_size=50)

    assert "total_counts" in adata.obs
    assert "n_genes_by_counts" in adata.obs
    assert "pct_counts_mt" in adata.obs
    assert len(adata.obs["total_counts"]) == adata.n_obs


def test_detect_outliers_mad(synthetic_anndata):
    """Test MAD-based outlier detection."""
    adata = synthetic_anndata.copy()
    calculate_qc_metrics_fast(adata, inplace=True)

    # Intentionally inject an outlier
    adata.obs.iloc[0, adata.obs.columns.get_loc("total_counts")] = 100000.0

    mask = detect_outliers_mad(adata, "total_counts", n_mads=3, verbose=False)
    assert isinstance(mask, np.ndarray)
    assert mask[0]  # The injected outlier should be detected


def test_apply_hard_threshold(synthetic_anndata):
    """Test hard thresholding."""
    adata = synthetic_anndata.copy()
    adata.obs["pct_counts_mt"] = np.array([5.0, 12.0, 2.0] * (adata.n_obs // 3))

    mask = apply_hard_threshold(adata, "pct_counts_mt", 10.0, operator=">", verbose=False)
    assert mask.sum() == (adata.n_obs // 3)


def test_doublet_detection_simulation(synthetic_sparse_counts):
    """Test synthetic doublet generation."""
    sim_matrix, pairs = simulate_doublets(synthetic_sparse_counts, sim_doublet_ratio=1.5)
    expected_n = int(synthetic_sparse_counts.shape[0] * 1.5)
    assert sim_matrix.shape[0] == expected_n
    assert sim_matrix.shape[1] == synthetic_sparse_counts.shape[1]
    assert pairs.shape == (expected_n, 2)


def test_run_doublet_detection(synthetic_anndata):
    """Test end-to-end doublet detection pipeline on AnnData."""
    adata = synthetic_anndata.copy()
    adata, summary = run_doublet_detection(adata, expected_doublet_rate=0.05)

    assert "doublet_score" in adata.obs
    assert "predicted_doublet" in adata.obs
    assert 0.0 <= summary["doublet_threshold"] <= 1.0
    assert summary["n_cells_total"] == adata.n_obs


def test_ambient_rna_correction(synthetic_anndata):
    """Test ambient RNA profile estimation and background subtraction."""
    adata = synthetic_anndata.copy()
    adata, summary = correct_ambient_rna(adata, contamination_rate=0.05)

    assert "ambient_contamination_fraction" in adata.obs
    assert "ambient_corrected" in adata.layers
    assert summary["mean_contamination_fraction"] == 0.05
    assert summary["total_umi_removed"] >= 0
