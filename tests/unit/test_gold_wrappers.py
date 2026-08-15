"""2.7.0 gold wrappers: scrublet, pydeseq2, spatial table, launch, narrative."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "single-cell-rna-qc" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "spatial-transcriptomics" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "nextflow-development" / "scripts"))

from bio_research.gate import DoctorGateError, _enforce_ready


def test_default_scrna_skill_does_not_recommend_soupx():
    text = (PROJECT_ROOT / "skills" / "single-cell-rna-qc" / "SKILL.md").read_text(encoding="utf-8")
    assert "Approach 1: Complete QC Pipeline (Recommended)" not in text
    assert "qc_analysis.py" in text
    assert "grade C" in text.lower() or "heuristics" in text.lower()
    assert "scrna_pipeline.py" in text
    assert "scanpy.pp.scrublet" in text


def test_skip_doctor_still_enforces_scverse():
    with pytest.raises(DoctorGateError, match="scanpy"):
        _enforce_ready({"tier": "degraded", "ready": {"scverse_ready": False}}, require_scverse=True, require_spatial=False)
    with pytest.raises(DoctorGateError, match="squidpy"):
        _enforce_ready({"tier": "full", "ready": {"spatial_ready": False}}, require_scverse=False, require_spatial=True)


def test_spatialdata_multi_table_requires_key():
    pytest.importorskip("anndata")
    import anndata as ad
    from spatial_io import _table_from_spatialdata

    class Fake:
        tables = {
            "left": ad.AnnData(np.ones((3, 2))),
            "right": ad.AnnData(np.ones((4, 2))),
        }

    with pytest.raises(ValueError, match="multiple tables"):
        _table_from_spatialdata(Fake())
    picked = _table_from_spatialdata(Fake(), table_key="left")
    assert picked.n_obs == 3
    assert picked.uns["spatialdata_table"] == "left"


def test_scrublet_names_official_api_or_refuses():
    pytest.importorskip("scanpy")
    pytest.importorskip("anndata")
    import anndata as ad
    import scipy.sparse as sp
    from scrna_scrublet import run_scrublet

    rng = np.random.default_rng(0)
    counts = rng.poisson(3, size=(80, 60)).astype(np.float32)
    adata = ad.AnnData(X=sp.csr_matrix(counts))
    adata.layers["counts"] = adata.X.copy()
    _, contract = run_scrublet(adata)
    if contract.get("abstain"):
        assert contract["method"] == "scanpy.pp.scrublet"
        reason = (contract.get("abstain_reason") or "") + " ".join(contract.get("limitations") or [])
        assert "scDblFinder" in reason or "missing" in reason.lower() or "counts" in reason.lower()
    else:
        assert contract["method"] == "scanpy.pp.scrublet"
        assert contract["backend"] == "scanpy"
        assert "doublet_score" in adata.obs or "predicted_doublet" in adata.obs


def test_pydeseq2_recovers_planted_gene():
    pytest.importorskip("pydeseq2")
    from scrna_deseq import run_pydeseq2

    rng = np.random.default_rng(1)
    genes = [f"g{i}" for i in range(20)]
    samples = [f"s{i}" for i in range(8)]
    cond = ["A"] * 4 + ["B"] * 4
    mat = rng.poisson(20, size=(8, 20)).astype(int)
    mat[4:, 0] += 80
    counts = pd.DataFrame(mat, index=samples, columns=genes)
    design = pd.DataFrame({"sample_id": samples, "condition": cond})
    table, contract = run_pydeseq2(counts, design, condition="condition", reference="A", contrast_level="B")
    assert contract["method"] == "pydeseq2.DeseqStats"
    assert "padj" in table.columns or "pvalue" in table.columns
    top = table.sort_values("pvalue").head(5)["gene"].astype(str).tolist()
    assert "g0" in top


def test_nfcore_launch_writes_script_and_rejects_unknown_pipeline():
    from nfcore_launch import build_launch_command, write_launch_script

    with pytest.raises(ValueError, match="rnaseq"):
        build_launch_command(pipeline="sarek", samplesheet="s.csv", outdir="out")
    cmd = build_launch_command(pipeline="rnaseq", samplesheet="s.csv", outdir="results")
    assert cmd[:3] == ["nextflow", "run", "nf-core/rnaseq"]
    dest = PROJECT_ROOT / "tests" / "_tmp_nfcore_run.sh"
    try:
        write_launch_script(cmd, dest)
        text = dest.read_text(encoding="utf-8")
        assert "nf-core/rnaseq" in text
        assert "--input s.csv" in text
    finally:
        if dest.exists():
            dest.unlink()


def test_spatial_scatter_writes_stable_name():
    pytest.importorskip("squidpy")
    pytest.importorskip("anndata")
    import matplotlib

    matplotlib.use("Agg")
    import anndata as ad
    import shutil
    from spatial_plot import plot_spatial

    n = 16
    coords = np.array([(i % 4, i // 4) for i in range(n)], dtype=float)
    adata = ad.AnnData(np.ones((n, 5)))
    adata.obsm["spatial"] = coords
    adata.obs["leiden"] = ["0"] * 8 + ["1"] * 8
    out = PROJECT_ROOT / "tests" / "_tmp_spatial_figs"
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)
    try:
        report = plot_spatial(adata, str(out), color="leiden")
        assert report["method"] == "squidpy.pl.spatial_scatter"
        assert (out / "spatial_leiden.png").is_file()
    finally:
        if out.exists():
            shutil.rmtree(out, ignore_errors=True)
