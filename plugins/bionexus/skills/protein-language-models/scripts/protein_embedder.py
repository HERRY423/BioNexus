#!/usr/bin/env python3
"""Sequence embeddings.

Default path is a deterministic k-mer + random-projection vector. It is not
an ESM embedding. If transformers ESM is explicitly enabled, mean-pool ESM-2.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Any, Dict

import numpy as np
from _common import GRADE_A, GRADE_C, attach_meta, is_available

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("ProteinEmbedder")

AMINO_ACIDS = "ACDEFGHIKLMNPQRSTVWY"
AA_TO_IDX = {aa: i for i, aa in enumerate(AMINO_ACIDS)}


def _kmer_projection(sequence: str, embedding_dim: int) -> np.ndarray:
    seq = sequence.strip().upper()
    if not seq:
        return np.zeros(embedding_dim, dtype=float)
    comp = np.array([seq.count(aa) / len(seq) for aa in AMINO_ACIDS])
    dipeptides = np.zeros(400)
    for i in range(len(seq) - 1):
        pair = seq[i : i + 2]
        if pair[0] in AA_TO_IDX and pair[1] in AA_TO_IDX:
            dipeptides[AA_TO_IDX[pair[0]] * 20 + AA_TO_IDX[pair[1]]] += 1
    if len(seq) > 1:
        dipeptides /= len(seq) - 1
    feat = np.concatenate([comp, dipeptides])
    rng = np.random.default_rng(42)
    proj = rng.normal(0, 1.0 / np.sqrt(420), size=(420, embedding_dim))
    emb = feat @ proj
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    return emb


def embed_protein_sequence(sequence: str, embedding_dim: int = 128) -> np.ndarray:
    """Return a dense vector. See last-call metadata via compute_protein_similarity."""
    return _kmer_projection(sequence, embedding_dim)


def compute_protein_similarity(seq_a: str, seq_b: str) -> Dict[str, Any]:
    use_esm = os.environ.get("BIONEXUS_ALLOW_ESM", "").strip() in {"1", "true", "TRUE"} and is_available("esm")
    if use_esm:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            model_id = os.environ.get("BIONEXUS_ESM_MODEL", "facebook/esm2_t6_8M_UR50D")
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            model = AutoModel.from_pretrained(model_id)
            model.eval()
            vecs = []
            for seq in (seq_a, seq_b):
                enc = tokenizer(seq, return_tensors="pt")
                with torch.no_grad():
                    hidden = model(**enc).last_hidden_state[0, 1:-1].mean(dim=0)
                vecs.append(hidden.cpu().numpy())
            emb_a, emb_b = vecs
            method, backend, grade = "esm2_mean_pool", "transformers", GRADE_A
        except Exception as exc:
            logger.warning("ESM embedding failed (%s); using k-mer projection.", exc)
            emb_a = embed_protein_sequence(seq_a)
            emb_b = embed_protein_sequence(seq_b)
            method, backend, grade = "kmer_random_projection", "numpy", GRADE_C
    else:
        emb_a = embed_protein_sequence(seq_a)
        emb_b = embed_protein_sequence(seq_b)
        method, backend, grade = "kmer_random_projection", "numpy", GRADE_C

    na, nb = np.linalg.norm(emb_a), np.linalg.norm(emb_b)
    cos_sim = float(np.dot(emb_a, emb_b) / (na * nb)) if na > 0 and nb > 0 else 0.0
    payload = {
        "sequence_a_length": len(seq_a),
        "sequence_b_length": len(seq_b),
        "cosine_similarity": round(cos_sim, 4),
        "functional_homology": (
            "High compositional similarity"
            if cos_sim >= 0.75
            else ("Moderate compositional similarity" if cos_sim >= 0.50 else "Low compositional similarity")
        ),
    }
    return attach_meta(
        payload,
        method=method,
        backend=backend,
        evidence_grade=grade,
        limitations=[
            "k-mer projection is not an ESM latent space and is not homology proof."
            if method == "kmer_random_projection"
            else "Mean-pooled ESM-2 embedding; cosine is not a phylogenetic distance."
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Protein sequence embedding / similarity")
    parser.add_argument("--seq1", "-a", required=True)
    parser.add_argument("--seq2", "-b")
    args = parser.parse_args()
    if args.seq2:
        print(json.dumps(compute_protein_similarity(args.seq1, args.seq2), indent=2))
    else:
        emb = embed_protein_sequence(args.seq1)
        print(
            json.dumps(
                {"length": len(args.seq1), "embedding_dim": len(emb), "embedding_norm": float(np.linalg.norm(emb))},
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
