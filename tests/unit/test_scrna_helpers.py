"""Subset, pseudobulk, and convert contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "single-cell-rna-qc" / "scripts"))

pytest.importorskip("anndata")
import anndata as ad
from scrna_convert import convert_to_h5ad
from scrna_inspect import inspect_adata
from scrna_pseudobulk import pseudobulk_counts
from scrna_subset import subset_adata


def _tiny():
    adata = ad.AnnData(np.arange(24, dtype=float).reshape(6, 4))
    adata.obs_names = [f"c{i}" for i in range(6)]
    adata.var_names = ["G1", "G2", "G3", "G4"]
    adata.obs["leiden"] = ["0", "0", "1", "1", "1", "1"]
    adata.obs["sample"] = ["s1", "s1", "s1", "s2", "s2", "s2"]
    adata.layers["counts"] = adata.X.copy()
    adata.obsm["X_umap"] = np.zeros((6, 2))
    return adata


def test_inspect_guesses_human_mt():
    adata = _tiny()
    adata.var_names = ["MT-CO1", "CD3D", "MS4A1", "CD14"]
    info = inspect_adata(adata)
    assert info["species_guess"] == "human"
    assert info["n_obs"] == 6


def test_subset_and_clear_embeddings():
    view, contract = subset_adata(
        _tiny(), obs_key="leiden", keep_values=["0"], clear_embeddings=True
    )
    assert view.n_obs == 2
    assert "X_umap" not in view.obsm
    assert contract["method"] == "anndata_subset"


def test_pseudobulk_sums_counts():
    table, design, contract = pseudobulk_counts(_tiny(), by=["sample", "leiden"])
    assert table.shape[0] == 3
    assert design.shape[0] == 3
    assert list(design.columns) == ["sample_id", "sample", "leiden"]
    assert design["sample_id"].nunique() == 3
    assert contract["n_pseudobulk_samples"] == 3
    assert "not a DE test" in contract["next"].lower() or "DE" in contract["next"]


def test_convert_rejects_rds():
    with pytest.raises(ValueError, match="rds"):
        convert_to_h5ad("obj.rds", "out.h5ad")
