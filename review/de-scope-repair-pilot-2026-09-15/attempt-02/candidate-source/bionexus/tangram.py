"""
BioNexus Tangram Spatial Deconvolution & Cell-to-Space Mapping Engine.

Implements deep learning & optimal transport mapping of single-cell transcriptomes
(adata_sc) onto spatial transcriptomics coordinates (adata_sp e.g. Visium / Slide-seq)
based on Tangram (Biancalani et al., Nature Biotechnology 2021).

Adheres strictly to BioNexus Fail-Closed & Epistemic Honesty Invariants:
- Requires valid spatial coordinates (obsm['spatial']).
- Requires single-cell reference cell type annotations.
- Verifies >= 10 overlapping marker genes.
- Transparently discloses execution backend (PyTorch GPU/CPU vs Heuristic Fallback).
"""

import importlib
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import sparse

logger = logging.getLogger("bionexus.tangram")


@dataclass
class TangramConfig:
    """Configuration hyperparameters for Tangram spatial mapping."""

    mode: str = "cells"  # 'cells' or 'clusters'
    device: str = "auto"  # 'auto', 'cuda', 'cpu'
    num_epochs: int = 500
    learning_rate: float = 0.1
    density_prior: str = "uniform"  # 'uniform' or 'rna_count_based'
    n_top_markers: int = 50
    min_shared_genes: int = 10
    target_count_per_cell: float = 1e4
    random_seed: int = 42

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TangramMappingResult:
    """Structured result of Tangram spatial deconvolution and mapping."""

    success: bool
    status: str
    cell_type_names: List[str]
    n_spots: int
    n_cells_or_clusters: int
    n_shared_genes: int
    shared_genes: List[str]
    backend_used: str  # 'tangram-pytorch-cuda', 'tangram-pytorch-cpu', 'heuristic-nnls-fallback'
    proportions_df: Optional[pd.DataFrame] = None
    dominant_cell_types: Optional[List[str]] = None
    cell_to_spot_map_shape: Optional[Tuple[int, int]] = None
    training_loss_final: Optional[float] = None
    execution_notes: List[str] = field(default_factory=list)
    remedy_if_failed: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.proportions_df is not None:
            d["proportions_df"] = self.proportions_df.to_dict(orient="split")
        return d


def check_tangram_backend() -> Tuple[bool, str]:
    """Check whether tangram and torch are available in the current environment."""
    try:
        tg = importlib.import_module("tangram")
        torch = importlib.import_module("torch")
        has_cuda = torch.cuda.is_available()
        backend_str = f"tangram-pytorch-{'cuda' if has_cuda else 'cpu'} (tangram {getattr(tg, '__version__', 'unknown')})"
        return True, backend_str
    except ImportError as e:
        return False, f"Backend unavailable: {str(e)}"


def select_training_marker_genes(
    adata_sc: Any,
    adata_sp: Any,
    cell_type_col: str = "cell_type",
    n_top_markers: int = 50,
    min_expr: float = 0.05,
) -> Tuple[List[str], pd.DataFrame]:
    """
    Identify informative marker genes from scRNA-seq reference and intersect with spatial target.
    """
    if cell_type_col not in adata_sc.obs:
        raise ValueError(
            f"Cell type column '{cell_type_col}' not found in single-cell reference obs. "
            f"Available obs columns: {list(adata_sc.obs.columns)}"
        )

    sc_genes = np.array(adata_sc.var_names)
    sp_genes = set(adata_sp.var_names)

    # Compute per-cell-type mean expressions
    cell_types = np.unique(adata_sc.obs[cell_type_col].dropna())
    X_sc = adata_sc.X.toarray() if sparse.issparse(adata_sc.X) else np.array(adata_sc.X)

    # Library size normalize
    lib_sizes = np.sum(X_sc, axis=1, keepdims=True) + 1e-6
    X_cpm = (X_sc / lib_sizes) * 1e4

    candidate_markers = set()
    signatures = {}

    for ct in cell_types:
        mask = (adata_sc.obs[cell_type_col] == ct).values
        if np.sum(mask) == 0:
            continue
        ct_mean = np.mean(X_cpm[mask], axis=0)
        signatures[str(ct)] = ct_mean

        other_mean = np.mean(X_cpm[~mask], axis=0) if np.sum(~mask) > 0 else np.zeros_like(ct_mean)
        log2_fc = np.log2((ct_mean + 1.0) / (other_mean + 1.0))

        valid = np.where(ct_mean > min_expr)[0]
        if len(valid) > 0:
            top_idx = valid[np.argsort(-log2_fc[valid])[:n_top_markers]]
            candidate_markers.update(sc_genes[top_idx])

    # Intersect with spatial genes
    shared_markers = [g for g in candidate_markers if g in sp_genes]
    sig_df = pd.DataFrame(signatures, index=sc_genes)

    return shared_markers, sig_df


def _fallback_heuristic_deconvolution(
    adata_sc: Any,
    adata_sp: Any,
    cell_type_col: str,
    marker_genes: List[str],
    reference_sig: pd.DataFrame,
) -> TangramMappingResult:
    """
    Honest, non-negative least squares & optimal transport fallback when Tangram/PyTorch is absent.
    Discloses fallback status explicitly.
    """
    from scipy.optimize import nnls

    S = reference_sig.loc[marker_genes].to_numpy(dtype=float)
    cell_types = list(reference_sig.columns)

    sp_sub = adata_sp[:, marker_genes]
    X_sp = sp_sub.X.toarray() if sparse.issparse(sp_sub.X) else np.array(sp_sub.X)

    lib_sizes = np.sum(X_sp, axis=1, keepdims=True) + 1e-6
    X_sp_cpm = (X_sp / lib_sizes) * 1e4

    n_spots = X_sp.shape[0]
    n_types = len(cell_types)
    proportions = np.zeros((n_spots, n_types), dtype=float)

    for i in range(n_spots):
        spot_vec = X_sp_cpm[i]
        weights, _ = nnls(S, spot_vec)
        tot = np.sum(weights)
        if tot > 0:
            proportions[i] = weights / tot
        else:
            proportions[i] = np.ones(n_types) / n_types

    prop_df = pd.DataFrame(proportions, index=adata_sp.obs_names, columns=cell_types)
    dominant = [cell_types[idx] for idx in np.argmax(proportions, axis=1)]

    # Store in adata_sp
    adata_sp.obsm["tangram_ct_pred"] = prop_df.to_numpy()
    adata_sp.uns["tangram_cell_types"] = cell_types
    adata_sp.obs["dominant_cell_type"] = dominant

    return TangramMappingResult(
        success=True,
        status="COMPLETED_WITH_HEURISTIC_FALLBACK",
        cell_type_names=cell_types,
        n_spots=n_spots,
        n_cells_or_clusters=n_types,
        n_shared_genes=len(marker_genes),
        shared_genes=marker_genes,
        backend_used="heuristic-nnls-fallback",
        proportions_df=prop_df,
        dominant_cell_types=dominant,
        execution_notes=[
            "Tangram / PyTorch was not found in the environment.",
            "Deconvolution executed using constrained Non-Negative Least Squares (NNLS) signature projection.",
            "Disclaimer: Output is research heuristic fallback; for official Tangram deep learning, install tangram-sc and torch.",
        ],
    )


def run_tangram_spatial_mapping(
    adata_sc: Any,
    adata_sp: Any,
    cell_type_col: str = "cell_type",
    config: Optional[TangramConfig] = None,
    allow_fallback: bool = False,
) -> TangramMappingResult:
    """
    Execute Tangram spatial deconvolution and cell-to-spot mapping.

    Parameters:
        adata_sc: Single-cell AnnData reference with cell type labels in obs[cell_type_col].
        adata_sp: Spatial AnnData target containing 2D coordinates in obsm['spatial'].
        cell_type_col: Column name in adata_sc.obs containing cell type annotations.
        config: Optional TangramConfig hyperparameters.
        allow_fallback: If True and tangram is missing, uses honest NNLS fallback.
                        Default is False (Fail closed by default, degrade only by explicit opt-in).

    Returns:
        TangramMappingResult containing cell type proportions, shared genes, and diagnostic metadata.
    """
    cfg = config or TangramConfig()

    # Invariant 1: Spatial coordinates must be present
    if "spatial" not in adata_sp.obsm:
        return TangramMappingResult(
            success=False,
            status="REFUSAL_MISSING_COORDINATES",
            cell_type_names=[],
            n_spots=adata_sp.n_obs,
            n_cells_or_clusters=0,
            n_shared_genes=0,
            shared_genes=[],
            backend_used="none",
            remedy_if_failed="Spatial AnnData target must have 2D coordinates in obsm['spatial'].",
        )

    coords = adata_sp.obsm["spatial"]
    if getattr(coords, "ndim", 0) != 2 or coords.shape[1] not in (2, 3):
        return TangramMappingResult(
            success=False,
            status="REFUSAL_INVALID_COORDINATES",
            cell_type_names=[],
            n_spots=adata_sp.n_obs,
            n_cells_or_clusters=0,
            n_shared_genes=0,
            shared_genes=[],
            backend_used="none",
            remedy_if_failed=f"obsm['spatial'] must have shape (N, 2) or (N, 3), found {getattr(coords, 'shape', None)}.",
        )

    # Invariant 2: Single cell reference must have valid cell type annotations
    if cell_type_col not in adata_sc.obs:
        return TangramMappingResult(
            success=False,
            status="REFUSAL_MISSING_CELL_TYPE_ANNOTATION",
            cell_type_names=[],
            n_spots=adata_sp.n_obs,
            n_cells_or_clusters=0,
            n_shared_genes=0,
            shared_genes=[],
            backend_used="none",
            remedy_if_failed=f"Single-cell reference must contain '{cell_type_col}' in obs.",
        )

    # Invariant 3: Marker gene extraction and overlap verification
    try:
        shared_markers, sig_df = select_training_marker_genes(
            adata_sc=adata_sc,
            adata_sp=adata_sp,
            cell_type_col=cell_type_col,
            n_top_markers=cfg.n_top_markers,
        )
    except Exception as e:
        return TangramMappingResult(
            success=False,
            status="REFUSAL_PREPROCESSING_FAILED",
            cell_type_names=[],
            n_spots=adata_sp.n_obs,
            n_cells_or_clusters=0,
            n_shared_genes=0,
            shared_genes=[],
            backend_used="none",
            remedy_if_failed=f"Failed to identify marker gene overlap: {str(e)}",
        )

    if len(shared_markers) < cfg.min_shared_genes:
        return TangramMappingResult(
            success=False,
            status="REFUSAL_INSUFFICIENT_SHARED_GENES",
            cell_type_names=list(sig_df.columns),
            n_spots=adata_sp.n_obs,
            n_cells_or_clusters=len(sig_df.columns),
            n_shared_genes=len(shared_markers),
            shared_genes=shared_markers,
            backend_used="none",
            remedy_if_failed=(
                f"Only {len(shared_markers)} overlapping marker genes found between scRNA and spatial target. "
                f"Minimum required is {cfg.min_shared_genes}. Please check gene nomenclature (e.g. Ensembl vs Symbol)."
            ),
        )

    # Check Tangram backend availability
    has_tg, backend_desc = check_tangram_backend()

    if not has_tg:
        if not allow_fallback:
            return TangramMappingResult(
                success=False,
                status="REFUSAL_BACKEND_UNAVAILABLE",
                cell_type_names=list(sig_df.columns),
                n_spots=adata_sp.n_obs,
                n_cells_or_clusters=len(sig_df.columns),
                n_shared_genes=len(shared_markers),
                shared_genes=shared_markers,
                backend_used="none",
                remedy_if_failed=(
                    "Tangram deep learning backend is not installed. "
                    "Install via `pip install tangram-sc torch` or enable `allow_fallback=True` for heuristic NNLS projection."
                ),
            )
        # Execute honest fallback
        return _fallback_heuristic_deconvolution(
            adata_sc=adata_sc,
            adata_sp=adata_sp,
            cell_type_col=cell_type_col,
            marker_genes=shared_markers,
            reference_sig=sig_df,
        )

    # Execute official Tangram mapping with PyTorch
    try:
        tg = importlib.import_module("tangram")
        torch = importlib.import_module("torch")

        device = cfg.device
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(f"Running Tangram map_cells_to_space on device={device} with {len(shared_markers)} training genes...")

        # Preprocess adatas for tangram
        tg.pp_adatas(adata_sc, adata_sp, genes=shared_markers)

        # Execute map
        ad_map = tg.map_cells_to_space(
            adata_sc,
            adata_sp,
            mode=cfg.mode,
            device=device,
            num_epochs=cfg.num_epochs,
            learning_rate=cfg.learning_rate,
            random_state=cfg.random_seed,
            verbose=False,
        )

        # Project cell type annotations to spatial spots
        tg.project_cell_annotations(ad_map, adata_sp, annotation=cell_type_col)

        # Extract proportions dataframe
        cell_types = list(np.unique(adata_sc.obs[cell_type_col].dropna()))
        if "tangram_ct_pred" in adata_sp.obsm:
            pred_mat = adata_sp.obsm["tangram_ct_pred"]
            if hasattr(pred_mat, "to_numpy"):
                prop_df = pred_mat
            elif hasattr(pred_mat, "values"):
                prop_df = pd.DataFrame(pred_mat.values, index=adata_sp.obs_names, columns=cell_types[: pred_mat.shape[1]])
            else:
                prop_df = pd.DataFrame(pred_mat, index=adata_sp.obs_names, columns=cell_types[: pred_mat.shape[1]])
        else:
            prop_df = pd.DataFrame(index=adata_sp.obs_names)

        dominant = [cell_types[idx] for idx in np.argmax(prop_df.to_numpy(), axis=1)] if not prop_df.empty else []
        adata_sp.obs["dominant_cell_type"] = dominant

        return TangramMappingResult(
            success=True,
            status="COMPLETED",
            cell_type_names=cell_types,
            n_spots=adata_sp.n_obs,
            n_cells_or_clusters=len(cell_types),
            n_shared_genes=len(shared_markers),
            shared_genes=shared_markers,
            backend_used=f"tangram-pytorch-{device}",
            proportions_df=prop_df,
            dominant_cell_types=dominant,
            cell_to_spot_map_shape=ad_map.shape,
            execution_notes=[
                f"Tangram optimal transport optimization completed successfully on {device.upper()}.",
                "Cell type proportions written to adata_sp.obsm['tangram_ct_pred'].",
                "Dominant cell type assigned per spatial spot in adata_sp.obs['dominant_cell_type'].",
            ],
        )

    except Exception as e:
        logger.error(f"Tangram mapping failed during optimization: {e}")
        if allow_fallback:
            logger.info("Falling back to constrained NNLS deconvolution...")
            res = _fallback_heuristic_deconvolution(
                adata_sc=adata_sc,
                adata_sp=adata_sp,
                cell_type_col=cell_type_col,
                marker_genes=shared_markers,
                reference_sig=sig_df,
            )
            res.execution_notes.append(f"Tangram PyTorch execution crashed ({str(e)}); reverted to heuristic fallback.")
            return res
        return TangramMappingResult(
            success=False,
            status="ERROR_DURING_OPTIMIZATION",
            cell_type_names=list(sig_df.columns),
            n_spots=adata_sp.n_obs,
            n_cells_or_clusters=len(sig_df.columns),
            n_shared_genes=len(shared_markers),
            shared_genes=shared_markers,
            backend_used="none",
            remedy_if_failed=f"Tangram optimization error: {str(e)}",
        )
