"""Phase 2.6: pipeline config, default skill discovery, inspect depth, plots."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "single-cell-rna-qc" / "scripts"))

from bio_research.agent_routing import DEFAULT_SKILLS, discoverable_skill_names
from bio_research.pipeline_config import load_pipeline_config, merge_config


def test_merge_config_cli_wins():
    merged = merge_config({"resolution": 0.4, "n_top_genes": 1000}, {"resolution": 0.8, "n_top_genes": None})
    assert merged["resolution"] == 0.8
    assert merged["n_top_genes"] == 1000


def test_load_pipeline_config():
    path = PROJECT_ROOT / "tests" / "_tmp_pipeline_cfg.json"
    try:
        path.write_text(json.dumps({"resolution": 1.2, "run_qc": False}), encoding="utf-8")
        cfg = load_pipeline_config(path)
        assert cfg["resolution"] == 1.2
        assert cfg["run_qc"] is False
        with pytest.raises(FileNotFoundError):
            load_pipeline_config(PROJECT_ROOT / "tests" / "_tmp_pipeline_missing.json")
    finally:
        if path.exists():
            path.unlink()


def test_discoverable_skills_exclude_legacy():
    names = discoverable_skill_names(PROJECT_ROOT / "skills")
    assert "single-cell-rna-qc" in names
    assert "spatial-transcriptomics" in names
    assert "start" in names
    assert "biologics-design" not in names
    assert "variant-interpretation" not in names
    assert names == DEFAULT_SKILLS


def test_inspect_flags_loglike_and_batch_keys():
    pytest.importorskip("anndata")
    import anndata as ad
    from scrna_inspect import inspect_adata

    rng = np.random.default_rng(0)
    adata = ad.AnnData(X=rng.random((8, 6)))
    adata.var_names = ["MT-CO1", "G2", "G3", "G4", "G5", "G6"]
    adata.obs_names = [f"c{i}" for i in range(8)]
    adata.obs["batch"] = ["b1"] * 4 + ["b2"] * 4
    info = inspect_adata(adata)
    assert info["x_stats"]["likely_log_transformed"] is True
    assert "batch" in info["batch_key_candidates"]
    assert info["library_size"] is not None
    assert any("scVI" in a or "scvi" in a.lower() or "log" in a.lower() for a in info["allowed_next_actions"])


def test_plot_writes_stable_names():
    pytest.importorskip("scanpy")
    pytest.importorskip("anndata")
    import matplotlib

    matplotlib.use("Agg")
    import shutil
    import anndata as ad
    from scrna_plot import plot_processed

    out_dir = PROJECT_ROOT / "tests" / "_tmp_plot_figures"
    if out_dir.exists():
        shutil.rmtree(out_dir, ignore_errors=True)
    try:
        adata = ad.AnnData(np.arange(40, dtype=float).reshape(10, 4))
        adata.obs_names = [f"c{i}" for i in range(10)]
        adata.var_names = ["G1", "G2", "G3", "G4"]
        adata.obs["leiden"] = ["0"] * 5 + ["1"] * 5
        adata.obs["total_counts"] = np.linspace(100, 400, 10)
        adata.obs["n_genes_by_counts"] = np.linspace(10, 40, 10)
        adata.obsm["X_umap"] = np.column_stack([np.linspace(0, 1, 10), np.linspace(1, 0, 10)])
        report = plot_processed(adata, str(out_dir), color="leiden", genes=["G1"])
        names = {Path(p).name for p in report["figures"]}
        assert "umap_leiden.png" in names
        assert "dotplot_markers.png" in names
        assert "violin_qc.png" in names
        for path in report["figures"]:
            assert Path(path).is_file()
    finally:
        if out_dir.exists():
            shutil.rmtree(out_dir, ignore_errors=True)
