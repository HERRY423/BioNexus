"""
Unit tests for BioNexus Single-Cell Foundation Model (scFM) interfaces: Geneformer & scGPT (bionexus.scfm).

Verifies strict compliance with BioNexus Epistemic Honesty (BNS-EF-002 / BNS-CC-012):
- Canonical Transformer execution with genuine neural network forward pass.
- Fail-closed refusal when canonical model checkpoint is missing.
- Transparent Grade C attribution for Rank-Weighted SVD proxy (no heuristic masquerading).
"""

import anndata as ad
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from bionexus.abi import capability_abis, get_capability_abi
from bionexus.intent_router import route_scientific_intent
from bionexus.scfm import (
    FoundationModelFamily,
    SCFMConfig,
    extract_rank_proxy_embeddings,
    extract_scfm_embeddings,
    rank_value_encode,
    run_geneformer_canonical_forward,
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


def test_fail_closed_refusal_when_checkpoint_missing(synthetic_sc_adata):
    """
    CRITICAL INVARIANT (BNS-EF-002):
    When canonical foundation model is requested without a checkpoint and allow_proxy_fallback=False,
    BioNexus MUST refuse (REFUSAL_MODEL_CHECKPOINT_REQUIRED) and NEVER silently run a proxy!
    """
    cfg = SCFMConfig(model_family=FoundationModelFamily.GENEFORMER, model_name_or_path=None)
    res = extract_scfm_embeddings(synthetic_sc_adata, config=cfg, allow_proxy_fallback=False)

    assert res.success is False
    assert res.status == "REFUSAL_MODEL_CHECKPOINT_REQUIRED"
    assert res.backend_used == "none"
    assert "strictly requires an official model checkpoint" in res.remedy_if_failed
    assert "BNS-EF-002" in res.remedy_if_failed


def test_scgpt_canonical_not_implemented_refusal(synthetic_sc_adata):
    """
    CRITICAL INVARIANT (BNS-EF-002):
    When scGPT canonical inference is requested without explicit fallback,
    BioNexus MUST refuse honestly with REFUSAL_CANONICAL_BACKEND_NOT_IMPLEMENTED
    since scGPT canonical checkpoint integration is under frontier development.
    """
    cfg = SCFMConfig(model_family=FoundationModelFamily.SCGPT, model_name_or_path="scgpt_checkpoint")
    res = extract_scfm_embeddings(synthetic_sc_adata, config=cfg, allow_proxy_fallback=False)

    assert res.success is False
    assert res.status == "REFUSAL_CANONICAL_BACKEND_NOT_IMPLEMENTED"
    assert res.backend_used == "none"
    assert "under frontier development" in res.remedy_if_failed


def test_scgpt_proxy_fallback_honest_attribution(synthetic_sc_adata):
    """
    Verify that when scGPT falls back to SVD proxy with allow_proxy_fallback=True,
    the backend is labeled as heuristic SVD proxy and NEVER scgpt-pytorch.
    """
    cfg = SCFMConfig(model_family=FoundationModelFamily.SCGPT)
    res = extract_scfm_embeddings(synthetic_sc_adata, config=cfg, allow_proxy_fallback=True)

    assert res.success is True
    assert res.status == "COMPLETED_PROXY_EXPERIMENTAL"
    assert res.backend_used == "heuristic-rank-svd-proxy (Grade C Heuristic)"
    assert "scgpt-pytorch" not in res.backend_used
    assert "X_scgpt" in synthetic_sc_adata.obsm


def test_canonical_geneformer_transformer_execution(synthetic_sc_adata):
    """
    Verify genuine Transformer neural network forward pass when model is loaded.
    Tests token tensor preparation, attention mask, and mean-pooled hidden state extraction.
    """
    try:
        import torch.nn as nn
    except ImportError:
        pytest.skip("PyTorch not installed")

    # Mock lightweight transformer model with actual nn.Embedding and linear layers
    class MockGeneformerTransformer(nn.Module):
        def __init__(self, vocab_size=100, hidden_dim=64):
            super().__init__()
            self.emb = nn.Embedding(vocab_size, hidden_dim)
            self.transformer = nn.TransformerEncoderLayer(d_model=hidden_dim, nhead=2, batch_first=True)

        def forward(self, input_ids, attention_mask, output_hidden_states=True):
            x = self.emb(input_ids)
            # Create boolean mask where False is valid and True is padded
            pad_mask = (attention_mask == 0)
            out = self.transformer(x, src_key_padding_mask=pad_mask)
            return type("ModelOutput", (), {"last_hidden_state": out, "hidden_states": [out]})()

    mock_model = MockGeneformerTransformer(vocab_size=100, hidden_dim=64)
    tokens, _ = rank_value_encode(synthetic_sc_adata, max_seq_len=10)

    # Run genuine forward pass
    embeds = run_geneformer_canonical_forward(
        model=mock_model,
        token_sequences=tokens,
        token_dict=None,
        device="cpu",
        max_seq_len=10,
        embedding_dim=64,
        batch_size=16,
    )

    assert embeds.shape == (40, 64)
    assert not np.isnan(embeds).any()
    assert np.std(embeds) > 0.0  # Real non-trivial embeddings generated


def test_rank_proxy_embedding_grade_c_attribution(synthetic_sc_adata):
    """
    CRITICAL INVARIANT (BNS-EF-002 / BNS-CC-012):
    When the rank-weighted SVD proxy is run, it MUST:
    1. Honestly identify backend as 'heuristic-rank-svd-proxy (Grade C Heuristic)'.
    2. Set is_canonical=False and status='COMPLETED_PROXY_EXPERIMENTAL'.
    3. Include explicit Grade C / proxy disclaimers in execution notes.
    4. Store embeddings in obsm['X_rank_proxy'].
    """
    res = extract_rank_proxy_embeddings(synthetic_sc_adata, embedding_dim=128)

    assert res.success is True
    assert res.status == "COMPLETED_PROXY_EXPERIMENTAL"
    assert res.is_canonical is False
    assert res.backend_used == "heuristic-rank-svd-proxy (Grade C Heuristic)"
    assert res.obsm_key == "X_rank_proxy"
    assert "X_rank_proxy" in synthetic_sc_adata.obsm
    assert synthetic_sc_adata.obsm["X_rank_proxy"].shape == (40, 128)

    # Check for mandatory disclaimers
    disclaimer_found = any("Grade C experimental rank-weighted SVD proxy" in note for note in res.execution_notes)
    assert disclaimer_found is True

    # MUST NOT claim to be geneformer-pytorch or scgpt-pytorch
    assert "geneformer-pytorch" not in res.backend_used
    assert "scgpt-pytorch" not in res.backend_used


def test_simulate_gene_perturbation_knockout(synthetic_sc_adata):
    """Verify in silico knockout perturbation measures non-zero embedding shift vector."""
    res = simulate_gene_perturbation(
        adata=synthetic_sc_adata,
        target_gene="Gene_1",
        mode="knockout",
        cell_type_col="cell_type",
        allow_proxy_fallback=True,
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
    """Verify Geneformer, scGPT, and Rank Proxy capabilities are registered in FRONTIER_CAPABILITIES and ALL_CAPABILITIES."""
    from bionexus.capabilities import ALL_CAPABILITIES, FRONTIER_CAPABILITIES

    assert "scfm.geneformer_canonical" in FRONTIER_CAPABILITIES
    assert "scfm.scgpt_canonical" in FRONTIER_CAPABILITIES
    assert "scfm.rank_proxy_embedding" in FRONTIER_CAPABILITIES
    assert "scfm.geneformer_canonical" in ALL_CAPABILITIES

    abis = capability_abis(include_frontier=True)
    assert "scfm.geneformer_canonical" in abis
    assert "scfm.scgpt_canonical" in abis
    assert "scfm.rank_proxy_embedding" in abis

    gf_abi = get_capability_abi("scfm.geneformer_canonical")
    assert gf_abi.evidence_ceiling.without_external_validation == "PRELIMINARY"
    assert "model_substitution" in gf_abi.forbidden_claims
    assert "clinical_diagnosis" in gf_abi.forbidden_claims

    proxy_abi = get_capability_abi("scfm.rank_proxy_embedding")
    assert proxy_abi.evidence_ceiling.without_external_validation == "PRELIMINARY"
    assert "model_substitution" in proxy_abi.forbidden_claims


def test_scfm_intent_routing():
    """Verify user queries route accurately to canonical vs proxy capabilities."""
    res1 = route_scientific_intent("extract cell embeddings with geneformer foundation model")
    assert res1.matched_capability is not None
    assert res1.matched_capability.id == "scfm.geneformer_canonical"

    res2 = route_scientific_intent("extract single cell representation using scgpt")
    assert res2.matched_capability is not None
    assert res2.matched_capability.id == "scfm.scgpt_canonical"

    res3 = route_scientific_intent("calculate rank-value SVD embedding proxy for exploratory visualization")
    assert res3.matched_capability is not None
    assert res3.matched_capability.id == "scfm.rank_proxy_embedding"
