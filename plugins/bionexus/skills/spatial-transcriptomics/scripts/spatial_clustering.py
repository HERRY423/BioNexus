#!/usr/bin/env python3
"""
Grade-C fused kNN + expression graph + spectral/KMeans clustering.

This is not BayesSpace and not SpaGCN. Prefer spatial_pipeline.py (squidpy).
"""

import argparse
import logging
import os
from typing import Any, Dict

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.spatial import cKDTree
from sklearn.cluster import SpectralClustering
from sklearn.decomposition import PCA
from sklearn.neighbors import kneighbors_graph

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("SpatialClustering")


def build_fused_spatial_graph(
    adata,
    n_pcs: int = 30,
    n_spatial_neighbors: int = 6,
    n_expression_neighbors: int = 15,
    spatial_weight: float = 0.35,
    spatial_key: str = "spatial",
) -> sparse.csr_matrix:
    """
    Construct a fused affinity graph:
      W_fused = (1 - alpha) * W_expression + alpha * W_spatial
    where alpha = spatial_weight in [0, 1].
    """
    n_cells = adata.n_obs
    spatial_coords = adata.obsm.get(spatial_key)
    if spatial_coords is None:
        raise ValueError(f"Spatial coordinates key '{spatial_key}' not found in adata.obsm.")

    # 1. Spatial adjacency graph via KDTree (k-nearest physical neighbors)
    k_sp = min(n_spatial_neighbors, n_cells - 1)
    tree = cKDTree(spatial_coords)
    dists, indices = tree.query(spatial_coords, k=k_sp + 1)

    row_ind = np.repeat(np.arange(n_cells), k_sp)
    col_ind = indices[:, 1:].flatten()
    # Gaussian kernel on physical distances
    spatial_dists = dists[:, 1:].flatten()
    sigma_sp = np.median(spatial_dists) if np.median(spatial_dists) > 0 else 1.0
    sp_weights = np.exp(-(spatial_dists**2) / (2 * sigma_sp**2 + 1e-8))

    W_spatial = sparse.csr_matrix((sp_weights, (row_ind, col_ind)), shape=(n_cells, n_cells))
    # Symmetrize spatial graph
    W_spatial = 0.5 * (W_spatial + W_spatial.T)

    # 2. Expression adjacency graph via PCA
    if "X_pca" in adata.obsm:
        X_pca = adata.obsm["X_pca"][:, :n_pcs]
    else:
        X = adata.X.toarray() if sparse.issparse(adata.X) else adata.X
        # Normalize and PCA
        X_norm = np.log1p(X / (np.sum(X, axis=1, keepdims=True) + 1e-6) * 1e4)
        pca = PCA(n_components=min(n_pcs, X.shape[1], n_cells - 1), random_state=42)
        X_pca = pca.fit_transform(X_norm)
        adata.obsm["X_pca"] = X_pca

    k_exp = min(n_expression_neighbors, n_cells - 1)
    W_expression = kneighbors_graph(X_pca, n_neighbors=k_exp, mode="connectivity", metric="cosine", include_self=False)
    W_expression = 0.5 * (W_expression + W_expression.T)

    # 3. Fuse graphs
    alpha = np.clip(spatial_weight, 0.0, 1.0)
    W_fused = (1.0 - alpha) * W_expression + alpha * W_spatial
    W_fused = sparse.csr_matrix(W_fused)
    return W_fused


def smooth_spatial_domains(
    domain_labels: np.ndarray, spatial_coords: np.ndarray, n_neighbors: int = 6, iterations: int = 2
) -> np.ndarray:
    """
    Markov Random Field / majority-vote smoothing to reduce salt-and-pepper noise
    and form anatomically contiguous tissue domains.
    """
    smoothed = domain_labels.copy()
    n_cells = len(domain_labels)
    tree = cKDTree(spatial_coords)
    k = min(n_neighbors + 1, n_cells)
    _, indices = tree.query(spatial_coords, k=k)

    for it in range(iterations):
        new_labels = smoothed.copy()
        for i in range(n_cells):
            nbr_labels = smoothed[indices[i]]
            # Majority vote including self
            vals, counts = np.unique(nbr_labels, return_counts=True)
            new_labels[i] = vals[np.argmax(counts)]
        smoothed = new_labels
    return smoothed


def run_spatial_clustering(
    adata,
    n_clusters: int = 8,
    spatial_weight: float = 0.35,
    n_spatial_neighbors: int = 6,
    n_expression_neighbors: int = 15,
    smooth_iterations: int = 2,
    spatial_key: str = "spatial",
    random_state: int = 42,
) -> Dict[str, Any]:
    """
    Perform end-to-end spatial-aware clustering on AnnData.
    Assigns domain labels to `adata.obs['spatial_domain']`.
    """
    logger.info(f"Running spatial clustering: n_clusters={n_clusters}, spatial_weight={spatial_weight}...")
    W_fused = build_fused_spatial_graph(
        adata,
        n_spatial_neighbors=n_spatial_neighbors,
        n_expression_neighbors=n_expression_neighbors,
        spatial_weight=spatial_weight,
        spatial_key=spatial_key,
    )

    # Spectral clustering on fused graph
    clustering = SpectralClustering(
        n_clusters=n_clusters, affinity="precomputed", assign_labels="kmeans", random_state=random_state
    )
    raw_labels = clustering.fit_predict(W_fused)

    # Spatial domain smoothing
    spatial_coords = adata.obsm[spatial_key]
    if smooth_iterations > 0:
        refined_labels = smooth_spatial_domains(
            raw_labels, spatial_coords, n_neighbors=n_spatial_neighbors, iterations=smooth_iterations
        )
    else:
        refined_labels = raw_labels

    # Store in adata
    domain_strings = np.array([f"Domain_{label}" for label in refined_labels])
    adata.obs["spatial_domain"] = pd.Categorical(domain_strings)
    adata.obs["spatial_domain_raw"] = pd.Categorical([f"Domain_{lbl}" for lbl in raw_labels])

    # Compute domain summary statistics
    unique_domains, counts = np.unique(domain_strings, return_counts=True)
    summary = {
        "n_clusters": int(n_clusters),
        "spatial_weight": float(spatial_weight),
        "domain_counts": {d: int(c) for d, c in zip(unique_domains, counts)},
        "smooth_iterations": int(smooth_iterations),
    }
    logger.info(f"Spatial clustering completed. Domain breakdown: {summary['domain_counts']}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Spatial-Aware Domain Clustering")
    parser.add_argument("--input", "-i", required=True, help="Input AnnData .h5ad file")
    parser.add_argument("--output", "-o", required=True, help="Output clustered .h5ad file")
    parser.add_argument("--n-clusters", "-k", type=int, default=8, help="Number of spatial domains")
    parser.add_argument(
        "--spatial-weight", type=float, default=0.35, help="Weight for spatial vs expression graph (0.0 to 1.0)"
    )
    parser.add_argument("--smooth-iter", type=int, default=2, help="MRF smoothing iterations")

    args = parser.parse_args()
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    run_spatial_clustering(
        adata, n_clusters=args.n_clusters, spatial_weight=args.spatial_weight, smooth_iterations=args.smooth_iter
    )
    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    adata.write_h5ad(args.output)
    logger.info(f"Clustered spatial dataset saved to {args.output}")


if __name__ == "__main__":
    main()
