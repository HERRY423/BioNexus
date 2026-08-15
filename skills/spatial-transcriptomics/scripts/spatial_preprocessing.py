#!/usr/bin/env python3
"""
Spatial Transcriptomics Preprocessing & Quality Control Module.
Handles coordinate normalization, tissue boundary filtering, spatial outlier detection,
and spot/cell-level quality metrics for Visium, Xenium, MERFISH, and Stereo-seq platforms.
"""

import argparse
import logging
import os
from typing import Any, Dict, Tuple

import numpy as np
from scipy import sparse
from scipy.spatial import cKDTree

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("SpatialPreprocessing")

_PLATFORM_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "configs",
    "platform_configs.yml",
)


def load_platform_config(platform: str) -> Dict[str, Any]:
    """Load hardware defaults for a named platform. Unknown names return empty dict."""
    try:
        import yaml
    except ImportError:
        return {}
    if not os.path.exists(_PLATFORM_CONFIG_PATH):
        return {}
    with open(_PLATFORM_CONFIG_PATH, "r", encoding="utf-8") as handle:
        catalog = yaml.safe_load(handle) or {}
    return dict((catalog.get("platforms") or {}).get(platform, {}))


def load_spatial_anndata(file_path: str, platform: str = "visium"):
    """Load spatial AnnData dataset and ensure spatial coordinates are accessible."""
    try:
        import anndata as ad  # noqa: F401
        import scanpy as sc
    except ImportError:
        raise ImportError("scanpy and anndata are required for spatial preprocessing.")

    logger.info(f"Loading spatial dataset from {file_path} (platform: {platform})...")
    if file_path.endswith(".h5ad"):
        adata = sc.read_h5ad(file_path)
    elif file_path.endswith(".h5"):
        adata = sc.read_10x_h5(file_path)
    else:
        raise ValueError(f"Unsupported file format: {file_path}. Expected .h5ad or .h5.")

    # Validate or set spatial coordinates in obsm['spatial']
    if "spatial" not in adata.obsm:
        # Check alternative coordinate columns in obs
        coord_cols = [
            ("x", "y"),
            ("X", "Y"),
            ("imagecol", "imagerow"),
            ("array_col", "array_row"),
            ("spatial_x", "spatial_y"),
        ]
        found = False
        for x_col, y_col in coord_cols:
            if x_col in adata.obs and y_col in adata.obs:
                adata.obsm["spatial"] = adata.obs[[x_col, y_col]].to_numpy(dtype=float)
                logger.info(f"Constructed obsm['spatial'] from obs['{x_col}'], obs['{y_col}'].")
                found = True
                break
        if not found:
            raise ValueError("No spatial coordinates in obsm['spatial'] or obs x/y columns. Refusing to invent a grid.")

    return adata


def calculate_spatial_qc_metrics(adata, spatial_key: str = "spatial", n_spatial_neighbors: int = 6) -> Dict[str, Any]:
    """
    Calculate comprehensive spatial transcriptomics quality control metrics:
      - Library size (total counts per spot/cell)
      - Number of detected genes per spot
      - Mitochondrial gene percentage
      - Spatial neighbor distance & isolated spot score
    """
    X = adata.X
    is_sparse = sparse.issparse(X)

    # 1. Total counts & detected genes
    if is_sparse:
        total_counts = np.array(X.sum(axis=1)).flatten()
        n_genes_by_counts = np.array((X > 0).sum(axis=1)).flatten()
    else:
        total_counts = np.sum(X, axis=1).flatten()
        n_genes_by_counts = np.sum(X > 0, axis=1).flatten()

    adata.obs["total_counts"] = total_counts
    adata.obs["n_genes_by_counts"] = n_genes_by_counts

    # 2. Mitochondrial %
    mt_genes = [name for name in adata.var_names if name.upper().startswith(("MT-", "MT_", "MT."))]
    if mt_genes:
        mt_mask = np.isin(adata.var_names, mt_genes)
        if is_sparse:
            mt_counts = np.array(X[:, mt_mask].sum(axis=1)).flatten()
        else:
            mt_counts = np.sum(X[:, mt_mask], axis=1).flatten()
        pct_counts_mt = np.where(total_counts > 0, (mt_counts / total_counts) * 100.0, 0.0)
    else:
        pct_counts_mt = np.zeros(adata.n_obs, dtype=float)
    adata.obs["pct_counts_mt"] = pct_counts_mt

    # 3. Spatial neighborhood density via KDTree
    coords = adata.obsm.get(spatial_key, np.zeros((adata.n_obs, 2)))
    tree = cKDTree(coords)
    k = min(n_spatial_neighbors + 1, adata.n_obs)
    distances, _ = tree.query(coords, k=k)
    # Average distance to k nearest spatial neighbors
    mean_neighbor_dist = np.mean(distances[:, 1:], axis=1) if distances.shape[1] > 1 else np.zeros(adata.n_obs)
    adata.obs["spatial_neighbor_dist"] = mean_neighbor_dist

    # Isolated spots (distance > 3 * median distance)
    med_dist = np.median(mean_neighbor_dist) if len(mean_neighbor_dist) > 0 else 1.0
    adata.obs["is_spatial_outlier"] = mean_neighbor_dist > (3.0 * (med_dist + 1e-6))

    summary = {
        "n_spots": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "median_counts": float(np.median(total_counts)),
        "median_genes": float(np.median(n_genes_by_counts)),
        "median_pct_mt": float(np.median(pct_counts_mt)),
        "n_spatial_outliers": int(np.sum(adata.obs["is_spatial_outlier"])),
    }
    return summary


def filter_spatial_spots(
    adata,
    min_counts: int = 300,
    min_genes: int = 200,
    max_pct_mt: float = 25.0,
    in_tissue_only: bool = True,
    remove_spatial_outliers: bool = False,
):
    """Filter spots/cells according to spatial transcriptomics criteria."""
    n_init = adata.n_obs
    mask = np.ones(n_init, dtype=bool)

    if in_tissue_only and "in_tissue" in adata.obs:
        mask &= adata.obs["in_tissue"].astype(int) == 1

    if "total_counts" in adata.obs:
        mask &= adata.obs["total_counts"] >= min_counts

    if "n_genes_by_counts" in adata.obs:
        mask &= adata.obs["n_genes_by_counts"] >= min_genes

    if "pct_counts_mt" in adata.obs:
        mask &= adata.obs["pct_counts_mt"] <= max_pct_mt

    if remove_spatial_outliers and "is_spatial_outlier" in adata.obs:
        mask &= ~adata.obs["is_spatial_outlier"]

    adata_filtered = adata[mask].copy()
    n_retained = adata_filtered.n_obs
    logger.info(f"Spatial filtering: {n_init} -> {n_retained} spots ({n_retained / n_init * 100:.1f}% retained).")
    return adata_filtered


def normalize_spatial_coordinates(
    adata, spatial_key: str = "spatial", target_range: Tuple[float, float] = (0.0, 1000.0)
):
    """Min-max normalize spatial coordinates into standard coordinate frame."""
    coords = adata.obsm[spatial_key].copy().astype(float)
    c_min = coords.min(axis=0)
    c_max = coords.max(axis=0)
    c_range = c_max - c_min
    c_range[c_range == 0] = 1.0

    normalized = target_range[0] + (coords - c_min) / c_range * (target_range[1] - target_range[0])
    adata.obsm[f"{spatial_key}_normalized"] = normalized
    return adata


def main():
    parser = argparse.ArgumentParser(description="Spatial Transcriptomics Preprocessing & QC")
    parser.add_argument("--input", "-i", required=True, help="Input AnnData .h5ad or 10X .h5 file")
    parser.add_argument("--output", "-o", required=True, help="Output filtered .h5ad file")
    parser.add_argument(
        "--platform", default="visium", choices=["visium", "visium_hd", "xenium", "merfish", "cosmx", "stereoseq"]
    )
    parser.add_argument("--min-counts", type=int, default=300, help="Minimum total UMI counts per spot")
    parser.add_argument("--min-genes", type=int, default=200, help="Minimum detected genes per spot")
    parser.add_argument("--max-mt", type=float, default=20.0, help="Maximum mitochondrial count percentage")

    args = parser.parse_args()
    platform_cfg = load_platform_config(args.platform)
    min_counts = args.min_counts if args.min_counts != 300 else int(platform_cfg.get("recommended_min_counts", 300))
    min_genes = args.min_genes if args.min_genes != 200 else int(platform_cfg.get("recommended_min_genes", 200))
    n_neighbors = int(platform_cfg.get("n_spatial_neighbors", 6)) if platform_cfg else 6
    spatial_key = platform_cfg.get("default_spatial_key", "spatial")
    logger.info(
        "Platform %s: min_counts=%s min_genes=%s n_neighbors=%s (from platform_configs.yml when present).",
        args.platform,
        min_counts,
        min_genes,
        n_neighbors,
    )
    adata = load_spatial_anndata(args.input, platform=args.platform)
    if "platform" not in adata.uns:
        adata.uns["platform"] = args.platform
        adata.uns["platform_config"] = {k: v for k, v in platform_cfg.items() if not isinstance(v, list)}
    summary = calculate_spatial_qc_metrics(adata, spatial_key=spatial_key, n_spatial_neighbors=n_neighbors)
    logger.info(f"Initial QC Summary: {summary}")

    adata_filtered = filter_spatial_spots(adata, min_counts=min_counts, min_genes=min_genes, max_pct_mt=args.max_mt)
    normalize_spatial_coordinates(adata_filtered)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    adata_filtered.write_h5ad(args.output)
    logger.info(f"Saved preprocessed spatial dataset to {args.output}")


if __name__ == "__main__":
    main()
