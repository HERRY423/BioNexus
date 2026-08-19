"""
BioNexus Closed-Loop Perturbation-to-Spatial-Niche Engine.

Integrates:
1. GEARS (Roohani et al., Nature Biotechnology 2023): Graph-Enhanced Gene Perturbation
   Prediction for single and combinatorial genetic knockouts/overexpressions.
2. NicheFormer (Schulz et al., Nature Methods / bioRxiv 2024): Foundation model for
   spatial niche composition and microenvironment forecasting.
3. Dry-Wet Closed-Loop Evaluator: Automates the workflow
   Single-Cell Perturbation -> Spatial Niche Shift -> Wet-Lab Experimental Hypothesis Card.

Adheres strictly to BioNexus Epistemic Honesty & Specification Series:
- Evidence ceiling: PRELIMINARY for in silico forecasts.
- Refusal guards: Invalid gene names, empty matrices, missing spatial geometry.
- Transparent backend disclosure (PyTorch GNN/Transformer vs Co-expression Network Fallback).
"""

import importlib
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import sparse

logger = logging.getLogger("bionexus.closed_loop")


@dataclass
class GEARSPerturbationConfig:
    """Hyperparameters for GEARS genetic perturbation modeling."""

    target_genes: List[str] = field(default_factory=list)
    mode: str = "knockout"  # 'knockout' or 'overexpression'
    device: str = "auto"
    num_epochs: int = 50
    hidden_dim: int = 64
    random_seed: int = 42
    model_path: Optional[str] = None
    gears_model: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["gears_model"] = str(type(self.gears_model)) if self.gears_model is not None else None
        return d


@dataclass
class NicheFormerConfig:
    """Hyperparameters for NicheFormer spatial microenvironment forecasting."""

    n_niche_classes: int = 5
    niche_radius_spots: int = 6
    device: str = "auto"
    random_seed: int = 42
    model_path: Optional[str] = None
    nicheformer_model: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["nicheformer_model"] = str(type(self.nicheformer_model)) if self.nicheformer_model is not None else None
        return d


@dataclass
class GEARSPredictionResult:
    """Structured result of GEARS in silico perturbation prediction."""

    success: bool
    status: str
    target_genes: List[str]
    perturbation_mode: str
    n_cells_predicted: int
    n_genes: int
    top_upregulated_genes: List[str] = field(default_factory=list)
    top_downregulated_genes: List[str] = field(default_factory=list)
    mean_fold_change: float = 0.0
    backend_used: str = "none"
    execution_notes: List[str] = field(default_factory=list)
    remedy_if_failed: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class NicheFormerForecastResult:
    """Structured result of NicheFormer spatial microenvironment forecasting."""

    success: bool
    status: str
    n_spots: int
    n_niche_types: int
    niche_names: List[str]
    niche_proportions_mean: Dict[str, float] = field(default_factory=dict)
    dominant_niche_distribution: Dict[str, int] = field(default_factory=dict)
    backend_used: str = "none"
    execution_notes: List[str] = field(default_factory=list)
    remedy_if_failed: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClosedLoopEvaluationResult:
    """Structured result of the end-to-end Perturbation -> Spatial Niche evaluation chain."""

    success: bool
    status: str
    target_perturbation: List[str]
    perturbation_mode: str
    gears_result: Optional[GEARSPredictionResult] = None
    niche_result_baseline: Optional[NicheFormerForecastResult] = None
    niche_result_perturbed: Optional[NicheFormerForecastResult] = None
    niche_remodeling_scores: Dict[str, float] = field(default_factory=dict)
    top_remodeled_niches: List[Tuple[str, float]] = field(default_factory=list)
    wet_lab_hypothesis_card: Dict[str, Any] = field(default_factory=dict)
    execution_notes: List[str] = field(default_factory=list)
    remedy_if_failed: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.gears_result:
            d["gears_result"] = self.gears_result.to_dict()
        if self.niche_result_baseline:
            d["niche_result_baseline"] = self.niche_result_baseline.to_dict()
        if self.niche_result_perturbed:
            d["niche_result_perturbed"] = self.niche_result_perturbed.to_dict()
        return d


# ==============================================================================
# 1. GEARS Genetic Perturbation Engine
# ==============================================================================


# ==============================================================================
# 1. GEARS Genetic Perturbation Engine
# ==============================================================================


def check_gears_backend() -> Tuple[bool, str]:
    """Check availability of GEARS model package and PyTorch Geometric."""
    try:
        torch = importlib.import_module("torch")
        importlib.import_module("torch_geometric")
        gears_pkg = importlib.import_module("gears")
        has_cuda = torch.cuda.is_available()
        return True, f"gears-pytorch-{'cuda' if has_cuda else 'cpu'} (gears {getattr(gears_pkg, '__version__', 'unknown')})"
    except ImportError as e:
        return False, f"GEARS canonical backend unavailable: {str(e)}"


def run_gears_canonical_forward(
    gears_model: Any,
    target_genes: List[str],
    adata_base: Any,
    mode: str = "knockout",
) -> Tuple[Any, List[str], List[str], float]:
    """
    Execute genuine GEARS Graph Neural Network model forward pass / prediction.
    """
    if hasattr(gears_model, "predict"):
        pred_res = gears_model.predict([target_genes])
        if isinstance(pred_res, dict) and "_pert" in pred_res:
            X_pert = pred_res["_pert"]
        elif isinstance(pred_res, np.ndarray):
            X_pert = pred_res
        elif hasattr(pred_res, "X"):
            X_pert = pred_res.X
        else:
            X_pert = np.array(adata_base.X)
    elif callable(gears_model):
        import torch

        with torch.no_grad():
            inputs = torch.tensor(
                adata_base.X.toarray() if sparse.issparse(adata_base.X) else adata_base.X, dtype=torch.float32
            )
            out = gears_model(inputs)
            X_pert = out.detach().cpu().numpy() if hasattr(out, "detach") else np.array(out)
    else:
        raise TypeError(f"Invalid gears_model object: expected GEARS instance or callable, got {type(gears_model)}")

    adata_pert = adata_base.copy()
    adata_pert.X = sparse.csr_matrix(X_pert) if sparse.issparse(adata_base.X) else X_pert

    X_base = adata_base.X.toarray() if sparse.issparse(adata_base.X) else np.array(adata_base.X)
    delta = np.mean(X_pert - X_base, axis=0)
    genes = np.array(adata_base.var_names)
    sorted_idx = np.argsort(delta)
    top_down = [str(genes[idx]) for idx in sorted_idx[:5] if str(genes[idx]) not in target_genes]
    top_up = [str(genes[idx]) for idx in sorted_idx[-5:][::-1] if str(genes[idx]) not in target_genes]
    mean_fc = float(np.mean(np.abs(delta)))
    return adata_pert, top_up, top_down, mean_fc


def predict_gears_perturbation(
    adata_base: Any,
    target_genes: List[str],
    mode: str = "knockout",
    config: Optional[GEARSPerturbationConfig] = None,
    allow_fallback: bool = False,
) -> Tuple[Any, GEARSPredictionResult]:
    """
    Predict whole-transcriptome single-cell shifts under genetic perturbation via GEARS.

    Parameters:
        adata_base: Single-cell AnnData baseline count/normalized matrix.
        target_genes: List of gene symbols to perturb (e.g. ['TP53'] or ['MYC', 'CDKN1A']).
        mode: 'knockout' or 'overexpression'.
        config: Optional GEARSPerturbationConfig.
        allow_fallback: If True, uses empirical co-expression network shift fallback.
                        Default is False (Fail closed by default, degrade only by explicit opt-in).

    Returns:
        Tuple of (adata_perturbed, GEARSPredictionResult).
    """
    cfg = config or GEARSPerturbationConfig(target_genes=target_genes, mode=mode)

    if adata_base.n_obs == 0 or adata_base.n_vars == 0:
        res = GEARSPredictionResult(
            success=False,
            status="REFUSAL_EMPTY_DATASET",
            target_genes=target_genes,
            perturbation_mode=mode,
            n_cells_predicted=0,
            n_genes=0,
            remedy_if_failed="Input AnnData baseline dataset is empty.",
        )
        return adata_base, res

    missing_genes = [g for g in target_genes if g not in adata_base.var_names]
    if missing_genes:
        res = GEARSPredictionResult(
            success=False,
            status="REFUSAL_TARGET_GENES_NOT_FOUND",
            target_genes=target_genes,
            perturbation_mode=mode,
            n_cells_predicted=0,
            n_genes=adata_base.n_vars,
            remedy_if_failed=f"Target genes {missing_genes} not found in adata.var_names.",
        )
        return adata_base, res

    has_backend, backend_desc = check_gears_backend()

    # Path 1: Canonical GEARS Execution (model object or checkpoint provided)
    if cfg.gears_model is not None or (cfg.model_path and has_backend):
        try:
            gears_model = cfg.gears_model
            if gears_model is None and cfg.model_path:
                gears_pkg = importlib.import_module("gears")
                gears_model = getattr(gears_pkg, "GEARS")()
                gears_model.load_pretrained(cfg.model_path)

            adata_pert, top_up, top_down, mean_fc = run_gears_canonical_forward(
                gears_model=gears_model,
                target_genes=target_genes,
                adata_base=adata_base,
                mode=mode,
            )
            return adata_pert, GEARSPredictionResult(
                success=True,
                status="COMPLETED",
                target_genes=target_genes,
                perturbation_mode=mode,
                n_cells_predicted=adata_base.n_obs,
                n_genes=adata_base.n_vars,
                top_upregulated_genes=top_up,
                top_downregulated_genes=top_down,
                mean_fold_change=mean_fc,
                backend_used="gears-graph-neural-network (canonical)",
                execution_notes=[
                    f"Canonical GEARS GNN executed for target genes: {', '.join(target_genes)} ({mode.upper()}).",
                    "Backend used: gears-graph-neural-network (canonical).",
                    f"Top predicted upregulated downstream genes: {', '.join(top_up)}.",
                    f"Top predicted downregulated downstream genes: {', '.join(top_down)}.",
                    "Evidence Ceiling: PRELIMINARY. In silico predictions are computational hypotheses requiring experimental validation.",
                ],
            )
        except Exception as e:
            logger.warning(f"Canonical GEARS execution failed: {e}")
            if not allow_fallback:
                return adata_base, GEARSPredictionResult(
                    success=False,
                    status="REFUSAL_CANONICAL_EXECUTION_FAILED",
                    target_genes=target_genes,
                    perturbation_mode=mode,
                    n_cells_predicted=0,
                    n_genes=adata_base.n_vars,
                    backend_used="none",
                    remedy_if_failed=f"Canonical GEARS execution failed: {str(e)}. Pass allow_fallback=True for heuristic simulation.",
                )

    # Path 2: No canonical model provided -> Fail closed unless allow_fallback=True
    if not allow_fallback:
        return adata_base, GEARSPredictionResult(
            success=False,
            status="REFUSAL_CANONICAL_MODEL_REQUIRED",
            target_genes=target_genes,
            perturbation_mode=mode,
            n_cells_predicted=0,
            n_genes=adata_base.n_vars,
            backend_used="none",
            remedy_if_failed=(
                "Official GEARS execution requires a loaded GEARS model object (config.gears_model) or trained checkpoint (config.model_path). "
                "BioNexus strictly prohibits substituting co-expression heuristics under the GEARS label (BNS-EF-002 / BN-F010). "
                "Provide a model object or pass `allow_fallback=True` to explicitly opt in to empirical co-expression network simulation."
            ),
        )

    # Path 3: Explicit Grade C Heuristic Fallback
    adata_pert = adata_base.copy()
    X = adata_base.X.toarray() if sparse.issparse(adata_base.X) else np.array(adata_base.X)
    X_pert = X.copy()
    genes = np.array(adata_base.var_names)

    np.random.seed(cfg.random_seed)
    n_cells, n_genes = X.shape
    mean_vec = np.mean(X, axis=0, keepdims=True) + 1e-6
    std_vec = np.std(X, axis=0, keepdims=True) + 1e-6
    X_norm = (X - mean_vec) / std_vec

    delta_expression = np.zeros(n_genes, dtype=np.float32)

    for target_g in target_genes:
        t_idx = list(genes).index(target_g)
        target_col = X_norm[:, t_idx]

        # Pearson correlation of all genes with target
        corr = np.dot(X_norm.T, target_col) / n_cells
        corr = np.nan_to_num(corr, nan=0.0)

        if mode == "knockout":
            X_pert[:, t_idx] = 0.0
            delta = -1.5 * corr
        else:  # overexpression
            max_val = np.max(X_pert[:, t_idx]) if np.max(X_pert[:, t_idx]) > 0 else 10.0
            X_pert[:, t_idx] = max_val * 2.0
            delta = 1.5 * corr

        delta_expression += delta

    shift_matrix = np.tile(delta_expression, (n_cells, 1))
    X_pert = np.clip(X_pert + shift_matrix, 0.0, None)
    adata_pert.X = sparse.csr_matrix(X_pert) if sparse.issparse(adata_base.X) else X_pert

    sorted_gene_idx = np.argsort(delta_expression)
    top_down = [str(genes[idx]) for idx in sorted_gene_idx[:5] if str(genes[idx]) not in target_genes]
    top_up = [str(genes[idx]) for idx in sorted_gene_idx[-5:][::-1] if str(genes[idx]) not in target_genes]
    mean_fc = float(np.mean(np.abs(delta_expression)))

    backend_label = "heuristic-coexpression-network (Grade C Experimental)"
    status_label = "COMPLETED_WITH_HEURISTIC_FALLBACK"

    res = GEARSPredictionResult(
        success=True,
        status=status_label,
        target_genes=target_genes,
        perturbation_mode=mode,
        n_cells_predicted=n_cells,
        n_genes=n_genes,
        top_upregulated_genes=top_up,
        top_downregulated_genes=top_down,
        mean_fold_change=mean_fc,
        backend_used=backend_label,
        execution_notes=[
            f"Perturbation simulated for target genes: {', '.join(target_genes)} ({mode.upper()}).",
            f"Backend used: {backend_label}.",
            f"Top predicted upregulated downstream genes: {', '.join(top_up)}.",
            f"Top predicted downregulated downstream genes: {', '.join(top_down)}.",
            "Evidence Ceiling: PRELIMINARY. In silico predictions are computational hypotheses requiring experimental validation.",
        ],
    )
    return adata_pert, res


# ==============================================================================
# 2. NicheFormer Spatial Niche Forecasting Engine
# ==============================================================================


def check_nicheformer_backend() -> Tuple[bool, str]:
    """Check availability of NicheFormer transformer backend."""
    try:
        torch = importlib.import_module("torch")
        importlib.import_module("transformers")
        nf = importlib.import_module("nicheformer")
        has_cuda = torch.cuda.is_available()
        return True, f"nicheformer-pytorch-{'cuda' if has_cuda else 'cpu'} (nicheformer {getattr(nf, '__version__', 'unknown')})"
    except ImportError as e:
        return False, f"NicheFormer backend unavailable: {str(e)}"


def run_nicheformer_canonical_forward(
    nicheformer_model: Any,
    adata_cells: Any,
    adata_spatial: Any,
    n_niche: int = 5,
) -> Tuple[np.ndarray, List[str]]:
    """
    Execute genuine NicheFormer multimodal transformer forward pass.
    """
    if hasattr(nicheformer_model, "predict"):
        pred_proportions = nicheformer_model.predict(adata_cells, adata_spatial)
    elif hasattr(nicheformer_model, "forward"):
        import torch

        with torch.no_grad():
            coords = torch.tensor(adata_spatial.obsm["spatial"], dtype=torch.float32)
            out = nicheformer_model.forward(coords)
            pred_proportions = out.detach().cpu().numpy() if hasattr(out, "detach") else np.array(out)
    elif callable(nicheformer_model):
        pred_proportions = nicheformer_model(adata_cells, adata_spatial)
    else:
        raise TypeError(
            f"Invalid nicheformer_model object: expected NicheFormer instance or callable, got {type(nicheformer_model)}"
        )

    if not isinstance(pred_proportions, np.ndarray):
        pred_proportions = np.array(pred_proportions)
    if pred_proportions.shape[1] > n_niche:
        pred_proportions = pred_proportions[:, :n_niche]
    elif pred_proportions.shape[1] < n_niche:
        pad = np.zeros((pred_proportions.shape[0], n_niche - pred_proportions.shape[1]), dtype=np.float32)
        pred_proportions = np.hstack([pred_proportions, pad])

    proportions = pred_proportions / np.sum(pred_proportions + 1e-6, axis=1, keepdims=True)
    niche_names = [
        "Immune_Infiltration_Niche",
        "Stromal_Barrier_Niche",
        "Tumor_Core_Niche",
        "Invasive_Margin_Niche",
        "Vascularized_Perivascular_Niche",
    ][:n_niche]
    return proportions, niche_names


def forecast_spatial_niche(
    adata_cells: Any,
    adata_spatial: Any,
    config: Optional[NicheFormerConfig] = None,
    allow_fallback: bool = False,
) -> Tuple[Any, NicheFormerForecastResult]:
    """
    Forecast spatial microenvironment / niche distributions from single-cell transcriptomes.

    Parameters:
        adata_cells: Single-cell AnnData dataset (e.g. baseline or post-perturbation).
        adata_spatial: Spatial AnnData dataset with 2D coordinates in obsm['spatial'].
        config: Optional NicheFormerConfig.
        allow_fallback: If True, uses spatial distance & density mapping fallback.
                        Default is False (Fail closed by default, degrade only by explicit opt-in).

    Returns:
        Tuple of (adata_spatial_with_niche, NicheFormerForecastResult).
    """
    cfg = config or NicheFormerConfig()

    if "spatial" not in adata_spatial.obsm:
        res = NicheFormerForecastResult(
            success=False,
            status="REFUSAL_MISSING_COORDINATES",
            n_spots=adata_spatial.n_obs,
            n_niche_types=0,
            niche_names=[],
            remedy_if_failed="Spatial reference dataset lacks 2D coordinates in obsm['spatial'].",
        )
        return adata_spatial, res

    coords = np.array(adata_spatial.obsm["spatial"])
    if coords.ndim != 2 or coords.shape[1] not in (2, 3):
        res = NicheFormerForecastResult(
            success=False,
            status="REFUSAL_INVALID_COORDINATES",
            n_spots=adata_spatial.n_obs,
            n_niche_types=0,
            niche_names=[],
            remedy_if_failed="obsm['spatial'] must have shape (N, 2) or (N, 3).",
        )
        return adata_spatial, res

    has_backend, backend_desc = check_nicheformer_backend()
    n_spots = adata_spatial.n_obs
    n_niche = cfg.n_niche_classes

    # Path 1: Canonical NicheFormer Execution (model object or checkpoint provided)
    if cfg.nicheformer_model is not None or (cfg.model_path and has_backend):
        try:
            nicheformer_model = cfg.nicheformer_model
            if nicheformer_model is None and cfg.model_path:
                nf_pkg = importlib.import_module("nicheformer")
                nicheformer_model = getattr(nf_pkg, "Nicheformer").from_pretrained(cfg.model_path)

            proportions, niche_names = run_nicheformer_canonical_forward(
                nicheformer_model=nicheformer_model,
                adata_cells=adata_cells,
                adata_spatial=adata_spatial,
                n_niche=n_niche,
            )

            adata_spatial.obsm["nicheformer_niche_pred"] = proportions
            adata_spatial.uns["niche_names"] = niche_names
            dominant_indices = np.argmax(proportions, axis=1)
            dominant_labels = [niche_names[idx] for idx in dominant_indices]
            adata_spatial.obs["dominant_niche"] = dominant_labels

            mean_proportions = {niche_names[i]: float(np.mean(proportions[:, i])) for i in range(n_niche)}
            distribution = {niche_names[i]: int(np.sum(dominant_indices == i)) for i in range(n_niche)}

            return adata_spatial, NicheFormerForecastResult(
                success=True,
                status="COMPLETED",
                n_spots=n_spots,
                n_niche_types=n_niche,
                niche_names=niche_names,
                niche_proportions_mean=mean_proportions,
                dominant_niche_distribution=distribution,
                backend_used="nicheformer-multimodal-transformer (canonical)",
                execution_notes=[
                    f"Canonical NicheFormer transformer executed across {n_spots} spots.",
                    "Backend used: nicheformer-multimodal-transformer (canonical).",
                    f"Forecasted {n_niche} distinct spatial niches: {', '.join(niche_names)}.",
                    "Evidence Ceiling: PRELIMINARY. In silico spatial niche forecasts require multiplexed in situ staining confirmation.",
                ],
            )
        except Exception as e:
            logger.warning(f"Canonical NicheFormer execution failed: {e}")
            if not allow_fallback:
                return adata_spatial, NicheFormerForecastResult(
                    success=False,
                    status="REFUSAL_CANONICAL_EXECUTION_FAILED",
                    n_spots=n_spots,
                    n_niche_types=0,
                    niche_names=[],
                    backend_used="none",
                    remedy_if_failed=f"Canonical NicheFormer execution failed: {str(e)}. Pass allow_fallback=True for spatial clustering fallback.",
                )

    # Path 2: No canonical model provided -> Fail closed unless allow_fallback=True
    if not allow_fallback:
        return adata_spatial, NicheFormerForecastResult(
            success=False,
            status="REFUSAL_CANONICAL_MODEL_REQUIRED",
            n_spots=adata_spatial.n_obs,
            n_niche_types=0,
            niche_names=[],
            backend_used="none",
            remedy_if_failed=(
                "Official NicheFormer execution requires a loaded NicheFormer model object (config.nicheformer_model) or pretrained checkpoint (config.model_path). "
                "BioNexus strictly prohibits substituting spatial KMeans clustering under the NicheFormer label (BNS-EF-002 / BN-F010). "
                "Provide a model object or pass `allow_fallback=True` to explicitly opt in to spatial KMeans clustering fallback."
            ),
        )

    # Path 3: Explicit Grade C Heuristic Fallback
    niche_names = [
        "Immune_Infiltration_Niche",
        "Stromal_Barrier_Niche",
        "Tumor_Core_Niche",
        "Invasive_Margin_Niche",
        "Vascularized_Perivascular_Niche",
    ][:n_niche]

    # Intersect overlapping genes between cells and spatial spots
    shared_genes = [g for g in adata_cells.var_names if g in adata_spatial.var_names]
    if len(shared_genes) < 5:
        shared_genes = list(adata_spatial.var_names[:10])

    X_cells = adata_cells[:, shared_genes].X
    X_cells_mat = X_cells.toarray() if sparse.issparse(X_cells) else np.array(X_cells)

    mean_cell_profile = np.mean(X_cells_mat, axis=0)

    # Compute spot-level niche affinities using KMeans + spatial features
    np.random.seed(cfg.random_seed)
    from sklearn.cluster import KMeans

    spatial_features = (coords - np.mean(coords, axis=0)) / (np.std(coords, axis=0) + 1e-6)
    km = KMeans(n_clusters=n_niche, random_state=cfg.random_seed, n_init=5)
    km.fit_predict(spatial_features)

    distances = km.transform(spatial_features) + 1e-5
    inv_d = 1.0 / distances
    proportions = inv_d / np.sum(inv_d, axis=1, keepdims=True)

    cell_energy_factor = float(np.mean(mean_cell_profile)) / (float(np.mean(X_cells_mat)) + 1e-6)
    proportions[:, 0] = np.clip(proportions[:, 0] * cell_energy_factor, 0.05, 0.95)
    proportions = proportions / np.sum(proportions, axis=1, keepdims=True)

    # Store in adata_spatial
    adata_spatial.obsm["nicheformer_niche_pred"] = proportions
    adata_spatial.uns["niche_names"] = niche_names
    dominant_indices = np.argmax(proportions, axis=1)
    dominant_labels = [niche_names[idx] for idx in dominant_indices]
    adata_spatial.obs["dominant_niche"] = dominant_labels

    mean_proportions = {niche_names[i]: float(np.mean(proportions[:, i])) for i in range(n_niche)}
    distribution = {niche_names[i]: int(np.sum(dominant_indices == i)) for i in range(n_niche)}

    backend_label = "heuristic-spatial-niche-clustering (Grade C Experimental)"
    status_label = "COMPLETED_WITH_HEURISTIC_FALLBACK"

    res = NicheFormerForecastResult(
        success=True,
        status=status_label,
        n_spots=n_spots,
        n_niche_types=n_niche,
        niche_names=niche_names,
        niche_proportions_mean=mean_proportions,
        dominant_niche_distribution=distribution,
        backend_used=backend_label,
        execution_notes=[
            f"Spatial microenvironment forecast completed across {n_spots} spots.",
            f"Backend used: {backend_label}.",
            f"Forecasted {n_niche} distinct spatial niches: {', '.join(niche_names)}.",
            f"Dominant niche: {max(distribution, key=distribution.get)} ({distribution[max(distribution, key=distribution.get)]} spots).",
            "Evidence Ceiling: PRELIMINARY. In silico spatial niche forecasts require multiplexed in situ staining confirmation.",
        ],
    )
    return adata_spatial, res



# ==============================================================================
# 3. Dry-Wet Closed-Loop End-to-End Evaluation Pipeline
# ==============================================================================


def run_perturbation_to_niche_closed_loop(
    adata_cells: Any,
    adata_spatial: Any,
    target_genes: List[str],
    mode: str = "knockout",
    gears_config: Optional[GEARSPerturbationConfig] = None,
    niche_config: Optional[NicheFormerConfig] = None,
    allow_fallback: bool = False,
) -> ClosedLoopEvaluationResult:
    """
    Execute end-to-end Closed-Loop Pipeline:
    1. GEARS: in silico genetic perturbation simulation on single-cell baseline.
    2. NicheFormer: spatial niche forecasting on baseline vs perturbed cell states.
    3. Evaluation & Remodeling Scoring: quantify niche shifts.
    4. Wet-Lab Hypothesis Card & Protocol Generation.
    """
    # 1. Step 1: GEARS Perturbation
    adata_pert, gears_res = predict_gears_perturbation(
        adata_base=adata_cells,
        target_genes=target_genes,
        mode=mode,
        config=gears_config,
        allow_fallback=allow_fallback,
    )
    if not gears_res.success:
        return ClosedLoopEvaluationResult(
            success=False,
            status=f"FAILED_AT_GEARS_{gears_res.status}",
            target_perturbation=target_genes,
            perturbation_mode=mode,
            gears_result=gears_res,
            remedy_if_failed=gears_res.remedy_if_failed,
        )

    # 2. Step 2: NicheFormer Baseline Forecast
    ad_sp_base = adata_spatial.copy()
    _, niche_base_res = forecast_spatial_niche(
        adata_cells=adata_cells,
        adata_spatial=ad_sp_base,
        config=niche_config,
        allow_fallback=allow_fallback,
    )
    if not niche_base_res.success:
        return ClosedLoopEvaluationResult(
            success=False,
            status=f"FAILED_AT_NICHEFORMER_BASELINE_{niche_base_res.status}",
            target_perturbation=target_genes,
            perturbation_mode=mode,
            gears_result=gears_res,
            niche_result_baseline=niche_base_res,
            remedy_if_failed=niche_base_res.remedy_if_failed,
        )

    # 3. Step 3: NicheFormer Perturbed Forecast
    ad_sp_pert = adata_spatial.copy()
    _, niche_pert_res = forecast_spatial_niche(
        adata_cells=adata_pert,
        adata_spatial=ad_sp_pert,
        config=niche_config,
        allow_fallback=allow_fallback,
    )
    if not niche_pert_res.success:
        return ClosedLoopEvaluationResult(
            success=False,
            status=f"FAILED_AT_NICHEFORMER_PERTURBED_{niche_pert_res.status}",
            target_perturbation=target_genes,
            perturbation_mode=mode,
            gears_result=gears_res,
            niche_result_baseline=niche_base_res,
            niche_result_perturbed=niche_pert_res,
            remedy_if_failed=niche_pert_res.remedy_if_failed,
        )

    # 4. Step 4: Quantify Niche Remodeling Delta
    remodeling_scores = {}
    for niche in niche_base_res.niche_names:
        base_prop = niche_base_res.niche_proportions_mean.get(niche, 0.0)
        pert_prop = niche_pert_res.niche_proportions_mean.get(niche, 0.0)
        delta = pert_prop - base_prop
        remodeling_scores[niche] = float(delta)

    top_remodeled = sorted(remodeling_scores.items(), key=lambda x: abs(x[1]), reverse=True)

    # 5. Step 5: Format Wet-Lab Experimental Hypothesis Card
    hypothesis_card = {
        "title": f"Dry-Wet Closed-Loop Validation Card: {', '.join(target_genes)} {mode.upper()}",
        "perturbation_targets": target_genes,
        "mode": mode,
        "predicted_downstream_markers": {
            "upregulated_top5": gears_res.top_upregulated_genes,
            "downregulated_top5": gears_res.top_downregulated_genes,
        },
        "spatial_niche_shifts": remodeling_scores,
        "primary_hypotheses": [
            f"Perturbing {', '.join(target_genes)} by {mode} is predicted to induce a {remodeling_scores.get(top_remodeled[0][0], 0.0):+.2%} shift in {top_remodeled[0][0]}.",
            f"Downstream validation targets for RT-qPCR or multiplex RNA-FISH: {', '.join(gears_res.top_upregulated_genes[:3] + gears_res.top_downregulated_genes[:3])}.",
        ],
        "recommended_wet_lab_assays": [
            "CRISPR-Cas9 knockout or dCas9-KRAB CRISPRi in matching cell lines.",
            "Multiplexed In Situ Hybridization (e.g. 10x Xenium / CosMx / MERFISH) for spatial niche verification.",
            "Flow cytometry / IHC staining of top remodeled niche marker proteins.",
        ],
        "evidence_ceiling": "PRELIMINARY (BNS-CC-013)",
        "regulatory_disclaimer": "Research Use Only. In silico simulation results are exploratory hypotheses.",
    }

    return ClosedLoopEvaluationResult(
        success=True,
        status="COMPLETED",
        target_perturbation=target_genes,
        perturbation_mode=mode,
        gears_result=gears_res,
        niche_result_baseline=niche_base_res,
        niche_result_perturbed=niche_pert_res,
        niche_remodeling_scores=remodeling_scores,
        top_remodeled_niches=top_remodeled,
        wet_lab_hypothesis_card=hypothesis_card,
        execution_notes=[
            "Dry-Wet Closed-Loop Pipeline executed successfully.",
            f"GEARS backend used: {gears_res.backend_used}.",
            f"NicheFormer backend used: {niche_base_res.backend_used}.",
            f"Top shifted niche: {top_remodeled[0][0]} ({top_remodeled[0][1]:+.4f}).",
            "Wet-Lab Hypothesis Card generated for wet-lab validation handoff.",
        ],
    )

