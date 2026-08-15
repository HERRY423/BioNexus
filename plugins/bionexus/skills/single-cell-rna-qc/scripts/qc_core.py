#!/usr/bin/env python3
"""
Core utility functions for single-cell RNA-seq quality control.
High-Performance & Memory-Optimized Edition for Large Datasets (100k+ cells).

This module provides building blocks for metrics calculation, chunked processing,
sparse matrix vectorization, and MAD-based filtering following scverse best practices:
https://www.sc-best-practices.org/preprocessing_visualization/quality_control.html
"""

from typing import Optional

import anndata as ad
import numpy as np
import scanpy as sc
import scipy.sparse as sp
from scipy.stats import median_abs_deviation


def calculate_qc_metrics_fast(
    adata: ad.AnnData,
    mt_pattern: str = "mt-,MT-",
    ribo_pattern: str = "Rpl,Rps,RPL,RPS",
    hb_pattern: str = "^Hb[^(p)]|^HB[^(P)]",
    inplace: bool = True,
) -> Optional[ad.AnnData]:
    """
    High-performance vectorized calculation of QC metrics.
    Optimized for CSR/CSC sparse matrices with zero dense memory duplication.

    Parameters
    ----------
    adata : AnnData
        Annotated data matrix (in-memory or backed)
    mt_pattern : str
        Comma-separated mitochondrial gene prefixes
    ribo_pattern : str
        Comma-separated ribosomal gene prefixes
    hb_pattern : str
        Regex pattern for hemoglobin genes
    inplace : bool
        Modify adata in place (default: True)

    Returns
    -------
    AnnData or None
    """
    if not inplace:
        adata = adata.copy()

    # Identify gene subsets
    mt_prefixes = tuple(mt_pattern.split(","))
    adata.var["mt"] = adata.var_names.str.startswith(mt_prefixes)

    ribo_prefixes = tuple(ribo_pattern.split(","))
    adata.var["ribo"] = adata.var_names.str.startswith(ribo_prefixes)

    adata.var["hb"] = adata.var_names.str.match(hb_pattern)

    X = adata.X

    if sp.issparse(X):
        # Ultra-fast sparse vectorization
        if not sp.isspmatrix_csr(X):
            X_csr = X.tocsr()
        else:
            X_csr = X

        # Total counts per cell
        total_counts = np.asarray(X_csr.sum(axis=1)).ravel()

        # Detected genes per cell (non-zero entries per row)
        n_genes_by_counts = np.diff(X_csr.indptr)

        # Mitochondrial counts
        mt_indices = np.where(adata.var["mt"].values)[0]
        if len(mt_indices) > 0:
            total_counts_mt = np.asarray(X_csr[:, mt_indices].sum(axis=1)).ravel()
            pct_counts_mt = (
                np.divide(
                    total_counts_mt, total_counts, out=np.zeros_like(total_counts, dtype=float), where=total_counts > 0
                )
                * 100
            )
        else:
            total_counts_mt = np.zeros(adata.n_obs, dtype=float)
            pct_counts_mt = np.zeros(adata.n_obs, dtype=float)

        # Ribosomal counts
        ribo_indices = np.where(adata.var["ribo"].values)[0]
        if len(ribo_indices) > 0:
            total_counts_ribo = np.asarray(X_csr[:, ribo_indices].sum(axis=1)).ravel()
            pct_counts_ribo = (
                np.divide(
                    total_counts_ribo,
                    total_counts,
                    out=np.zeros_like(total_counts, dtype=float),
                    where=total_counts > 0,
                )
                * 100
            )
        else:
            total_counts_ribo = np.zeros(adata.n_obs, dtype=float)
            pct_counts_ribo = np.zeros(adata.n_obs, dtype=float)

        # Hemoglobin counts
        hb_indices = np.where(adata.var["hb"].values)[0]
        if len(hb_indices) > 0:
            total_counts_hb = np.asarray(X_csr[:, hb_indices].sum(axis=1)).ravel()
            pct_counts_hb = (
                np.divide(
                    total_counts_hb, total_counts, out=np.zeros_like(total_counts, dtype=float), where=total_counts > 0
                )
                * 100
            )
        else:
            total_counts_hb = np.zeros(adata.n_obs, dtype=float)
            pct_counts_hb = np.zeros(adata.n_obs, dtype=float)

        adata.obs["total_counts"] = total_counts
        adata.obs["n_genes_by_counts"] = n_genes_by_counts
        adata.obs["total_counts_mt"] = total_counts_mt
        adata.obs["pct_counts_mt"] = pct_counts_mt
        adata.obs["total_counts_ribo"] = total_counts_ribo
        adata.obs["pct_counts_ribo"] = pct_counts_ribo
        adata.obs["total_counts_hb"] = total_counts_hb
        adata.obs["pct_counts_hb"] = pct_counts_hb

        # Gene level metrics
        adata.var["n_cells_by_counts"] = np.asarray((X_csr > 0).sum(axis=0)).ravel()
        adata.var["total_counts"] = np.asarray(X_csr.sum(axis=0)).ravel()

    else:
        # Standard Scanpy call for dense/custom layers
        sc.pp.calculate_qc_metrics(adata, qc_vars=["mt", "ribo", "hb"], percent_top=None, log1p=False, inplace=True)

    if not inplace:
        return adata


def calculate_qc_metrics(
    adata, mt_pattern="mt-,MT-", ribo_pattern="Rpl,Rps,RPL,RPS", hb_pattern="^Hb[^(p)]|^HB[^(P)]", inplace=True
):
    """Calculate QC metrics with auto-selection of high-performance vectorized path."""
    return calculate_qc_metrics_fast(
        adata, mt_pattern=mt_pattern, ribo_pattern=ribo_pattern, hb_pattern=hb_pattern, inplace=inplace
    )


def calculate_qc_metrics_chunked(
    adata: ad.AnnData,
    chunk_size: int = 50000,
    mt_pattern: str = "mt-,MT-",
    ribo_pattern: str = "Rpl,Rps,RPL,RPS",
    hb_pattern: str = "^Hb[^(p)]|^HB[^(P)]",
):
    """
    Chunked QC calculation for ultra-large or backed AnnData (100k+ cells).
    Processes cells in chunks to keep peak memory minimal.
    """
    n_cells = adata.n_obs
    print(f"Chunked QC computation: processing {n_cells} cells in chunks of {chunk_size}...")

    # Gene categories
    mt_prefixes = tuple(mt_pattern.split(","))
    adata.var["mt"] = adata.var_names.str.startswith(mt_prefixes)
    ribo_prefixes = tuple(ribo_pattern.split(","))
    adata.var["ribo"] = adata.var_names.str.startswith(ribo_prefixes)
    adata.var["hb"] = adata.var_names.str.match(hb_pattern)

    obs_metrics = {
        "total_counts": np.zeros(n_cells, dtype=float),
        "n_genes_by_counts": np.zeros(n_cells, dtype=int),
        "pct_counts_mt": np.zeros(n_cells, dtype=float),
        "pct_counts_ribo": np.zeros(n_cells, dtype=float),
        "pct_counts_hb": np.zeros(n_cells, dtype=float),
    }

    for start in range(0, n_cells, chunk_size):
        end = min(start + chunk_size, n_cells)
        sub_X = adata[start:end].X
        if not sp.issparse(sub_X):
            sub_X = sp.csr_matrix(sub_X)
        elif not sp.isspmatrix_csr(sub_X):
            sub_X = sub_X.tocsr()

        sub_counts = np.asarray(sub_X.sum(axis=1)).ravel()
        sub_genes = np.diff(sub_X.indptr)

        obs_metrics["total_counts"][start:end] = sub_counts
        obs_metrics["n_genes_by_counts"][start:end] = sub_genes

        # mt
        mt_idx = np.where(adata.var["mt"].values)[0]
        if len(mt_idx) > 0:
            mt_counts = np.asarray(sub_X[:, mt_idx].sum(axis=1)).ravel()
            obs_metrics["pct_counts_mt"][start:end] = (
                np.divide(mt_counts, sub_counts, out=np.zeros_like(sub_counts, dtype=float), where=sub_counts > 0) * 100
            )

        # ribo
        ribo_idx = np.where(adata.var["ribo"].values)[0]
        if len(ribo_idx) > 0:
            ribo_counts = np.asarray(sub_X[:, ribo_idx].sum(axis=1)).ravel()
            obs_metrics["pct_counts_ribo"][start:end] = (
                np.divide(ribo_counts, sub_counts, out=np.zeros_like(sub_counts, dtype=float), where=sub_counts > 0)
                * 100
            )

    for k, v in obs_metrics.items():
        adata.obs[k] = v

    print(f"Chunked QC computation complete across {n_cells} cells.")


def detect_outliers_mad(adata, metric, n_mads, verbose=True):
    """Detect outliers using Median Absolute Deviation (MAD)."""
    metric_values = adata.obs[metric].values
    median = np.median(metric_values)
    mad = median_abs_deviation(metric_values)

    lower = median - n_mads * mad
    upper = median + n_mads * mad

    outlier_mask = (metric_values < lower) | (metric_values > upper)

    if verbose:
        print(f"  {metric}:")
        print(f"    Median: {median:.2f}, MAD: {mad:.2f}")
        print(f"    Bounds: [{lower:.2f}, {upper:.2f}] ({n_mads} MADs)")
        print(f"    Outliers: {outlier_mask.sum()} cells ({outlier_mask.sum() / len(metric_values) * 100:.2f}%)")

    return outlier_mask


def apply_hard_threshold(adata, metric, threshold, operator=">", verbose=True):
    """Apply a hard threshold filter."""
    metric_values = adata.obs[metric].values

    if operator == ">":
        mask = metric_values > threshold
    elif operator == "<":
        mask = metric_values < threshold
    elif operator == ">=":
        mask = metric_values >= threshold
    elif operator == "<=":
        mask = metric_values <= threshold
    else:
        raise ValueError(f"Invalid operator: {operator}. Use '>', '<', '>=', or '<='")

    if verbose:
        print(f"  {metric} {operator} {threshold}:")
        print(f"    Cells filtered: {mask.sum()} ({mask.sum() / len(metric_values) * 100:.2f}%)")

    return mask


def filter_cells(adata, mask):
    """Filter cells based on a boolean mask."""
    return adata[mask].copy()


def filter_genes(adata, min_cells=20, min_counts=None, inplace=True):
    """Filter genes based on detection thresholds."""
    if not inplace:
        adata = adata.copy()

    if min_cells is not None:
        sc.pp.filter_genes(adata, min_cells=min_cells)

    if min_counts is not None:
        sc.pp.filter_genes(adata, min_counts=min_counts)

    if not inplace:
        return adata


def print_qc_summary(adata, label=""):
    """Print summary statistics for QC metrics."""
    if label:
        print(f"\n{label}:")
    print(f"  Cells: {adata.n_obs}")
    print(f"  Genes: {adata.n_vars}")

    if "total_counts" in adata.obs:
        print(f"  Mean counts per cell: {adata.obs['total_counts'].mean():.0f}")
        print(f"  Median counts per cell: {adata.obs['total_counts'].median():.0f}")

    if "n_genes_by_counts" in adata.obs:
        print(f"  Mean genes per cell: {adata.obs['n_genes_by_counts'].mean():.0f}")
        print(f"  Median genes per cell: {adata.obs['n_genes_by_counts'].median():.0f}")

    if "pct_counts_mt" in adata.obs:
        print(f"  Mean mitochondrial %: {adata.obs['pct_counts_mt'].mean():.2f}%")

    if "pct_counts_ribo" in adata.obs:
        print(f"  Mean ribosomal %: {adata.obs['pct_counts_ribo'].mean():.2f}%")
