#!/usr/bin/env python3
"""
Transcription Factor Chromatin Footprinting & Tn5 Bias Correction Module.
Measures high-resolution Tn5 transposase cleavage protection profiles around TF motif centers
to quantify in vivo transcription factor chromatin binding occupancy.
"""

import argparse
import logging
from typing import Any, Dict

import numpy as np

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("TFFootprinting")


def compute_tf_footprint_profile(
    cut_frequencies: np.ndarray, window_size: int = 100, core_flank: int = 10
) -> Dict[str, Any]:
    """
    Calculate footprint depth and chromatin protection index from aggregation profile.
    cut_frequencies: 1D array of length (2 * window_size + 1), centered at position 0.
    """
    n_pts = len(cut_frequencies)
    mid = n_pts // 2

    # Motif core region [-core_flank, +core_flank]
    core_cuts = cut_frequencies[mid - core_flank : mid + core_flank + 1]
    mean_core = float(np.mean(core_cuts))

    # Flanking shoulder regions [-window_size, -30] and [+30, +window_size]
    left_shoulder = cut_frequencies[: mid - 30]
    right_shoulder = cut_frequencies[mid + 30 :]
    flank_cuts = np.concatenate([left_shoulder, right_shoulder])
    mean_flank = float(np.mean(flank_cuts)) if len(flank_cuts) > 0 else (mean_core + 1e-6)

    # Footprint Depth / Chromatin Protection Index (CPI)
    # 0.0 = No protection (unoccupied motif), > 0.40 = Strong TF binding protection
    protection_score = max(0.0, 1.0 - (mean_core / (mean_flank + 1e-6)))

    return {
        "mean_core_cuts": round(mean_core, 2),
        "mean_flank_cuts": round(mean_flank, 2),
        "chromatin_protection_index": round(float(protection_score), 3),
        "binding_status": "Active Chromatin Binding (Occupied Footprint)"
        if protection_score >= 0.35
        else "Unoccupied Motif / Transient Binding",
    }


def main():
    parser = argparse.ArgumentParser(description="TF Footprinting Analyzer")
    parser.parse_args()
    logger.info("TF Footprinting analyzer loaded.")


if __name__ == "__main__":
    main()
