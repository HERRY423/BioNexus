"""
Unit tests for Protein Language Models (pLM) suite:
Zero-shot variant effect Log-Likelihood Ratio (Delta LLR) and sequence embeddings.
"""

import pytest
import numpy as np
from pathlib import Path
import sys

# Add skill script directories to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "skills" / "protein-language-models" / "scripts"))

from plm_fitness_scorer import (
    score_variant_delta_llr
)
from protein_embedder import (
    embed_protein_sequence,
    compute_protein_similarity
)

# KRAS protein sequence (first 30 residues)
KRAS_WT = "MTEYKLVVVGAGGVGKSALTIQLIQNHFVD"


def test_plm_zero_shot_variant_fitness_scoring():
    """Test Log-Likelihood Ratio calculation for benign vs pathogenic mutations."""
    # G12D mutation (oncogenic driver in KRAS)
    res_damaging = score_variant_delta_llr(KRAS_WT, "G12D")
    assert res_damaging["mutation"] == "G12D"
    assert res_damaging["score"] < -1.0
    assert res_damaging["delta_llr"] is None
    assert res_damaging["score_kind"] == "blosum62_delta"
    assert "Deleterious" in res_damaging["predicted_effect"] or "Moderate" in res_damaging["predicted_effect"]
    assert res_damaging["method"] == "blosum62_substitution"
    assert res_damaging["acmg_computational_evidence"] == "abstain"

    # Conservative mutation G12A (more tolerated)
    res_tol = score_variant_delta_llr(KRAS_WT, "G12A")
    assert res_tol["score"] > res_damaging["score"]


def test_protein_sequence_embeddings_and_similarity():
    """Test dense fixed-dimension embedding extraction and semantic similarity."""
    emb = embed_protein_sequence(KRAS_WT, embedding_dim=128)
    assert len(emb) == 128
    assert np.isclose(np.linalg.norm(emb), 1.0, atol=1e-3)

    # Identical sequence similarity should be ~1.0
    sim_self = compute_protein_similarity(KRAS_WT, KRAS_WT)
    assert sim_self["cosine_similarity"] >= 0.99

    # Distant sequence
    distant_seq = "ACDEFGHIKLMNPQRSTVWY"
    sim_dist = compute_protein_similarity(KRAS_WT, distant_seq)
    assert sim_dist["cosine_similarity"] < 0.90
