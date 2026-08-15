#!/usr/bin/env python3
"""
Grade-C niche clustering and ligand×receptor products on neighbor spots.

This is not CellChat and not COMMOT. Prefer squidpy gold chain for SVGs.
"""

import argparse
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import sparse
from scipy.spatial import cKDTree
from sklearn.cluster import KMeans

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("SpatialNicheAnalysis")

# Curated high-impact Ligand-Receptor pairs for immuno-oncology and tissue signaling
CURATED_LR_PAIRS = [
    ("CD274", "PDCD1", "Immune Checkpoint (PD-L1 / PD-1)"),
    ("CTLA4", "CD80", "Immune Checkpoint (CTLA-4 / CD80)"),
    ("CTLA4", "CD86", "Immune Checkpoint (CTLA-4 / CD86)"),
    ("CXCL12", "CXCR4", "Chemokine Recruitment"),
    ("CCL2", "CCR2", "Myeloid Infiltration"),
    ("VEGFA", "KDR", "Angiogenesis (VEGF-A / VEGFR2)"),
    ("TGFA", "EGFR", "Growth Factor Signaling"),
    ("EGF", "EGFR", "EGF Signaling"),
    ("TNF", "TNFRSF1A", "Inflammatory Signaling"),
    ("IL6", "IL6R", "IL-6 Pro-inflammatory"),
    ("TGFB1", "TGFBR1", "Fibrosis / Immunosuppression"),
    ("IFNG", "IFNGR1", "Interferon-gamma Cytotoxicity"),
]


def identify_spatial_niches(
    adata,
    proportions_key: str = "cell_type_proportions",
    spatial_key: str = "spatial",
    n_spatial_neighbors: int = 12,
    n_niches: int = 5,
    random_state: int = 42,
) -> Dict[str, Any]:
    """
    Identify cellular microenvironment niches by smoothing cell type proportions
    over local physical neighborhoods and clustering local composition profiles.
    """
    if proportions_key not in adata.obsm:
        raise ValueError(
            f"Cell type proportions key '{proportions_key}' not found in adata.obsm. Run deconvolution first."
        )

    proportions = adata.obsm[proportions_key]
    coords = adata.obsm.get(spatial_key)
    if coords is None:
        raise ValueError(f"Spatial coordinates key '{spatial_key}' not found in adata.obsm.")

    n_cells = adata.n_obs
    k = min(n_spatial_neighbors + 1, n_cells)
    tree = cKDTree(coords)
    dists, indices = tree.query(coords, k=k)

    # Compute neighborhood-averaged composition vectors
    niche_vectors = np.zeros_like(proportions)
    for i in range(n_cells):
        nbr_props = proportions[indices[i]]  # (k, n_types)
        # Distance-weighted neighborhood average
        w = np.exp(-dists[i] / (np.median(dists[i]) + 1e-6))
        w /= np.sum(w)
        niche_vectors[i] = np.sum(nbr_props * w[:, None], axis=0)

    # Cluster niche vectors
    kmeans = KMeans(n_clusters=n_niches, random_state=random_state, n_init=10)
    niche_labels = kmeans.fit_predict(niche_vectors)
    niche_names = [f"Niche_{lbl + 1}" for lbl in niche_labels]

    adata.obs["spatial_niche"] = pd.Categorical(niche_names)
    adata.obsm["niche_composition_vectors"] = niche_vectors

    # Determine signature cell type for each niche
    cell_types = adata.uns.get("cell_type_names", [f"Type_{j}" for j in range(proportions.shape[1])])
    niche_profiles = {}
    for niche_idx in range(n_niches):
        mask = niche_labels == niche_idx
        if np.sum(mask) > 0:
            mean_comp = np.mean(proportions[mask], axis=0)
            top_ct_idx = np.argsort(-mean_comp)[:2]
            top_desc = ", ".join([f"{cell_types[idx]} ({mean_comp[idx] * 100:.1f}%)" for idx in top_ct_idx])
            niche_profiles[f"Niche_{niche_idx + 1}"] = top_desc

    adata.uns["niche_profiles"] = niche_profiles
    logger.info(f"Identified {n_niches} spatial niches: {niche_profiles}")
    return niche_profiles


def compute_spatial_colocalization(adata, proportions_key: str = "cell_type_proportions") -> pd.DataFrame:
    """
    Compute pairwise spatial colocalization matrix (Pearson correlation)
    between all cell types across the tissue slice.
    """
    proportions = adata.obsm.get(proportions_key)
    if proportions is None:
        raise ValueError(f"Key '{proportions_key}' missing from adata.obsm.")

    cell_types = adata.uns.get("cell_type_names", [f"Type_{j}" for j in range(proportions.shape[1])])
    prop_df = pd.DataFrame(proportions, columns=cell_types)
    corr_matrix = prop_df.corr(method="pearson").fillna(0.0)

    adata.uns["spatial_colocalization"] = corr_matrix
    return corr_matrix


def evaluate_ligand_receptor_spatial_signaling(
    adata,
    spatial_key: str = "spatial",
    n_spatial_neighbors: int = 8,
    lr_database: Optional[List[Tuple[str, str, str]]] = None,
) -> pd.DataFrame:
    """
    Evaluate spatial ligand-receptor interaction potential:
      Score(L, R) = sum_{i} sum_{j in N(i)} [ E_i(L) * E_j(R) * exp(- d_{ij}^2 / 2*sigma^2) ]
    """
    if lr_database is None:
        lr_database = CURATED_LR_PAIRS

    coords = adata.obsm.get(spatial_key)
    if coords is None:
        raise ValueError(f"Spatial coordinates '{spatial_key}' not found.")

    X = adata.X.toarray() if sparse.issparse(adata.X) else adata.X
    genes = list(adata.var_names)
    gene_to_idx = {g.upper(): idx for idx, g in enumerate(genes)}

    n_cells = adata.n_obs
    k = min(n_spatial_neighbors + 1, n_cells)
    tree = cKDTree(coords)
    dists, indices = tree.query(coords, k=k)
    sigma = np.median(dists[:, 1:]) if dists.shape[1] > 1 else 1.0

    lr_results = []
    for ligand, receptor, pathway in lr_database:
        l_idx = gene_to_idx.get(ligand.upper())
        r_idx = gene_to_idx.get(receptor.upper())
        if l_idx is None or r_idx is None:
            continue

        l_expr = X[:, l_idx]
        r_expr = X[:, r_idx]

        # Compute spatial interaction score over neighbor pairs
        interaction_scores = np.zeros(n_cells, dtype=float)
        for i in range(n_cells):
            nbr_indices = indices[i, 1:]
            nbr_dists = dists[i, 1:]
            weights = np.exp(-(nbr_dists**2) / (2 * (sigma**2) + 1e-6))
            interaction_scores[i] = l_expr[i] * np.sum(r_expr[nbr_indices] * weights)

        tot_potential = float(np.sum(interaction_scores))
        mean_potential = float(np.mean(interaction_scores))
        active_spots = int(np.sum(interaction_scores > 0))

        lr_results.append(
            {
                "ligand": ligand,
                "receptor": receptor,
                "pathway": pathway,
                "total_interaction_score": tot_potential,
                "mean_spot_score": mean_potential,
                "active_spots": active_spots,
                "percent_active_spots": round((active_spots / n_cells) * 100.0, 2),
            }
        )

    results_df = pd.DataFrame(lr_results)
    if not results_df.empty:
        results_df = results_df.sort_values(by="total_interaction_score", ascending=False)
    adata.uns["spatial_lr_interactions"] = results_df
    logger.info(f"Evaluated {len(lr_results)} spatial ligand-receptor pairs.")
    return results_df


def main():
    parser = argparse.ArgumentParser(description="Spatial Microenvironment & Niche Analysis")
    parser.add_argument("--input", "-i", required=True, help="Deconvolved spatial AnnData .h5ad file")
    parser.add_argument("--output", "-o", required=True, help="Output AnnData with niche annotations")
    parser.add_argument("--n-niches", type=int, default=5, help="Number of spatial microenvironment niches")
    parser.add_argument("--n-neighbors", type=int, default=12, help="Spatial neighborhood size for niche profiling")

    args = parser.parse_args()
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    identify_spatial_niches(adata, n_niches=args.n_niches, n_spatial_neighbors=args.n_neighbors)
    compute_spatial_colocalization(adata)
    evaluate_ligand_receptor_spatial_signaling(adata)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)) or ".", exist_ok=True)
    adata.write_h5ad(args.output)
    logger.info(f"Saved niche-annotated dataset to {args.output}")


if __name__ == "__main__":
    main()
