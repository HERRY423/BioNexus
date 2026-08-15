"""
Unit tests for Multiome Integration & Gene Regulatory Network suite:
WNN joint integration, peak-gene linking, motif enrichment, SCENIC+ regulons, AUCell, and TF footprinting.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add skill script directories to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "skills" / "multiome-integration" / "scripts"))

from grn_inference import calculate_aucell_activity, infer_tf_target_coexpression, prune_grn_with_cis_motifs
from joint_rna_atac import integrate_rna_atac_wnn
from motif_enrichment import calculate_motif_enrichment_in_peaks, compute_per_cell_motif_deviation
from peak_gene_linking import calculate_peak_gene_correlations
from regulatory_visualization import export_grn_to_cytoscape_json
from tf_footprinting import compute_tf_footprint_profile


@pytest.fixture
def synthetic_multiome_data():
    """Create paired synthetic single-cell RNA (100 cells x 20 genes) and ATAC (100 cells x 30 peaks)."""
    np.random.seed(42)
    n_cells = 100
    n_genes = 20
    n_peaks = 30

    rna = np.random.poisson(lam=4.0, size=(n_cells, n_genes)).astype(float)
    atac = (np.random.poisson(lam=0.5, size=(n_cells, n_peaks)) > 0).astype(float)

    # Correlate Peak_0 with Gene_0 (Enhancer link)
    atac[:, 0] = (rna[:, 0] > np.median(rna[:, 0])).astype(float)

    gene_names = [f"Gene_{i}" for i in range(n_genes)]
    gene_names[0] = "TP53"
    gene_names[1] = "CDK4"
    gene_names[2] = "MDM2"

    return rna, atac, gene_names


def test_wnn_joint_integration(synthetic_multiome_data):
    """Test WNN multi-modal graph and joint latent representation."""
    rna, atac, _ = synthetic_multiome_data
    res = integrate_rna_atac_wnn(rna, atac, n_rna_pcs=5, n_atac_lsi=5, k_neighbors=10, n_clusters=3)
    assert res["n_cells"] == 100
    assert 0.0 < res["mean_rna_weight"] < 1.0
    assert res["joint_latent"].shape[0] == 100
    assert len(res["joint_clusters"]) == 100


def test_peak_gene_cis_linking(synthetic_multiome_data):
    """Test peak-to-gene correlation calculation."""
    rna, atac, gene_names = synthetic_multiome_data
    gene_annot = [{"name": g, "chrom": "chr1", "tss": 10000 + i * 5000, "index": i} for i, g in enumerate(gene_names)]
    peak_annot = [{"peak_id": f"chr1:{10000+j*5000}", "chrom": "chr1", "center": 10200 + j * 5000, "index": j} for j in range(30)]

    links_df = calculate_peak_gene_correlations(
        rna, atac, gene_annot, peak_annot,
        max_distance_bp=50000, min_correlation=0.20, max_p_value=0.05
    )
    assert isinstance(links_df, pd.DataFrame)
    if not links_df.empty:
        assert "correlation_r" in links_df.columns
        assert "regulatory_type" in links_df.columns


def test_motif_enrichment_and_chromvar_deviation():
    """Test Fisher's exact motif enrichment and per-cell deviation scores."""
    n_peaks = 50
    n_motifs = 3
    tf_names = ["TP53", "SOX2", "GATA3"]

    peak_motif_mat = (np.random.rand(n_peaks, n_motifs) > 0.6).astype(float)
    target_indices = np.array([0, 1, 2, 3, 4, 5])

    enrich_df = calculate_motif_enrichment_in_peaks(peak_motif_mat, target_indices, tf_names)
    assert len(enrich_df) == 3
    assert "odds_ratio" in enrich_df.columns
    assert "p_value" in enrich_df.columns

    atac_mat = np.random.poisson(1.0, size=(20, n_peaks)).astype(float)
    dev_df = compute_per_cell_motif_deviation(atac_mat, peak_motif_mat, tf_names)
    assert dev_df.shape == (20, 3)


def test_grn_inference_and_aucell(synthetic_multiome_data):
    """Test SCENIC+ style co-expression inference and AUCell activity scoring."""
    rna, _, gene_names = synthetic_multiome_data
    tf_names = ["TP53"]

    coexpr_df = infer_tf_target_coexpression(rna, gene_names, tf_names, min_importance=0.01)
    assert isinstance(coexpr_df, pd.DataFrame)
    if not coexpr_df.empty:
        assert "importance" in coexpr_df.columns

    dummy_peaks_df = pd.DataFrame([
        {"gene_symbol": "CDK4", "peak_id": "peak_1"},
        {"gene_symbol": "MDM2", "peak_id": "peak_2"}
    ])
    regulons = prune_grn_with_cis_motifs(coexpr_df, dummy_peaks_df, {"TP53": ["peak_1", "peak_2"]})
    assert isinstance(regulons, dict)

    sample_regulons = {
        "TP53(+)": {
            "tf": "TP53",
            "targets": ["CDK4", "MDM2"],
            "target_details": [
                {"target_gene": "CDK4", "importance": 0.3, "mode": "Activator (+)"},
                {"target_gene": "MDM2", "importance": 0.25, "mode": "Activator (+)"}
            ]
        }
    }
    auc_df = calculate_aucell_activity(rna, gene_names, sample_regulons)
    assert auc_df.shape == (100, 1)
    assert "TP53(+)" in auc_df.columns

    # Test Cytoscape export
    cyto = export_grn_to_cytoscape_json(sample_regulons, output_path="test_grn.json")
    assert len(cyto["nodes"]) >= 3
    assert len(cyto["edges"]) >= 2
    if Path("test_grn.json").exists():
        Path("test_grn.json").unlink()


def test_tf_footprinting_profile():
    """Test transcription factor footprint depth and CPI calculation."""
    # Synthetic aggregation profile with deep dip at center 0
    cuts = np.ones(201) * 20.0
    cuts[90:111] = 4.0  # Protected footprint core [-10, +10]

    footprint = compute_tf_footprint_profile(cuts, window_size=100)
    assert footprint["chromatin_protection_index"] > 0.60
    assert "Active Chromatin Binding" in footprint["binding_status"]
