#!/usr/bin/env python3
"""
Grade-C NNLS spot proportion fit against a caller-supplied signature matrix.

This is not Cell2location and not RCTD. Dominant labels are argmax proportions, not identities.
"""

import argparse
import logging
import os
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.optimize import nnls

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("SpatialDeconvolution")


def build_reference_signature(
    sc_adata, cell_type_col: str = "cell_type", n_top_markers: int = 50, min_expr: float = 0.1
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Build reference cell-type expression signature matrix S (genes x cell_types)
    from single-cell reference AnnData.
    """
    if cell_type_col not in sc_adata.obs:
        raise ValueError(f"Cell type column '{cell_type_col}' not found in single-cell reference obs.")

    cell_types = np.unique(sc_adata.obs[cell_type_col].dropna())
    X = sc_adata.X.toarray() if sparse.issparse(sc_adata.X) else sc_adata.X
    genes = np.array(sc_adata.var_names)

    # Normalize single cell reference counts
    lib_sizes = np.sum(X, axis=1, keepdims=True) + 1e-6
    X_cpm = (X / lib_sizes) * 1e4

    profiles = {}
    selected_genes = set()

    for ct in cell_types:
        mask = (sc_adata.obs[cell_type_col] == ct).values
        if np.sum(mask) == 0:
            continue
        ct_mean = np.mean(X_cpm[mask], axis=0)
        profiles[ct] = ct_mean

        # Select top markers for this cell type vs others
        other_mean = np.mean(X_cpm[~mask], axis=0) if np.sum(~mask) > 0 else np.zeros_like(ct_mean)
        log2_fc = np.log2((ct_mean + 1.0) / (other_mean + 1.0))
        valid_idx = np.where((ct_mean > min_expr))[0]
        if len(valid_idx) > 0:
            top_local = valid_idx[np.argsort(-log2_fc[valid_idx])[:n_top_markers]]
            selected_genes.update(genes[top_local])

    sig_df = pd.DataFrame(profiles, index=genes)
    marker_gene_list = list(selected_genes)
    logger.info(
        f"Built reference signature for {len(cell_types)} cell types using {len(marker_gene_list)} marker genes."
    )
    return sig_df, marker_gene_list


def deconvolve_spatial_spots(
    spatial_adata,
    reference_sig: pd.DataFrame,
    marker_genes: Optional[List[str]] = None,
    min_prop_threshold: float = 0.02,
) -> pd.DataFrame:
    """
    Deconvolve each spatial spot into cell type proportions using Non-Negative Least Squares (NNLS).
    Minimizes || x_spot - S * w ||^2 s.t. w >= 0, then normalizes sum(w) = 1.
    """
    # Intersect genes
    if marker_genes:
        shared_genes = [g for g in marker_genes if g in spatial_adata.var_names and g in reference_sig.index]
    else:
        shared_genes = [g for g in reference_sig.index if g in spatial_adata.var_names]

    if len(shared_genes) < 10:
        raise ValueError(f"Insufficient overlapping marker genes ({len(shared_genes)}) between spatial and reference.")

    logger.info(f"Deconvolving {spatial_adata.n_obs} spots across {len(shared_genes)} intersecting marker genes...")
    S = reference_sig.loc[shared_genes].to_numpy(dtype=float)  # (G, K)
    cell_types = list(reference_sig.columns)

    # Extract spatial count matrix for shared genes
    spatial_sub = spatial_adata[:, shared_genes]
    X_spatial = spatial_sub.X.toarray() if sparse.issparse(spatial_sub.X) else spatial_sub.X

    # Normalize spatial spots
    lib_sizes = np.sum(X_spatial, axis=1, keepdims=True) + 1e-6
    X_spatial_cpm = (X_spatial / lib_sizes) * 1e4

    n_spots = X_spatial.shape[0]
    n_types = len(cell_types)
    proportions = np.zeros((n_spots, n_types), dtype=float)

    for i in range(n_spots):
        spot_vec = X_spatial_cpm[i]
        weights, _ = nnls(S, spot_vec)
        tot = np.sum(weights)
        if tot > 0:
            norm_w = weights / tot
            # Apply sparsity threshold
            norm_w[norm_w < min_prop_threshold] = 0.0
            re_tot = np.sum(norm_w)
            proportions[i] = (norm_w / re_tot) if re_tot > 0 else (weights / tot)
        else:
            proportions[i] = np.ones(n_types) / n_types

    prop_df = pd.DataFrame(proportions, index=spatial_adata.obs_names, columns=cell_types)

    # Store in spatial AnnData
    spatial_adata.obsm["cell_type_proportions"] = prop_df.to_numpy()
    spatial_adata.uns["cell_type_names"] = cell_types

    # Assign dominant cell type per spot
    dominant_idx = np.argmax(proportions, axis=1)
    spatial_adata.obs["dominant_cell_type"] = pd.Categorical([cell_types[idx] for idx in dominant_idx])

    # Assign top 3 cell types in string format
    top_ct_strings = []
    for i in range(n_spots):
        top_indices = np.argsort(-proportions[i])[:3]
        labels = [f"{cell_types[idx]}:{proportions[i, idx]:.2f}" for idx in top_indices if proportions[i, idx] > 0.05]
        top_ct_strings.append("; ".join(labels) if labels else "Unassigned")
    spatial_adata.obs["top_cell_types"] = top_ct_strings

    logger.info("Deconvolution completed successfully.")
    return prop_df


def main():
    parser = argparse.ArgumentParser(description="Spot-Level Cell Type Deconvolution")
    parser.add_argument("--spatial-input", "-s", required=True, help="Spatial AnnData .h5ad file")
    parser.add_argument("--sc-reference", "-r", required=True, help="Single-cell reference AnnData .h5ad file")
    parser.add_argument("--output", "-o", required=True, help="Output deconvolved spatial .h5ad file")
    parser.add_argument("--cell-type-col", default="cell_type", help="Column name in reference obs for cell types")
    parser.add_argument("--min-prop", type=float, default=0.02, help="Minimum proportion threshold")

    args = parser.parse_args()
    import scanpy as sc

    spatial_adata = sc.read_h5ad(args.spatial_input)
    sc_adata = sc.read_h5ad(args.sc_reference)

    sig_df, markers = build_reference_signature(sc_adata, cell_type_col=args.cell_type_col)
    deconvolve_spatial_spots(spatial_adata, sig_df, marker_genes=markers, min_prop_threshold=args.min_prop)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    spatial_adata.write_h5ad(args.output)
    logger.info(f"Saved deconvolved spatial dataset to {args.output}")


if __name__ == "__main__":
    main()
