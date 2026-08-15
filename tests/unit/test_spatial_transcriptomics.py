"""
Unit tests for Spatial Transcriptomics analysis suite:
preprocessing, spatial-aware clustering, spot deconvolution, niche analysis, and Moran's I SVGs.
"""

import pytest
import numpy as np
import pandas as pd
import anndata as ad
from scipy import sparse
from pathlib import Path
import sys
import tempfile
import os

# Add skill script directories to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "skills" / "spatial-transcriptomics" / "scripts"))

from spatial_preprocessing import (
    calculate_spatial_qc_metrics,
    filter_spatial_spots,
    normalize_spatial_coordinates
)
from spatial_clustering import (
    build_fused_spatial_graph,
    smooth_spatial_domains,
    run_spatial_clustering
)
from spatial_deconvolution import (
    build_reference_signature,
    deconvolve_spatial_spots
)
from spatial_niche_analysis import (
    identify_spatial_niches,
    compute_spatial_colocalization,
    evaluate_ligand_receptor_spatial_signaling
)
from spatial_variable_genes import (
    compute_spatial_weights_matrix,
    calculate_morans_i_vectorized,
    detect_spatially_variable_genes
)
from spatial_visualization import (
    plot_spatial_discrete,
    plot_spatial_continuous,
    generate_interactive_html
)


@pytest.fixture
def synthetic_spatial_adata():
    """Create a 100-spot 2D grid dataset with known spatial patterns."""
    np.random.seed(42)
    n_spots = 100
    n_genes = 50

    # 10x10 coordinate grid
    coords = np.array([(i % 10, i // 10) for i in range(n_spots)], dtype=float)

    # Base counts
    counts = np.random.poisson(lam=5.0, size=(n_spots, n_genes)).astype(float)

    # Inject spatial pattern in Gene_0 (high on left side)
    left_mask = coords[:, 0] < 5
    counts[left_mask, 0] += 50.0

    # Gene names
    gene_names = [f"Gene_{j}" for j in range(n_genes)]
    gene_names[1] = "MT-CO1"
    gene_names[2] = "CD274"  # Ligand (PD-L1)
    gene_names[3] = "PDCD1"  # Receptor (PD-1)

    obs = pd.DataFrame({
        "in_tissue": [1] * n_spots,
        "sample_id": ["slice_1"] * n_spots
    }, index=[f"spot_{i}" for i in range(n_spots)])

    var = pd.DataFrame(index=gene_names)

    adata = ad.AnnData(X=sparse.csr_matrix(counts), obs=obs, var=var)
    adata.obsm["spatial"] = coords
    return adata


@pytest.fixture
def synthetic_sc_reference():
    """Create a single-cell reference dataset with 3 distinct cell types."""
    np.random.seed(123)
    n_cells = 90
    n_genes = 50
    gene_names = [f"Gene_{j}" for j in range(n_genes)]
    gene_names[1] = "MT-CO1"
    gene_names[2] = "CD274"
    gene_names[3] = "PDCD1"

    counts = np.random.poisson(lam=3.0, size=(n_cells, n_genes)).astype(float)
    cell_types = ["Tumor_cell"] * 30 + ["T_cell"] * 30 + ["Macrophage"] * 30

    # Marker gene enrichment
    counts[:30, 4] += 30.0   # Tumor marker
    counts[30:60, 3] += 30.0 # T cell marker (PDCD1)
    counts[60:90, 5] += 30.0 # Macrophage marker

    obs = pd.DataFrame({"cell_type": cell_types}, index=[f"cell_{i}" for i in range(n_cells)])
    var = pd.DataFrame(index=gene_names)
    return ad.AnnData(X=sparse.csr_matrix(counts), obs=obs, var=var)


def test_spatial_preprocessing_and_qc(synthetic_spatial_adata):
    """Test spatial QC metric calculation and filtering."""
    summary = calculate_spatial_qc_metrics(synthetic_spatial_adata)
    assert summary["n_spots"] == 100
    assert "total_counts" in synthetic_spatial_adata.obs
    assert "pct_counts_mt" in synthetic_spatial_adata.obs
    assert "spatial_neighbor_dist" in synthetic_spatial_adata.obs

    adata_filt = filter_spatial_spots(synthetic_spatial_adata, min_counts=10, min_genes=5)
    assert adata_filt.n_obs > 0
    normalize_spatial_coordinates(adata_filt)
    assert "spatial_normalized" in adata_filt.obsm


def test_spatial_clustering(synthetic_spatial_adata):
    """Test fused spatial-transcriptomic graph clustering and MRF smoothing."""
    calculate_spatial_qc_metrics(synthetic_spatial_adata)
    summary = run_spatial_clustering(
        synthetic_spatial_adata,
        n_clusters=4,
        spatial_weight=0.4,
        smooth_iterations=1
    )
    assert summary["n_clusters"] == 4
    assert "spatial_domain" in synthetic_spatial_adata.obs
    assert len(synthetic_spatial_adata.obs["spatial_domain"].cat.categories) <= 4


def test_spatial_deconvolution(synthetic_spatial_adata, synthetic_sc_reference):
    """Test spot-level cell type deconvolution against scRNA reference."""
    sig_df, markers = build_reference_signature(synthetic_sc_reference, cell_type_col="cell_type")
    assert len(sig_df.columns) == 3
    assert len(markers) > 0

    prop_df = deconvolve_spatial_spots(synthetic_spatial_adata, sig_df, marker_genes=markers)
    assert prop_df.shape == (100, 3)
    # Proportions should sum approximately to 1
    row_sums = prop_df.sum(axis=1)
    np.testing.assert_allclose(row_sums, 1.0, rtol=1e-3)
    assert "dominant_cell_type" in synthetic_spatial_adata.obs


def test_spatial_niche_and_lr_signaling(synthetic_spatial_adata, synthetic_sc_reference):
    """Test microenvironment niche clustering and ligand-receptor interaction potential."""
    sig_df, markers = build_reference_signature(synthetic_sc_reference, cell_type_col="cell_type")
    deconvolve_spatial_spots(synthetic_spatial_adata, sig_df, marker_genes=markers)

    niches = identify_spatial_niches(synthetic_spatial_adata, n_niches=3)
    assert len(niches) == 3
    assert "spatial_niche" in synthetic_spatial_adata.obs

    coloc = compute_spatial_colocalization(synthetic_spatial_adata)
    assert coloc.shape == (3, 3)

    lr_df = evaluate_ligand_receptor_spatial_signaling(synthetic_spatial_adata)
    assert isinstance(lr_df, pd.DataFrame)
    if not lr_df.empty:
        assert "total_interaction_score" in lr_df.columns


def test_spatial_variable_genes_morans_i(synthetic_spatial_adata):
    """Test Moran's I spatial autocorrelation and ranking."""
    svg_df = detect_spatially_variable_genes(synthetic_spatial_adata, top_n=10)
    assert len(svg_df) > 0
    assert "morans_i" in svg_df.columns
    assert "fdr_q_value" in svg_df.columns
    # Gene_0 was injected with spatial pattern -> should have high Moran's I
    gene_0_res = svg_df[svg_df["gene"] == "Gene_0"]
    assert len(gene_0_res) == 1
    assert gene_0_res["morans_i"].values[0] > 0.3


def test_spatial_visualization_and_html(synthetic_spatial_adata):
    """Test figure generation and standalone interactive HTML export."""
    calculate_spatial_qc_metrics(synthetic_spatial_adata)
    run_spatial_clustering(synthetic_spatial_adata, n_clusters=3)

    with tempfile.TemporaryDirectory() as tmp_dir:
        plot_discrete_path = os.path.join(tmp_dir, "domains.png")
        plot_continuous_path = os.path.join(tmp_dir, "feature.png")
        html_path = os.path.join(tmp_dir, "atlas.html")

        plot_spatial_discrete(synthetic_spatial_adata, output_path=plot_discrete_path)
        plot_spatial_continuous(synthetic_spatial_adata, feature_name="total_counts", output_path=plot_continuous_path)
        generate_interactive_html(synthetic_spatial_adata, output_path=html_path)

        assert os.path.exists(plot_discrete_path)
        assert os.path.exists(plot_continuous_path)
        assert os.path.exists(html_path)
        with open(html_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "BioNexus Spatial Transcriptomics Atlas" in content
