#!/usr/bin/env python3
"""
SVG ranking via squidpy Moran when installed; otherwise local I with heuristic variance.

This is not SpatialDE, SPARK, or Seurat FindSpatiallyVariableFeatures.
Prefer spatial_pipeline.py (refuses without squidpy).
"""

import argparse
import logging
import os
from typing import Tuple

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.spatial import cKDTree
from scipy.stats import norm

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("SpatialVariableGenes")


def compute_spatial_weights_matrix(coords: np.ndarray, n_neighbors: int = 6) -> sparse.csr_matrix:
    """Build row-standardized k-nearest spatial neighbor adjacency matrix."""
    n_cells = len(coords)
    k = min(n_neighbors + 1, n_cells)
    tree = cKDTree(coords)
    dists, indices = tree.query(coords, k=k)

    row_ind = np.repeat(np.arange(n_cells), k - 1)
    col_ind = indices[:, 1:].flatten()
    # Binary connectivity or inverse distance
    weights = np.ones(len(col_ind), dtype=float)

    W = sparse.csr_matrix((weights, (row_ind, col_ind)), shape=(n_cells, n_cells))
    # Row-standardize: sum of each row = 1
    row_sums = np.array(W.sum(axis=1)).flatten()
    row_sums[row_sums == 0] = 1.0
    inv_diag = sparse.diags(1.0 / row_sums)
    W_norm = inv_diag.dot(W)
    return W_norm


def calculate_morans_i_vectorized(
    X_mat: np.ndarray, W_norm: sparse.csr_matrix
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Vectorized computation of Moran's I, analytical z-scores, and p-values
    for all genes simultaneously across N spots.
    """
    N, G = X_mat.shape
    # Center each gene
    means = np.mean(X_mat, axis=0, keepdims=True)
    Z = X_mat - means  # (N, G)

    # Denominator: sum of squared deviations
    sum_sq = np.sum(Z**2, axis=0)  # (G,)
    sum_sq[sum_sq == 0] = 1e-12

    # Numerator: Z.T * (W_norm * Z) diagonal elements
    WZ = W_norm.dot(Z)  # (N, G)
    numerator = np.sum(Z * WZ, axis=0)  # (G,)

    # Total sum of weights for row-standardized matrix = N
    S0 = N
    I_scores = (N / S0) * (numerator / sum_sq)

    # Expected value E[I] = -1 / (N - 1)
    E_I = -1.0 / (N - 1.0)

    # Variance under a simple randomization approximation — not Clifford–Ord.
    var_I = 1.0 / (N + 1.0)
    z_scores = (I_scores - E_I) / np.sqrt(var_I)
    # One-sided p-value for positive spatial autocorrelation
    p_values = 1.0 - norm.cdf(z_scores)

    return I_scores, z_scores, p_values


def detect_spatially_variable_genes(
    adata, spatial_key: str = "spatial", n_neighbors: int = 6, min_cells: int = 10, top_n: int = 500
) -> pd.DataFrame:
    """
    Detect spatially variable genes using vectorized Moran's I.
    Stores ranking metrics in `adata.var` and returns a summary DataFrame.
    """
    coords = adata.obsm.get(spatial_key)
    if coords is None:
        raise ValueError(f"Coordinates '{spatial_key}' not found in adata.obsm.")

    logger.info(f"Computing spatial autocorrelation (Moran's I) across {adata.n_vars} genes...")
    try:
        import squidpy as sq

        knn = getattr(sq.gr, "spatial_neighbors_knn", None)
        if knn is not None:
            knn(adata, spatial_key=spatial_key, n_neighs=n_neighbors)
        else:
            sq.gr.spatial_neighbors(adata, coord_type="generic", spatial_key=spatial_key, n_neighs=n_neighbors)
        sq.gr.spatial_autocorr(adata, mode="moran")
        moran = adata.uns.get("moranI")
        if moran is not None:
            results_df = pd.DataFrame(moran).reset_index().rename(columns={"index": "gene"})
            if "I" in results_df.columns:
                results_df = results_df.rename(columns={"I": "morans_i"})
            if "pval_norm_fdr_bh" in results_df.columns and "fdr_q_value" not in results_df.columns:
                results_df["fdr_q_value"] = results_df["pval_norm_fdr_bh"]
            elif "fdr_q_value" not in results_df.columns:
                results_df["fdr_q_value"] = np.nan
            results_df = results_df.sort_values(by="morans_i", ascending=False).reset_index(drop=True)
            results_df["svg_rank"] = np.arange(1, len(results_df) + 1)
            results_df.attrs["method"] = "squidpy.gr.spatial_autocorr"
            results_df.attrs["variance_model"] = "squidpy_default"
            results_df.attrs["evidence_grade"] = "A"
            results_df.attrs["limitations"] = "Moran's I via squidpy. Prefer I ranking over unadjusted p-values."
            adata.var["spatial_morans_i"] = np.nan
            adata.var["is_svg"] = False
            if "gene" in results_df.columns:
                overlap = [g for g in results_df["gene"] if g in adata.var_names]
                adata.var.loc[overlap, "spatial_morans_i"] = results_df.set_index("gene").loc[overlap, "morans_i"]
                adata.var.loc[results_df.head(top_n)["gene"].values, "is_svg"] = True
            return results_df.head(top_n) if top_n else results_df
    except Exception as exc:
        logger.info("squidpy Moran unavailable (%s); using local heuristic I.", exc)

    X = adata.X.toarray() if sparse.issparse(adata.X) else adata.X
    genes = np.array(adata.var_names)

    # Filter lowly expressed genes
    expressed_mask = np.sum(X > 0, axis=0) >= min_cells
    if np.sum(expressed_mask) == 0:
        expressed_mask = np.ones(len(genes), dtype=bool)

    X_filtered = X[:, expressed_mask]
    genes_filtered = genes[expressed_mask]

    # Normalize expression per spot
    lib_sizes = np.sum(X_filtered, axis=1, keepdims=True) + 1e-6
    X_norm = np.log1p((X_filtered / lib_sizes) * 1e4)

    # Build spatial weights matrix
    W_norm = compute_spatial_weights_matrix(coords, n_neighbors=n_neighbors)

    # Compute Moran's I
    morans_i, z_scores, p_values = calculate_morans_i_vectorized(X_norm, W_norm)

    # Benjamini-Hochberg FDR correction
    n_tested = len(p_values)
    sort_idx = np.argsort(p_values)
    fdr = np.zeros(n_tested)
    cum_min = 1.0
    for rank, idx in enumerate(reversed(sort_idx)):
        k = n_tested - rank
        val = (p_values[idx] * n_tested) / k
        cum_min = min(cum_min, val)
        fdr[idx] = min(1.0, cum_min)

    results_df = pd.DataFrame(
        {"gene": genes_filtered, "morans_i": morans_i, "z_score": z_scores, "p_value": p_values, "fdr_q_value": fdr}
    )
    results_df = results_df.sort_values(by="morans_i", ascending=False).reset_index(drop=True)
    results_df["svg_rank"] = np.arange(1, len(results_df) + 1)
    results_df.attrs["method"] = "morans_i_row_standardized_knn"
    results_df.attrs["variance_model"] = "heuristic_1_over_n_plus_1_not_clifford_ord"
    results_df.attrs["evidence_grade"] = "C"
    results_df.attrs["limitations"] = (
        "z/FDR use var=1/(N+1), not Clifford-Ord or permutation. Rank by Moran's I, not p-values."
    )

    # Store back in adata.var
    adata.var["spatial_morans_i"] = np.nan
    adata.var["spatial_fdr"] = np.nan
    adata.var["is_svg"] = False

    top_svg_genes = results_df.head(top_n)["gene"].values
    adata.var.loc[results_df["gene"], "spatial_morans_i"] = results_df["morans_i"].values
    adata.var.loc[results_df["gene"], "spatial_fdr"] = results_df["fdr_q_value"].values
    adata.var.loc[top_svg_genes, "is_svg"] = True

    logger.info(f"Identified top SVGs. Top 5: {list(results_df.head(5)['gene'].values)}")
    return results_df


def main():
    parser = argparse.ArgumentParser(description="Spatial Variable Gene Detection")
    parser.add_argument("--input", "-i", required=True, help="Preprocessed spatial AnnData .h5ad file")
    parser.add_argument("--output-adata", "-o", required=True, help="Output AnnData with SVG annotations")
    parser.add_argument("--output-csv", "-c", required=True, help="Output CSV of ranked SVGs")
    parser.add_argument("--top-n", type=int, default=500, help="Number of top SVGs to flag")

    args = parser.parse_args()
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    svg_df = detect_spatially_variable_genes(adata, top_n=args.top_n)

    os.makedirs(os.path.dirname(os.path.abspath(args.output_adata)) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.output_csv)) or ".", exist_ok=True)
    adata.write_h5ad(args.output_adata)
    svg_df.to_csv(args.output_csv, index=False)
    logger.info(f"Saved SVG annotations to {args.output_adata} and rankings to {args.output_csv}")


if __name__ == "__main__":
    main()
