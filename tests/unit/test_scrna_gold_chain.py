"""Biological regressions for the scverse gold chain."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "single-cell-rna-qc" / "scripts"))

pytest.importorskip("scanpy")
pytest.importorskip("anndata")

import anndata as ad
from qc_core import calculate_qc_metrics_fast, detect_outliers_mad, filter_cells
from scrna_pipeline import run_scrna_gold_chain


def _planted_scrna(n_per=40, n_genes=80, seed=0):
    rng = np.random.default_rng(seed)
    n_cells = n_per * 3
    counts = rng.poisson(0.4, size=(n_cells, n_genes)).astype(np.float32)
    # Three nearly exclusive expression programs
    counts[:n_per, 10:22] += 40
    counts[n_per : 2 * n_per, 22:34] += 40
    counts[2 * n_per :, 34:46] += 40
    genes = [f"Gene_{i}" for i in range(n_genes)]
    genes[10], genes[22], genes[34] = "CD3D", "MS4A1", "CD14"
    genes[0] = "MT-CO1"
    obs_types = ["T"] * n_per + ["B"] * n_per + ["Mono"] * n_per
    adata = ad.AnnData(X=sp.csr_matrix(counts))
    adata.obs_names = [f"c{i}" for i in range(n_cells)]
    adata.var_names = genes
    adata.obs["true_type"] = obs_types
    adata.layers["counts"] = adata.X.copy()
    return adata


def test_mad_filters_injected_outlier():
    adata = _planted_scrna()
    calculate_qc_metrics_fast(adata)
    adata.obs.iloc[0, adata.obs.columns.get_loc("total_counts")] = 1e6
    outlier = detect_outliers_mad(adata, "total_counts", n_mads=3, verbose=False)
    assert bool(outlier[0]) is True
    kept = filter_cells(adata, ~outlier)
    assert "c0" not in set(kept.obs_names)
    assert kept.n_obs < adata.n_obs


def test_gold_chain_recovers_planted_markers():
    adata = _planted_scrna()
    out, markers, summary = run_scrna_gold_chain(adata, run_qc=False, n_top_genes=80, resolution=1.2, n_marker_genes=15)
    assert out.n_obs == 120
    assert "X_pca" in out.obsm
    assert "X_umap" in out.obsm
    key = summary["cluster_key"]
    assert key in out.obs
    assert summary["method"] == "scanpy_gold_chain"
    from sklearn.metrics import silhouette_score

    sil = float(silhouette_score(out.obsm["X_pca"][:, : min(10, out.obsm["X_pca"].shape[1])], out.obs["true_type"]))
    assert sil > 0.15, f"planted types are not separated in PCA (silhouette={sil:.3f})"
    name_col = "names" if "names" in markers.columns else None
    if name_col is None:
        for col in markers.columns:
            if col.lower() in {"names", "gene"}:
                name_col = col
                break
    top_names = set(markers[name_col].astype(str)) if name_col else set()
    assert {"CD3D", "MS4A1", "CD14"} & top_names, f"planted markers missing: {markers.head()}"
    joined = " ".join(summary["allowed_next_actions"]).lower()
    assert "celltypepilot" not in joined
    assert "pseudobulk" in joined or "numeric" in joined
    assert "handoff" not in summary
