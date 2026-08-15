"""Smoke test for the scvi-tools wrapper skill. Skips if scvi is not installed."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "scvi-tools" / "scripts"))


def test_scvi_model_utils_importable():
    pytest.importorskip("scvi")
    import model_utils

    assert hasattr(model_utils, "train_scvi") or hasattr(model_utils, "setup_anndata")


def test_scvi_one_epoch_smoke():
    pytest.importorskip("scvi")
    pytest.importorskip("anndata")
    import anndata as ad
    import numpy as np
    import scipy.sparse as sp

    sys.path.insert(0, str(PROJECT_ROOT / "skills" / "scvi-tools" / "scripts"))
    from scvi_smoke import run_scvi_smoke

    rng = np.random.default_rng(0)
    counts = rng.poisson(2, size=(40, 25)).astype(np.float32)
    adata = ad.AnnData(X=sp.csr_matrix(counts))
    adata.layers["counts"] = adata.X.copy()
    adata.obs_names = [f"c{i}" for i in range(40)]
    adata.var_names = [f"g{i}" for i in range(25)]
    contract = run_scvi_smoke(adata, max_epochs=1, n_latent=4)
    assert "X_scVI" in adata.obsm
    assert adata.obsm["X_scVI"].shape[1] == 4
    assert contract["method"] == "scvi.model.SCVI.train"
    assert contract["backend"] == "scvi-tools"
