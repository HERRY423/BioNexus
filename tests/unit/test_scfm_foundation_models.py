"""
Unit tests for BioNexus Single-Cell Foundation Model (scFM) interfaces: Geneformer & scGPT (bionexus.scfm).
"""

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from bionexus.abi import capability_abis, get_capability_abi
from bionexus.capabilities import CANONICAL_CAPABILITIES
from bionexus.intent_router import route_scientific_intent
from bionexus.scfm import (
    FoundationModelFamily,
    SCFMConfig,
    SCFMEmbeddingResult,
    SCFMPerturbationResult,
    check_scfm_backend,
    extract_scfm_embeddings,
    rank_value_encode,
    scgpt_tokenize_and_bin,
    simulate_gene_perturbation,
)


@pytest.fixture
def synthetic_sc_adata():
    """Create synthetic single-cell expression matrix with distinct marker levels."""
    np.random.seed(42)
    n_cells = 40
    genes = [f"Gene_{i}" for i in range(1, 21)]  # 20 genes

    X = np.random.poisson(lam=1.5, size=(n_cells, len(genes))).astype(np.float32)
    # Plant distinct expression gradients
    X[:, 0] = 50.0  # Gene_1 highest
    X[:, 1] = 25.0  # Gene_2 second highest
    X[:, 2] = 10.0  # Gene_3 third

    adata = ad.AnnData(
        X=sparse.csr_matrix(X),
        obs=pd.DataFrame({"cell_type": ["T_cell"] * 20 + ["B_cell"] * 20}, index=[f"cell_{i}" for i in range(n_cells)]),
        var=pd.DataFrame(index=genes),
    )
    return adata


def test_rank_value_encode(synthetic_sc_adata):
    """Verify Geneformer rank-value encoding sorts non-zero genes by expression descending."""
    tokens, counts = rank_value_encode(synthetic_sc_adata, max_seq_len=10)

    assert len(tokens) == 40
    assert len(counts) == 40
    assert counts[0] > 0
    # Gene_1 must be ranked first (index 0) because expression was highest (50.0)
    assert tokens[0][0] == "Gene_1"
    assert tokens[0][1] == "Gene_2"
    assert tokens[0][2] == "Gene_3"


def test_scgpt_tokenize_and_bin(synthetic_sc_adata):
    """Verify scGPT expression binning discretizes values into 1..n_bins."""
    tokens, bins = scgpt_tokenize_and_bin(synthetic_sc_adata, n_bins=51, max_seq_len=10)

    assert len(tokens) == 40
    assert len(bins) == 40
    assert len(tokens[0]) == len(bins[0])
    assert max(bins[0]) <= 51
    assert min(bins[0]) >= 1


def test_extract_embeddings_geneformer(synthetic_sc_adata):
    """Verify Geneformer cell embedding extraction stores matrix in adata.obsm['X_geneformer']."""
    cfg = SCFMConfig(model_family=FoundationModelFamily.GENEFORMER, embedding_dim=128)
    res = extract_scfm_embeddings(synthetic_sc_adata, config=cfg, allow_fallback=True)

    assert res.success is True
    assert res.n_cells == 40
    assert res.embedding_dim == 128
    assert "X_geneformer" in synthetic_sc_adata.obsm
    assert synthetic_sc_adata.obsm["X_geneformer"].shape == (40, 128)


def test_extract_embeddings_scgpt(synthetic_sc_adata):
    """Verify scGPT cell embedding extraction stores matrix in adata.obsm['X_scgpt']."""
    cfg = SCFMConfig(model_family=FoundationModelFamily.SCGPT, embedding_dim=64)
    res = extract_scfm_embeddings(synthetic_sc_adata, config=cfg, allow_fallback=True)

    assert res.success is True
    assert res.n_cells == 40
    assert res.embedding_dim == 64
    assert "X_scgpt" in synthetic_sc_adata.obsm
    assert synthetic_sc_adata.obsm["X_scgpt"].shape == (40, 64)


def test_simulate_gene_perturbation_knockout(synthetic_sc_adata):
    """Verify in silico knockout perturbation measures non-zero embedding shift vector."""
    res = simulate_gene_perturbation(
        adata=synthetic_sc_adata,
        target_gene="Gene_1",
        mode="knockout",
        cell_type_col="cell_type",
        allow_fallback=True,
    )

    assert res.success is True
    assert res.target_gene == "Gene_1"
    assert res.perturbation_mode == "knockout"
    assert res.n_cells_evaluated == 40
    assert res.mean_displacement_magnitude > 0.0
    assert len(res.top_displaced_cells) > 0
    assert res.cell_type_shift_summary is not None
    assert "T_cell" in res.cell_type_shift_summary


def test_simulate_gene_perturbation_refusal_missing_gene(synthetic_sc_adata):
    """Verify fail-closed refusal when target gene is not found in dataset."""
    res = simulate_gene_perturbation(
        adata=synthetic_sc_adata,
        target_gene="NonExistentGene_XYZ",
        mode="knockout",
    )
    assert res.success is False
    assert res.status == "REFUSAL_TARGET_GENE_NOT_FOUND"


def test_scfm_refusal_empty_and_zero_matrix():
    """Verify fail-closed refusal on empty or all-zero matrix."""
    empty_adata = ad.AnnData(X=np.zeros((0, 0)))
    res = extract_scfm_embeddings(empty_adata)
    assert res.success is False
    assert res.status == "REFUSAL_EMPTY_DATASET"

    zero_adata = ad.AnnData(X=np.zeros((10, 10)), var=pd.DataFrame(index=[f"G_{i}" for i in range(10)]))
    res2 = extract_scfm_embeddings(zero_adata)
    assert res2.success is False
    assert res2.status == "REFUSAL_ALL_ZERO_MATRIX"


def test_scfm_capabilities_registered_and_abi_projection():
    """Verify Geneformer and scGPT are registered in CANONICAL_CAPABILITIES and project to ABI."""
    assert "scfm.geneformer_inference" in CANONICAL_CAPABILITIES
    assert "scfm.scgpt_inference" in CANONICAL_CAPABILITIES

    abis = capability_abis()
    assert "scfm.geneformer_inference" in abis
    assert "scfm.scgpt_inference" in abis

    gf_abi = get_capability_abi("scfm.geneformer_inference")
    assert gf_abi.evidence_ceiling.without_external_validation == "PRELIMINARY"
    assert "clinical_diagnosis" in gf_abi.forbidden_claims

    scgpt_abi = get_capability_abi("scfm.scgpt_inference")
    assert scgpt_abi.evidence_ceiling.without_external_validation == "PRELIMINARY"


def test_scfm_intent_routing():
    """Verify user queries about Geneformer, scGPT, or in silico knockout route to scfm capabilities."""
    res1 = route_scientific_intent("Please extract zero-shot cell embeddings using geneformer foundation model")
    assert res1.matched_capability is not None
    assert res1.matched_capability.id == "scfm.geneformer_inference"

    res2 = route_scientific_intent("simulate in silico knockout of TP53 using single-cell foundation model")
    assert res2.matched_capability is not None
    assert res2.matched_capability.id == "scfm.geneformer_inference"

    res3 = route_scientific_intent("extract cell representations with scgpt foundation model")
    assert res3.matched_capability is not None
    assert res3.matched_capability.id == "scfm.scgpt_inference"
