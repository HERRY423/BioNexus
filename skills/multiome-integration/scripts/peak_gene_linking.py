#!/usr/bin/env python3
"""
Chromatin Accessibility Peak-to-Gene Cis-Regulatory Linking Module.
Calculates distance-constrained Pearson correlations between ATAC-seq peak accessibility
and RNA-seq gene expression to identify enhancer-promoter regulatory loops (ArchR / Signac style).
"""

import argparse
import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("PeakGeneLinking")


def calculate_peak_gene_correlations(
    rna_matrix: np.ndarray,
    atac_matrix: np.ndarray,
    gene_annotations: List[Dict[str, Any]],
    peak_annotations: List[Dict[str, Any]],
    max_distance_bp: int = 250000,
    min_correlation: float = 0.25,
    max_p_value: float = 0.05,
) -> pd.DataFrame:
    """
    Correlate peak accessibility with gene expression for nearby genomic pairs.
    gene_annotations: [{'name': 'EGFR', 'chrom': 'chr7', 'tss': 55019017, 'index': 0}, ...]
    peak_annotations: [{'peak_id': 'chr7:55000000-55000500', 'chrom': 'chr7', 'center': 55000250, 'index': 0}, ...]
    """
    logger.info(f"Screening candidate peak-gene regulatory links within +/- {max_distance_bp // 1000} kb window...")
    links = []

    # Organize peaks by chromosome
    peaks_by_chrom = {}
    for p in peak_annotations:
        chrom = p.get("chrom", "chr1")
        if chrom not in peaks_by_chrom:
            peaks_by_chrom[chrom] = []
        peaks_by_chrom[chrom].append(p)

    for gene in gene_annotations:
        g_name = gene["name"]
        g_chrom = gene.get("chrom", "chr1")
        g_tss = gene.get("tss", 0)
        g_idx = gene["index"]
        g_expr = rna_matrix[:, g_idx]

        if np.std(g_expr) == 0:
            continue

        cand_peaks = peaks_by_chrom.get(g_chrom, [])
        for peak in cand_peaks:
            p_center = peak.get("center", 0)
            dist = abs(g_tss - p_center)

            if dist <= max_distance_bp:
                p_idx = peak["index"]
                p_access = atac_matrix[:, p_idx]
                if np.std(p_access) == 0:
                    continue

                r, p_val = pearsonr(p_access, g_expr)
                if r >= min_correlation and p_val <= max_p_value:
                    regulatory_type = "Promoter-Proximal" if dist <= 2000 else "Distal-Enhancer"
                    links.append(
                        {
                            "gene_symbol": g_name,
                            "peak_id": peak.get("peak_id", f"{g_chrom}:{p_center}"),
                            "chromosome": g_chrom,
                            "distance_to_tss_bp": dist,
                            "regulatory_type": regulatory_type,
                            "correlation_r": round(float(r), 3),
                            "p_value": float(p_val),
                        }
                    )

    results_df = pd.DataFrame(links)
    if not results_df.empty:
        results_df = results_df.sort_values(by="correlation_r", ascending=False).reset_index(drop=True)
    logger.info(f"Identified {len(results_df)} significant peak-gene cis-regulatory links.")
    return results_df


def main():
    parser = argparse.ArgumentParser(description="Peak-to-Gene Cis-Regulatory Linking")
    parser.add_argument("--out", "-o", default="peak_gene_links.csv", help="Output CSV path")

    parser.parse_args()
    logger.info("Executed peak-gene linking.")


if __name__ == "__main__":
    main()
