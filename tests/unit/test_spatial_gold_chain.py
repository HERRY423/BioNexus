"""squidpy spatial gold chain regressions."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import scipy.sparse as sp

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "spatial-transcriptomics" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "tests" / "fixtures"))

pytest.importorskip("squidpy")
pytest.importorskip("anndata")

import anndata as ad
from make_tiny import write_tiny_spatial
from spatial_inspect import inspect_spatial
from spatial_io import resolve_spatial_key
from spatial_pipeline import run_spatial_gold_chain


def _planted_spatial():
    n_side = 8
    n_genes = 30
    rng = np.random.default_rng(2)
    n_spots = n_side * n_side
    coords = np.array([(i % n_side, i // n_side) for i in range(n_spots)], dtype=float)
    counts = rng.poisson(1.0, size=(n_spots, n_genes)).astype(np.float32)
    left = coords[:, 0] < 4
    counts[left, 0] += 50
    genes = [f"Gene_{j}" for j in range(n_genes)]
    genes[0] = "SVG_LEFT"
    adata = ad.AnnData(X=sp.csr_matrix(counts))
    adata.obs_names = [f"spot_{i}" for i in range(n_spots)]
    adata.var_names = genes
    adata.obsm["spatial"] = coords
    adata.layers["counts"] = adata.X.copy()
    return adata


def test_inspect_requires_spatial_coords():
    adata = ad.AnnData(np.ones((4, 3)))
    with pytest.raises(ValueError, match="spatial"):
        resolve_spatial_key(adata)


def test_inspect_reports_coords():
    adata = _planted_spatial()
    report = inspect_spatial(adata)
    assert report["spatial_key"] == "spatial"
    assert report["n_obs"] == 64
    assert report["method"] == "spatial_inspect"


def test_squidpy_gold_chain_recovers_planted_svg():
    adata = _planted_spatial()
    out, svg, summary = run_spatial_gold_chain(adata, cluster=False, top_n=10, n_neighs=6)
    assert summary["method"] == "squidpy_spatial_gold_chain"
    assert summary["backend"] == "squidpy"
    assert summary["graph"] in {
        "squidpy.gr.spatial_neighbors_knn",
        "squidpy.gr.spatial_neighbors",
    }
    assert "morans_i" in svg.columns
    assert "fdr_q_value" in svg.columns
    top = set(svg.head(5)["gene"].astype(str))
    assert "SVG_LEFT" in top
    left_i = float(svg.loc[svg["gene"] == "SVG_LEFT", "morans_i"].iloc[0])
    assert left_i > 0.3
    fixture = PROJECT_ROOT / "tests" / "fixtures" / "tiny_spatial.h5ad"
    if not fixture.is_file():
        fixture = write_tiny_spatial(fixture)
    assert fixture.stat().st_size < 5 * 1024 * 1024


def test_gold_chain_refuses_without_coords():
    adata = ad.AnnData(np.ones((8, 6)))
    with pytest.raises(ValueError, match="spatial"):
        run_spatial_gold_chain(adata, cluster=False)
