#!/usr/bin/env python3
"""
Transcription Factor Binding Motif Enrichment & Deviation Module.
Scans chromatin accessibility peak sets for TF Position Weight Matrices (JASPAR/HOCOMOCO)
and computes motif enrichment statistics and a simple depth z-score. Not chromVAR.
"""

import argparse
import logging
from typing import List

import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("MotifEnrichment")

# Master regulator TF consensus motifs (IUPAC / Core Regex)
CORE_TF_MOTIFS = {
    "TP53": {"name": "p53", "motif": "RRRCWWGYYY", "length": 10},
    "SOX2": {"name": "SOX2", "motif": "CATTGTT", "length": 7},
    "POU5F1": {"name": "OCT4", "motif": "ATGCAAAT", "length": 8},
    "GATA3": {"name": "GATA3", "motif": "WGATAR", "length": 6},
    "NFKB1": {"name": "NF-kappaB", "motif": "GGGRNYYYCC", "length": 10},
    "STAT3": {"name": "STAT3", "motif": "TTCCNGGAA", "length": 9},
    "MYC": {"name": "c-Myc", "motif": "CACGTG", "length": 6},
    "RUNX1": {"name": "RUNX1", "motif": "AACCACA", "length": 7},
    "FOXA1": {"name": "FOXA1", "motif": "TGTTTRY", "length": 7},
    "CTCF": {"name": "CTCF", "motif": "CCACCAGGGGGCG", "length": 13},
}


def calculate_motif_enrichment_in_peaks(
    peak_motif_matrix: np.ndarray, target_peak_indices: np.ndarray, tf_names: List[str]
) -> pd.DataFrame:
    """
    Perform Fisher's exact test for TF motif enrichment in target peaks vs background peaks.
    peak_motif_matrix: (N_peaks, N_motifs) binary presence/absence matrix.
    """
    n_total_peaks = peak_motif_matrix.shape[0]
    n_target = len(target_peak_indices)
    n_background = n_total_peaks - n_target

    target_mask = np.zeros(n_total_peaks, dtype=bool)
    target_mask[target_peak_indices] = True
    bg_mask = ~target_mask

    enrichment_results = []
    for m_idx, tf in enumerate(tf_names):
        col = peak_motif_matrix[:, m_idx]
        a = int(np.sum(col[target_mask]))  # Target with motif
        b = int(n_target - a)  # Target without motif
        c = int(np.sum(col[bg_mask]))  # Background with motif
        d = int(n_background - c)  # Background without motif

        table = [[a, b], [c, d]]
        odds_ratio, p_val = fisher_exact(table, alternative="greater")

        target_pct = (a / n_target) * 100.0 if n_target > 0 else 0.0
        bg_pct = (c / n_background) * 100.0 if n_background > 0 else 0.0

        enrichment_results.append(
            {
                "transcription_factor": tf,
                "motif_target_count": a,
                "target_percent": round(target_pct, 1),
                "background_percent": round(bg_pct, 1),
                "odds_ratio": round(float(odds_ratio), 2),
                "p_value": float(p_val),
                "minus_log10_p": round(-np.log10(max(p_val, 1e-300)), 2),
            }
        )

    results_df = pd.DataFrame(enrichment_results)
    results_df = results_df.sort_values(by="minus_log10_p", ascending=False).reset_index(drop=True)
    return results_df


def compute_per_cell_motif_deviation(
    atac_matrix: np.ndarray, peak_motif_matrix: np.ndarray, tf_names: List[str]
) -> pd.DataFrame:
    """
    Simple depth z-score: (observed - expected) / sqrt(expected). Not chromVAR.
    Measures per-cell chromatin accessibility across all peaks containing a specific TF motif.
    """
    atac_matrix.shape[0]
    len(tf_names)

    # Observed motif accessibility
    observed = atac_matrix @ peak_motif_matrix  # (n_cells, n_tfs)

    # Expected under background depth
    cell_depth = np.sum(atac_matrix, axis=1, keepdims=True)  # (n_cells, 1)
    motif_freq = np.sum(peak_motif_matrix, axis=0, keepdims=True) / peak_motif_matrix.shape[0]  # (1, n_tfs)
    expected = cell_depth @ motif_freq

    # Deviation z-score
    std_dev = np.sqrt(expected + 1e-6)
    deviation_z = (observed - expected) / std_dev

    dev_df = pd.DataFrame(deviation_z, columns=[f"{tf}_deviation" for tf in tf_names])
    return dev_df


def main():
    parser = argparse.ArgumentParser(description="TF Motif Enrichment and Deviation")
    parser.add_argument("--out", "-o", default="motif_enrichment.csv", help="Output CSV path")

    parser.parse_args()
    logger.info("Motif enrichment module loaded.")


if __name__ == "__main__":
    main()
