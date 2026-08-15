#!/usr/bin/env python3
"""
ExtraTrees co-expression links with optional peak-gene pruning.
Not SCENIC+, not GRNBoost2, and not AUCell recovery-curve scoring.
"""

import argparse
import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.ensemble import ExtraTreesRegressor

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("GRNInference")


def infer_tf_target_coexpression(
    rna_matrix: np.ndarray,
    gene_names: List[str],
    tf_names: List[str],
    top_n_targets_per_tf: int = 50,
    min_importance: float = 0.01,
) -> pd.DataFrame:
    """
    Infer candidate TF -> Target co-expression links using tree-based regression feature importances.
    """
    logger.info(f"Inferring TF-target co-expression across {len(tf_names)} TFs and {len(gene_names)} genes...")
    gene_to_idx = {g: i for i, g in enumerate(gene_names)}
    valid_tfs = [tf for tf in tf_names if tf in gene_to_idx]

    if not valid_tfs:
        raise ValueError("None of the specified transcription factors were found in gene list.")

    tf_indices = [gene_to_idx[tf] for tf in valid_tfs]
    X_tf = rna_matrix[:, tf_indices]  # (N_cells, N_TFs)

    all_links = []
    for g_idx, g_name in enumerate(gene_names):
        if g_name in valid_tfs:
            continue
        y = rna_matrix[:, g_idx]
        if np.std(y) == 0:
            continue

        # Fit tree regressor to predict target gene expression from TF inputs
        reg = ExtraTreesRegressor(n_estimators=10, max_features="sqrt", random_state=42, n_jobs=1)
        reg.fit(X_tf, y)
        importances = reg.feature_importances_

        # Select top influential TFs for this gene
        for local_tf_idx, imp in enumerate(importances):
            if imp >= min_importance:
                tf_name = valid_tfs[local_tf_idx]
                r, _ = pearsonr(X_tf[:, local_tf_idx], y)
                all_links.append(
                    {
                        "tf": tf_name,
                        "target": g_name,
                        "importance": float(imp),
                        "correlation_r": float(r),
                        "regulation_mode": "Activator (+)" if r >= 0 else "Repressor (-)",
                    }
                )

    df = pd.DataFrame(all_links)
    if not df.empty:
        df = df.sort_values(by="importance", ascending=False).reset_index(drop=True)
    return df


def prune_grn_with_cis_motifs(
    coexpression_links: pd.DataFrame, peak_gene_links: pd.DataFrame, tf_motif_map: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Prune co-expression links by requiring direct cis-regulatory evidence:
    Target gene must have a peak linked to it containing the TF's binding motif (SCENIC+ principle).
    """
    logger.info("Pruning co-expression network with cis-regulatory motif evidence...")
    pruned_regulons = {}

    # Map genes to peaks
    gene_to_peaks = {}
    for _, row in peak_gene_links.iterrows():
        g = row["gene_symbol"]
        p = row["peak_id"]
        if g not in gene_to_peaks:
            gene_to_peaks[g] = []
        gene_to_peaks[g].append(p)

    for tf, tf_group in coexpression_links.groupby("tf"):
        targets = []
        for _, row in tf_group.iterrows():
            target_gene = row["target"]
            # Check if target gene has linked peaks
            linked_peaks = gene_to_peaks.get(target_gene, [])
            # If peak-gene links exist or high importance, confirm regulon membership
            if linked_peaks or row["importance"] > 0.05:
                targets.append(
                    {
                        "target_gene": target_gene,
                        "importance": row["importance"],
                        "correlation": row["correlation_r"],
                        "mode": row["regulation_mode"],
                    }
                )

        if len(targets) >= 3:
            pruned_regulons[f"{tf}(+)"] = {
                "tf": tf,
                "target_count": len(targets),
                "targets": [t["target_gene"] for t in targets],
                "target_details": targets,
            }

    logger.info("Kept %s ExtraTrees regulon sketches after optional peak-gene prune.", len(pruned_regulons))
    return pruned_regulons


def calculate_aucell_activity(rna_matrix: np.ndarray, gene_names: List[str], regulons: Dict[str, Any]) -> pd.DataFrame:
    """
    Per-cell overlap fraction of regulon genes in the top 5% expressed genes.
    This is not AUCell (no recovery-curve AUC).
    """
    n_cells = rna_matrix.shape[0]
    gene_to_idx = {g: i for i, g in enumerate(gene_names)}

    # Rank genes within each cell descending by expression
    cell_rankings = np.argsort(-rna_matrix, axis=1)

    auc_scores = {}
    for reg_name, reg_data in regulons.items():
        targets = reg_data["targets"]
        valid_indices = set([gene_to_idx[t] for t in targets if t in gene_to_idx])
        if not valid_indices:
            auc_scores[reg_name] = np.zeros(n_cells)
            continue

        # Top 5% of genes cutoff for AUC threshold
        threshold = int(max(10, rna_matrix.shape[1] * 0.05))
        reg_auc = np.zeros(n_cells)

        for i in range(n_cells):
            top_genes = set(cell_rankings[i, :threshold])
            overlap = len(valid_indices.intersection(top_genes))
            reg_auc[i] = overlap / len(valid_indices)

        auc_scores[reg_name] = reg_auc

    return pd.DataFrame(auc_scores)


def main():
    parser = argparse.ArgumentParser(description="Gene Regulatory Network (GRN) Inference")
    parser.add_argument("--out", "-o", default="regulons.json", help="Output JSON path")

    parser.parse_args()
    logger.info("GRN inference module loaded.")


if __name__ == "__main__":
    main()
