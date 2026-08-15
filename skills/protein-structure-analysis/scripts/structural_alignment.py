#!/usr/bin/env python3
"""
Structural Superposition & TM-Score Alignment Engine (Kabsch / TM-align style).
Performs optimal 3D rigid-body rotation and translation via Kabsch SVD algorithm
and computes sequence length-independent TM-score fold similarity.
"""

import argparse
import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("StructuralAlignment")


def kabsch_superposition(coords_p: np.ndarray, coords_q: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Perform optimal rigid body superposition of P onto Q using Kabsch algorithm (SVD).
    Returns (P_rotated_translated, Rotation_matrix, RMSD).
    """
    if coords_p.shape != coords_q.shape or len(coords_p) == 0:
        raise ValueError(f"Coordinate dimensions must match: {coords_p.shape} vs {coords_q.shape}")

    len(coords_p)

    # 1. Center coordinates at origin
    centroid_p = np.mean(coords_p, axis=0)
    centroid_q = np.mean(coords_q, axis=0)

    p_centered = coords_p - centroid_p
    q_centered = coords_q - centroid_q

    # 2. Covariance matrix H = P^T * Q
    H = np.dot(p_centered.T, q_centered)

    # 3. SVD
    U, S, Vt = np.linalg.svd(H)
    V = Vt.T

    # 4. Handle reflection / right-handedness constraint
    d = np.linalg.det(np.dot(V, U.T))
    flip = np.array([[1, 0, 0], [0, 1, 0], [0, 0, np.sign(d)]])
    R = np.dot(np.dot(V, flip), U.T)

    # 5. Rotate and translate P onto Q
    p_rotated = np.dot(p_centered, R.T) + centroid_q

    # 6. Calculate RMSD
    rmsd = float(np.sqrt(np.mean(np.sum((p_rotated - coords_q) ** 2, axis=1))))
    return p_rotated, R, rmsd


def compute_tm_score(p_superposed: np.ndarray, q_target: np.ndarray, target_length: Optional[int] = None) -> float:
    """
    Calculate TM-score fold similarity:
      TM = (1 / L_target) * sum( 1 / (1 + (d_i / d0)^2) )
      where d0 = 1.24 * (L_target - 15)^(1/3) - 1.8 for L > 21
    TM > 0.5 indicates same structural fold.
    """
    n_aligned = len(p_superposed)
    L = target_length or n_aligned
    if L <= 21:
        d0 = 0.5
    else:
        d0 = max(0.5, 1.24 * ((L - 15.0) ** (1.0 / 3.0)) - 1.8)

    distances = np.linalg.norm(p_superposed - q_target, axis=1)
    tm_terms = 1.0 / (1.0 + (distances / d0) ** 2)
    tm_score = float(np.sum(tm_terms) / L)
    return tm_score


def align_two_structures(
    coords_mobile: np.ndarray, coords_target: np.ndarray, target_name: str = "Target", mobile_name: str = "Mobile"
) -> Dict[str, Any]:
    """Align mobile structure onto target structure and evaluate fold conservation."""
    # Truncate to common length for CA superposition
    n_common = min(len(coords_mobile), len(coords_target))
    p_sub = coords_mobile[:n_common]
    q_sub = coords_target[:n_common]

    p_rot, R, rmsd = kabsch_superposition(p_sub, q_sub)
    tm = compute_tm_score(p_rot, q_sub, target_length=len(coords_target))

    if tm >= 0.70:
        fold_similarity = "High Structural Homology (Same Family / Fold)"
    elif tm >= 0.50:
        fold_similarity = "Probable Same Global Fold (TM > 0.5)"
    else:
        fold_similarity = "Different Structural Topology (Random Structural Alignment)"

    return {
        "mobile_structure": mobile_name,
        "target_structure": target_name,
        "aligned_residues": n_common,
        "rmsd_angstrom": round(rmsd, 3),
        "tm_score": round(tm, 4),
        "fold_classification": fold_similarity,
    }


def main():
    parser = argparse.ArgumentParser(description="Structural Superposition & TM-Score Alignment")
    parser.add_argument("--mobile", "-m", required=True, help="Mobile PDB file")
    parser.add_argument("--target", "-t", required=True, help="Target reference PDB file")

    args = parser.parse_args()
    from structure_fetcher import parse_pdb_text

    with open(args.mobile, "r", encoding="utf-8") as f:
        mob_parsed = parse_pdb_text(f.read())
    with open(args.target, "r", encoding="utf-8") as f:
        tgt_parsed = parse_pdb_text(f.read())

    res = align_two_structures(
        mob_parsed["ca_coordinates"], tgt_parsed["ca_coordinates"], mobile_name=args.mobile, target_name=args.target
    )
    import json

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
