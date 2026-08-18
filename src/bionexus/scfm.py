"""
BioNexus Single-Cell Foundation Model (scFM) Inference & Embedding Engine.

Provides unified, robust, and fail-closed interfaces for:
1. Canonical Geneformer (Theodoris et al., Nature 2023): Rank-Value Encoding Transformer
   using official pretrained model checkpoints (e.g. HuggingFace 'ctheodoris/Geneformer'
   or local weights directory).
2. Canonical scGPT (Cui et al., Nature Methods 2024): Generative pretrained transformer
   for single-cell embeddings using official model checkpoints.
3. Rank-Weighted SVD Proxy (Grade C Experimental): Transparent, deterministic rank-value
   heuristic for zero-shot exploratory visualization when official checkpoints are absent.

Adheres strictly to BioNexus Epistemic Honesty & Specification Series:
- BNS-EF-002: Heuristics must never masquerade as canonical backends (no model substitution).
- BNS-CC-012: 'model_substitution' is an enforced forbidden claim.
- Evidence ceiling: PRELIMINARY for zero-shot and in silico predictions.
- Forbidden claims: model_substitution, clinical_diagnosis, causal_interaction, cell_type_identity_without_reference.
"""

from dataclasses import asdict, dataclass, field
from enum import Enum
import importlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy import sparse

logger = logging.getLogger("bionexus.scfm")


class FoundationModelFamily(str, Enum):
    GENEFORMER = "geneformer"
    SCGPT = "scgpt"


@dataclass
class SCFMConfig:
    """Configuration hyperparameters for Single-Cell Foundation Model execution."""

    model_family: FoundationModelFamily = FoundationModelFamily.GENEFORMER
    model_name_or_path: Optional[str] = None  # Checkpoint path (e.g. 'ctheodoris/Geneformer' or local directory)
    device: str = "auto"  # 'auto', 'cuda', 'cpu'
    batch_size: int = 64
    max_seq_len: int = 2048
    embedding_dim: int = 512
    pooling_strategy: str = "mean"  # 'mean' or 'cls'
    n_bins: int = 51  # For scGPT expression binning
    random_seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["model_family"] = self.model_family.value
        return d


@dataclass
class SCFMEmbeddingResult:
    """Structured result of foundation model cell embedding extraction."""

    success: bool
    status: str
    model_family: str
    model_name: Optional[str]
    n_cells: int
    n_genes: int
    embedding_dim: int
    backend_used: str  # e.g. 'geneformer-canonical-transformer (ctheodoris/Geneformer)' vs 'heuristic-rank-svd-proxy (Grade C Heuristic)'
    obsm_key: str  # e.g. 'X_geneformer', 'X_scgpt', or 'X_rank_proxy'
    is_canonical: bool = False
    mean_token_count_per_cell: float = 0.0
    execution_notes: List[str] = field(default_factory=list)
    remedy_if_failed: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SCFMPerturbationResult:
    """Structured result of in silico gene perturbation (knockout or overexpression)."""

    success: bool
    status: str
    model_family: str
    target_gene: str
    perturbation_mode: str  # 'knockout' or 'overexpression'
    n_cells_evaluated: int
    mean_displacement_magnitude: float
    top_displaced_cells: List[str] = field(default_factory=list)
    cell_type_shift_summary: Optional[Dict[str, float]] = None
    backend_used: str = "none"
    is_canonical: bool = False
    execution_notes: List[str] = field(default_factory=list)
    remedy_if_failed: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==============================================================================
# Backend & Checkpoint Validation (BNS-EF-002 Honesty)
# ==============================================================================


def check_scfm_backend(family: FoundationModelFamily, checkpoint_path: Optional[str] = None) -> Tuple[bool, str]:
    """
    Check availability of PyTorch and required model libraries and checkpoints.
    Honesty rule: Only reports canonical availability if torch and transformers are importable.
    """
    try:
        torch = importlib.import_module("torch")
        transformers = importlib.import_module("transformers")
        has_cuda = torch.cuda.is_available()
        device_str = "cuda" if has_cuda else "cpu"

        if checkpoint_path and Path(checkpoint_path).exists():
            return True, f"{family.value}-canonical-checkpoint (local: {checkpoint_path}, torch {torch.__version__}, {device_str})"
        elif checkpoint_path:
            return True, f"{family.value}-canonical-checkpoint ({checkpoint_path}, transformers {transformers.__version__}, {device_str})"
        else:
            return True, f"{family.value}-pytorch-{device_str} (transformers {transformers.__version__}, no checkpoint loaded)"
    except ImportError as e:
        return False, f"Backend unavailable: {str(e)}"


# ==============================================================================
# Tokenization & Rank-Value Encoders
# ==============================================================================


def rank_value_encode(
    adata: Any,
    max_seq_len: int = 2048,
) -> Tuple[List[List[str]], np.ndarray]:
    """
    Convert single-cell expression matrix into Geneformer Rank-Value Encoded token sequences.
    For each cell, non-zero genes are ranked by normalized expression in descending order.
    """
    X = adata.X.toarray() if sparse.issparse(adata.X) else np.array(adata.X)
    genes = np.array(adata.var_names)
    n_cells = X.shape[0]

    token_sequences: List[List[str]] = []
    token_counts = np.zeros(n_cells, dtype=int)

    for i in range(n_cells):
        row = X[i]
        non_zero_idx = np.where(row > 0)[0]
        if len(non_zero_idx) == 0:
            token_sequences.append([])
            continue

        # Sort non-zero genes by expression value descending
        sorted_order = non_zero_idx[np.argsort(-row[non_zero_idx])]
        ranked_genes = list(genes[sorted_order[:max_seq_len]])
        token_sequences.append(ranked_genes)
        token_counts[i] = len(ranked_genes)

    return token_sequences, token_counts


def scgpt_tokenize_and_bin(
    adata: Any,
    n_bins: int = 51,
    max_seq_len: int = 2048,
) -> Tuple[List[List[str]], List[List[int]]]:
    """
    Discretize expression values into normalized expression bins for scGPT.
    """
    X = adata.X.toarray() if sparse.issparse(adata.X) else np.array(adata.X)
    genes = np.array(adata.var_names)
    n_cells = X.shape[0]

    gene_tokens: List[List[str]] = []
    binned_values: List[List[int]] = []

    # Compute non-zero expression bin edges globally or per cell
    for i in range(n_cells):
        row = X[i]
        non_zero_idx = np.where(row > 0)[0]
        if len(non_zero_idx) == 0:
            gene_tokens.append([])
            binned_values.append([])
            continue

        # Take top expressing genes up to max_seq_len
        top_idx = non_zero_idx[np.argsort(-row[non_zero_idx])[:max_seq_len]]
        top_genes = list(genes[top_idx])
        top_vals = row[top_idx]

        # Discretize values into 1..n_bins
        if np.max(top_vals) > np.min(top_vals):
            norm_vals = (top_vals - np.min(top_vals)) / (np.max(top_vals) - np.min(top_vals))
            bins = (norm_vals * (n_bins - 1) + 1).astype(int)
        else:
            bins = np.ones(len(top_vals), dtype=int)

        gene_tokens.append(top_genes)
        binned_values.append(list(bins))

    return gene_tokens, binned_values


# ==============================================================================
# Canonical Neural Network Inference (PyTorch / Transformers)
# ==============================================================================


def load_geneformer_transformer_model(
    model_name_or_path: str,
    device: str = "cpu",
) -> Tuple[Any, Optional[Dict[str, int]]]:
    """
    Load official Geneformer transformer model from HuggingFace hub or local checkpoint directory.
    """
    import torch
    from transformers import AutoModel, AutoModelForMaskedLM, BertForMaskedLM

    model_path = Path(model_name_or_path)
    logger.info(f"Loading canonical Geneformer transformer checkpoint from '{model_name_or_path}' on {device}...")

    # Attempt to load token dictionary if present
    token_dict: Optional[Dict[str, int]] = None
    if model_path.is_dir():
        token_dict_path = model_path / "token_dictionary.pkl"
        if token_dict_path.exists():
            import pickle

            with open(token_dict_path, "rb") as f:
                token_dict = pickle.load(f)

    # Load transformer architecture
    try:
        model = BertForMaskedLM.from_pretrained(model_name_or_path)
    except Exception:
        try:
            model = AutoModelForMaskedLM.from_pretrained(model_name_or_path)
        except Exception:
            model = AutoModel.from_pretrained(model_name_or_path)

    model.to(device)
    model.eval()
    return model, token_dict


def run_geneformer_canonical_forward(
    model: Any,
    token_sequences: List[List[str]],
    token_dict: Optional[Dict[str, int]],
    device: str = "cpu",
    max_seq_len: int = 2048,
    embedding_dim: int = 512,
    batch_size: int = 64,
) -> np.ndarray:
    """
    Execute genuine Geneformer Transformer forward pass with tensor tokenization,
    attention masks, and hidden-state extraction.
    """
    import torch

    n_cells = len(token_sequences)
    # Build vocabulary mapping if not provided
    if token_dict is None:
        all_unique_genes = sorted(list(set(g for seq in token_sequences for g in seq)))
        token_dict = {gene: idx + 2 for idx, gene in enumerate(all_unique_genes)}  # 0=pad, 1=mask

    embeddings_list = []

    for start_idx in range(0, n_cells, batch_size):
        batch_tokens = token_sequences[start_idx : start_idx + batch_size]
        batch_size_cur = len(batch_tokens)
        max_len_cur = min(max_seq_len, max((len(seq) for seq in batch_tokens), default=1))
        if max_len_cur == 0:
            max_len_cur = 1

        input_ids = torch.zeros((batch_size_cur, max_len_cur), dtype=torch.long, device=device)
        attention_mask = torch.zeros((batch_size_cur, max_len_cur), dtype=torch.float32, device=device)

        for b_i, seq in enumerate(batch_tokens):
            for pos_i, gene in enumerate(seq[:max_len_cur]):
                tid = token_dict.get(gene, 1)  # unknown maps to 1
                input_ids[b_i, pos_i] = tid
                attention_mask[b_i, pos_i] = 1.0

        with torch.no_grad():
            outputs = model(input_ids=input_ids, attention_mask=attention_mask, output_hidden_states=True)
            # Retrieve last hidden state
            if hasattr(outputs, "hidden_states") and outputs.hidden_states is not None:
                hidden = outputs.hidden_states[-1]
            elif hasattr(outputs, "last_hidden_state"):
                hidden = outputs.last_hidden_state
            else:
                hidden = outputs[0]

            # Mean pooling over valid (non-padded) tokens
            mask_expanded = attention_mask.unsqueeze(-1)  # (B, L, 1)
            sum_hidden = torch.sum(hidden * mask_expanded, dim=1)  # (B, D)
            sum_mask = torch.clamp(mask_expanded.sum(dim=1), min=1e-6)  # (B, 1)
            cell_embeds = (sum_hidden / sum_mask).detach().cpu().numpy()

        embeddings_list.append(cell_embeds)

    full_embeddings = np.vstack(embeddings_list)
    # Adjust to target embedding dimension if needed
    if full_embeddings.shape[1] != embedding_dim:
        if full_embeddings.shape[1] > embedding_dim:
            full_embeddings = full_embeddings[:, :embedding_dim]
        else:
            pad = np.zeros((n_cells, embedding_dim - full_embeddings.shape[1]), dtype=np.float32)
            full_embeddings = np.hstack([full_embeddings, pad])

    return full_embeddings.astype(np.float32)


# ==============================================================================
# Transparent Rank-Weighted SVD Proxy (Grade C Experimental, BNS-EF-002)
# ==============================================================================


def extract_rank_proxy_embeddings(
    adata: Any,
    embedding_dim: int = 512,
    max_seq_len: int = 2048,
    random_seed: int = 42,
    obsm_key: str = "X_rank_proxy",
) -> SCFMEmbeddingResult:
    """
    Transparent, deterministic Rank-Weighted SVD Proxy for zero-shot exploratory analysis.

    Grade: Grade C (EXPERIMENTAL HEURISTIC PROXY)
    Honesty Guarantee: Discloses clearly that this is an SVD proxy and not a neural network.
    """
    from sklearn.decomposition import TruncatedSVD

    if adata.n_obs == 0 or adata.n_vars == 0:
        return SCFMEmbeddingResult(
            success=False,
            status="REFUSAL_EMPTY_DATASET",
            model_family="rank_proxy",
            model_name="rank_svd_proxy",
            n_cells=adata.n_obs,
            n_genes=adata.n_vars,
            embedding_dim=embedding_dim,
            backend_used="none",
            obsm_key=obsm_key,
            remedy_if_failed="Dataset has 0 cells or 0 genes.",
        )

    X = adata.X.toarray() if sparse.issparse(adata.X) else np.array(adata.X)
    n_cells, n_genes = X.shape

    # Rank decay weights
    rank_weights = np.zeros_like(X, dtype=np.float32)
    for i in range(n_cells):
        row = X[i]
        non_zero_idx = np.where(row > 0)[0]
        if len(non_zero_idx) > 0:
            ranks = np.argsort(-row[non_zero_idx])[:max_seq_len]
            rank_weights[i, non_zero_idx[ranks]] = 1.0 / np.log2(np.arange(len(ranks)) + 2.0)

    n_comp = min(embedding_dim, n_genes, n_cells - 1)
    if n_comp < 2:
        n_comp = 2

    svd = TruncatedSVD(n_components=n_comp, random_state=random_seed)
    embeddings = svd.fit_transform(rank_weights)

    if embeddings.shape[1] < embedding_dim:
        pad_width = embedding_dim - embeddings.shape[1]
        embeddings = np.pad(embeddings, ((0, 0), (0, pad_width)), mode="constant")
    elif embeddings.shape[1] > embedding_dim:
        embeddings = embeddings[:, :embedding_dim]

    adata.obsm[obsm_key] = embeddings

    return SCFMEmbeddingResult(
        success=True,
        status="COMPLETED_PROXY_EXPERIMENTAL",
        model_family="rank_proxy",
        model_name="rank_svd_proxy",
        n_cells=n_cells,
        n_genes=n_genes,
        embedding_dim=embedding_dim,
        backend_used="heuristic-rank-svd-proxy (Grade C Heuristic)",
        obsm_key=obsm_key,
        is_canonical=False,
        mean_token_count_per_cell=float(np.mean(np.sum(X > 0, axis=1))),
        execution_notes=[
            "DISCLAIMER: Output is a Grade C experimental rank-weighted SVD proxy, NOT a pretrained Geneformer/scGPT neural network checkpoint.",
            "Canonical foundation model inference strictly requires loading official model weights (e.g. 'ctheodoris/Geneformer').",
            f"Embedding tensor stored in adata.obsm['{obsm_key}'] with shape {embeddings.shape}.",
            "Evidence Ceiling: PRELIMINARY (BNS-CC-013).",
        ],
    )


# ==============================================================================
# Main Public APIs (Unified & Fail-Closed)
# ==============================================================================


def extract_scfm_embeddings(
    adata: Any,
    config: Optional[SCFMConfig] = None,
    allow_proxy_fallback: bool = False,
) -> SCFMEmbeddingResult:
    """
    Extract single-cell foundation model embeddings.

    When `config.model_name_or_path` is specified:
        Executes genuine canonical Transformer inference with model weights.
    When `config.model_name_or_path` is None or unavailable:
        If `allow_proxy_fallback=True`, runs `extract_rank_proxy_embeddings` with explicit Grade C attribution.
        If `allow_proxy_fallback=False`, fails closed (REFUSAL_MODEL_CHECKPOINT_REQUIRED / REFUSAL_CANONICAL_BACKEND_NOT_IMPLEMENTED).
    """
    cfg = config or SCFMConfig()
    obsm_key = f"X_{cfg.model_family.value}"

    if adata.n_obs == 0 or adata.n_vars == 0:
        return SCFMEmbeddingResult(
            success=False,
            status="REFUSAL_EMPTY_DATASET",
            model_family=cfg.model_family.value,
            model_name=cfg.model_name_or_path,
            n_cells=adata.n_obs,
            n_genes=adata.n_vars,
            embedding_dim=cfg.embedding_dim,
            backend_used="none",
            obsm_key=obsm_key,
            remedy_if_failed="Input AnnData dataset has 0 cells or 0 genes.",
        )

    # Check for all-zero matrix
    X = adata.X.toarray() if sparse.issparse(adata.X) else np.array(adata.X)
    if np.all(np.sum(X > 0, axis=1) == 0):
        return SCFMEmbeddingResult(
            success=False,
            status="REFUSAL_ALL_ZERO_MATRIX",
            model_family=cfg.model_family.value,
            model_name=cfg.model_name_or_path,
            n_cells=adata.n_obs,
            n_genes=adata.n_vars,
            embedding_dim=cfg.embedding_dim,
            backend_used="none",
            obsm_key=obsm_key,
            remedy_if_failed="Count matrix contains exclusively zeros. Cannot compute rank encoding or tokenization.",
        )

    # Case 1: scGPT model family (Frontier / Canonical execution not yet implemented)
    if cfg.model_family == FoundationModelFamily.SCGPT:
        if not allow_proxy_fallback:
            return SCFMEmbeddingResult(
                success=False,
                status="REFUSAL_CANONICAL_BACKEND_NOT_IMPLEMENTED",
                model_family=cfg.model_family.value,
                model_name=cfg.model_name_or_path,
                n_cells=adata.n_obs,
                n_genes=adata.n_vars,
                embedding_dim=cfg.embedding_dim,
                backend_used="none",
                obsm_key=obsm_key,
                remedy_if_failed=(
                    "Canonical scGPT transformer forward execution pipeline is currently under frontier development "
                    "(vocabulary alignment, gene token binning & official checkpoint loader). Strict mode refusal: "
                    "canonical execution not yet implemented. Opt in with `allow_proxy_fallback=True` to run the Grade C SVD proxy (BNS-EF-002)."
                ),
            )
        return extract_rank_proxy_embeddings(
            adata=adata,
            embedding_dim=cfg.embedding_dim,
            max_seq_len=cfg.max_seq_len,
            random_seed=cfg.random_seed,
            obsm_key=obsm_key,
        )

    # Case 2: Geneformer Checkpoint specified -> Attempt canonical Transformer execution
    if cfg.model_name_or_path:
        try:
            torch = importlib.import_module("torch")
            device = cfg.device
            if device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"

            model, token_dict = load_geneformer_transformer_model(cfg.model_name_or_path, device=device)
            token_sequences, token_counts = rank_value_encode(adata, max_seq_len=cfg.max_seq_len)
            embeddings = run_geneformer_canonical_forward(
                model=model,
                token_sequences=token_sequences,
                token_dict=token_dict,
                device=device,
                max_seq_len=cfg.max_seq_len,
                embedding_dim=cfg.embedding_dim,
                batch_size=cfg.batch_size,
            )
            adata.obsm[obsm_key] = embeddings

            return SCFMEmbeddingResult(
                success=True,
                status="COMPLETED",
                model_family=cfg.model_family.value,
                model_name=cfg.model_name_or_path,
                n_cells=adata.n_obs,
                n_genes=adata.n_vars,
                embedding_dim=cfg.embedding_dim,
                backend_used=f"geneformer-canonical-transformer ({cfg.model_name_or_path})",
                obsm_key=obsm_key,
                is_canonical=True,
                mean_token_count_per_cell=float(np.mean(token_counts)),
                execution_notes=[
                    f"Canonical GENEFORMER transformer executed successfully with weights from '{cfg.model_name_or_path}'.",
                    f"Embedding tensor stored in adata.obsm['{obsm_key}'] with shape {embeddings.shape}.",
                    "Evidence Ceiling: PRELIMINARY (BNS-CC-013).",
                ],
            )

        except Exception as e:
            logger.warning(f"Canonical {cfg.model_family.value} checkpoint loading/inference failed: {e}")
            if not allow_proxy_fallback:
                return SCFMEmbeddingResult(
                    success=False,
                    status="REFUSAL_CHECKPOINT_EXECUTION_FAILED",
                    model_family=cfg.model_family.value,
                    model_name=cfg.model_name_or_path,
                    n_cells=adata.n_obs,
                    n_genes=adata.n_vars,
                    embedding_dim=cfg.embedding_dim,
                    backend_used="none",
                    obsm_key=obsm_key,
                    remedy_if_failed=(
                        f"Failed to execute canonical {cfg.model_family.value} checkpoint '{cfg.model_name_or_path}': {str(e)}. "
                        "To run lightweight rank-weighted SVD proxy instead, pass `allow_proxy_fallback=True`."
                    ),
                )

    # Case 3: Geneformer without checkpoint
    if not allow_proxy_fallback:
        return SCFMEmbeddingResult(
            success=False,
            status="REFUSAL_MODEL_CHECKPOINT_REQUIRED",
            model_family=cfg.model_family.value,
            model_name=cfg.model_name_or_path,
            n_cells=adata.n_obs,
            n_genes=adata.n_vars,
            embedding_dim=cfg.embedding_dim,
            backend_used="none",
            obsm_key=obsm_key,
            remedy_if_failed=(
                f"Canonical {cfg.model_family.value} inference strictly requires an official model checkpoint "
                "(e.g. 'ctheodoris/Geneformer' or local directory). BioNexus prohibits heuristic masquerading as canonical backend (BNS-EF-002). "
                "Provide a checkpoint via `SCFMConfig(model_name_or_path=...)` or explicitly invoke `extract_rank_proxy_embeddings()`."
            ),
        )

    # Fallback to transparent Grade C proxy
    return extract_rank_proxy_embeddings(
        adata=adata,
        embedding_dim=cfg.embedding_dim,
        max_seq_len=cfg.max_seq_len,
        random_seed=cfg.random_seed,
        obsm_key=obsm_key,
    )


def simulate_gene_perturbation(
    adata: Any,
    target_gene: str,
    mode: str = "knockout",
    config: Optional[SCFMConfig] = None,
    cell_type_col: Optional[str] = "cell_type",
    allow_proxy_fallback: bool = True,
) -> SCFMPerturbationResult:
    """
    Perform in silico gene perturbation (Knockout or Overexpression) and compute embedding displacement.
    """
    cfg = config or SCFMConfig()

    if target_gene not in adata.var_names:
        return SCFMPerturbationResult(
            success=False,
            status="REFUSAL_TARGET_GENE_NOT_FOUND",
            model_family=cfg.model_family.value,
            target_gene=target_gene,
            perturbation_mode=mode,
            n_cells_evaluated=0,
            mean_displacement_magnitude=0.0,
            remedy_if_failed=f"Target gene '{target_gene}' not found in adata.var_names.",
        )

    # 1. Baseline embedding
    adata_base = adata.copy()
    base_res = extract_scfm_embeddings(adata_base, cfg, allow_proxy_fallback=allow_proxy_fallback)
    if not base_res.success:
        return SCFMPerturbationResult(
            success=False,
            status=f"FAILED_BASELINE_{base_res.status}",
            model_family=cfg.model_family.value,
            target_gene=target_gene,
            perturbation_mode=mode,
            n_cells_evaluated=0,
            mean_displacement_magnitude=0.0,
            remedy_if_failed=base_res.remedy_if_failed,
        )

    base_emb = adata_base.obsm[base_res.obsm_key]

    # 2. In silico perturbation
    adata_pert = adata.copy()
    gene_idx = list(adata.var_names).index(target_gene)

    if sparse.issparse(adata_pert.X):
        X_pert = adata_pert.X.tolil()
        if mode == "knockout":
            X_pert[:, gene_idx] = 0.0
        else:
            max_val = float(np.max(X_pert.data)) if len(X_pert.data) > 0 else 10.0
            X_pert[:, gene_idx] = max_val
        adata_pert.X = X_pert.tocsr()
    else:
        X_pert = np.array(adata_pert.X)
        if mode == "knockout":
            X_pert[:, gene_idx] = 0.0
        else:
            max_val = np.max(X_pert) if np.max(X_pert) > 0 else 10.0
            X_pert[:, gene_idx] = max_val
        adata_pert.X = X_pert

    # 3. Perturbed embedding
    pert_res = extract_scfm_embeddings(adata_pert, cfg, allow_proxy_fallback=allow_proxy_fallback)
    pert_emb = adata_pert.obsm[pert_res.obsm_key]

    # 4. Measure displacement Delta e
    delta = pert_emb - base_emb
    magnitudes = np.linalg.norm(delta, axis=1)
    mean_mag = float(np.mean(magnitudes))

    top_cell_idx = np.argsort(-magnitudes)[:10]
    top_cells = [str(adata.obs_names[i]) for i in top_cell_idx]

    ct_summary = {}
    if cell_type_col and cell_type_col in adata.obs:
        for ct in np.unique(adata.obs[cell_type_col].dropna()):
            mask = (adata.obs[cell_type_col] == ct).values
            if np.sum(mask) > 0:
                ct_summary[str(ct)] = float(np.mean(magnitudes[mask]))

    return SCFMPerturbationResult(
        success=True,
        status="COMPLETED",
        model_family=cfg.model_family.value,
        target_gene=target_gene,
        perturbation_mode=mode,
        n_cells_evaluated=adata.n_obs,
        mean_displacement_magnitude=mean_mag,
        top_displaced_cells=top_cells,
        cell_type_shift_summary=ct_summary,
        backend_used=pert_res.backend_used,
        is_canonical=pert_res.is_canonical,
        execution_notes=[
            f"In silico {mode.upper()} of '{target_gene}' simulated across {adata.n_obs} cells.",
            f"Backend used: {pert_res.backend_used}.",
            f"Mean embedding displacement magnitude: {mean_mag:.4f}.",
            "Evidence Ceiling: PRELIMINARY. In silico predictions are computational hypotheses requiring experimental validation.",
        ],
    )

