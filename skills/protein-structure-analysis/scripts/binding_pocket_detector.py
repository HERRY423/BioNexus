#!/usr/bin/env python3
"""
CA-only grid cavity heuristic. Not fpocket alpha-spheres and not P2Rank.
Identifies concave, solvent-accessible ligand-binding pockets on protein surfaces,
computes pocket volumes, bounding box centers, and estimates druggability scores.
"""

import argparse
import logging
from typing import Any, Dict, List, Optional

import numpy as np
from scipy.spatial import cKDTree

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("BindingPocketDetector")

HYDROPHOBIC_AAS = {"A", "V", "I", "L", "M", "F", "Y", "W", "P"}


def detect_binding_pockets_grid(
    ca_coords: np.ndarray,
    sequence: Optional[str] = None,
    grid_spacing: float = 1.5,
    probe_radius: float = 1.4,
    min_pocket_points: int = 15,
) -> List[Dict[str, Any]]:
    """
    Detect concave surface pockets using 3D spatial grid casting and spatial clustering.
    Returns ranked list of binding pockets with volume, center, lining residues, and druggability.
    """
    n_atoms = len(ca_coords)
    if n_atoms < 10:
        return []

    # 1. Bounding box definition
    min_c = np.min(ca_coords, axis=0) - 4.0
    max_c = np.max(ca_coords, axis=0) + 4.0

    x_range = np.arange(min_c[0], max_c[0], grid_spacing)
    y_range = np.arange(min_c[1], max_c[1], grid_spacing)
    z_range = np.arange(min_c[2], max_c[2], grid_spacing)

    # Generate 3D grid points
    grid_x, grid_y, grid_z = np.meshgrid(x_range, y_range, z_range, indexing="ij")
    grid_points = np.vstack([grid_x.ravel(), grid_y.ravel(), grid_z.ravel()]).T

    # 2. Distance filtering using KDTree
    tree_atoms = cKDTree(ca_coords)
    dists, nearest_atom_idx = tree_atoms.query(grid_points, k=1)

    # Cavity points: between 2.2 A (outside VDW) and 6.0 A (near protein surface)
    cavity_mask = (dists >= (probe_radius + 1.0)) & (dists <= 6.0)
    cavity_points = grid_points[cavity_mask]

    if len(cavity_points) < min_pocket_points:
        return []

    # 3. Simple spatial clustering of cavity points
    tree_cavity = cKDTree(cavity_points)
    visited = np.zeros(len(cavity_points), dtype=bool)
    clusters = []

    for i in range(len(cavity_points)):
        if visited[i]:
            continue
        # BFS / region growing within 2.5 A
        cluster_pts = []
        queue = [i]
        visited[i] = True

        while queue:
            curr = queue.pop(0)
            cluster_pts.append(curr)
            nbrs = tree_cavity.query_ball_point(cavity_points[curr], r=grid_spacing * 1.8)
            for nb in nbrs:
                if not visited[nb]:
                    visited[nb] = True
                    queue.append(nb)

        if len(cluster_pts) >= min_pocket_points:
            clusters.append(cavity_points[cluster_pts])

    # 4. Calculate pocket descriptors and druggability
    pockets = []
    for p_idx, pts in enumerate(clusters):
        center = np.mean(pts, axis=0)
        # Approximate volume: number of points * grid_spacing^3
        volume_a3 = len(pts) * (grid_spacing**3)

        # Find lining residues (CA within 6.5 A of pocket center or cavity points)
        lining_idx = tree_atoms.query_ball_point(center, r=8.0)
        hydrophobic_count = 0
        if sequence and len(sequence) == n_atoms:
            lining_aas = [sequence[idx] for idx in lining_idx if idx < len(sequence)]
            "".join(lining_aas)
            hydrophobic_count = sum(1 for aa in lining_aas if aa in HYDROPHOBIC_AAS)
            hydro_ratio = (hydrophobic_count / len(lining_aas)) if lining_aas else 0.0
        else:
            hydro_ratio = 0.5  # Neutral default

        # Druggability score (0.0 to 1.0)
        # Optimal druggable pocket volume ~ 300 to 1200 A^3 with good hydrophobicity
        vol_score = (
            min(1.0, volume_a3 / 600.0) if volume_a3 <= 1000.0 else max(0.5, 1.0 - (volume_a3 - 1000.0) / 2000.0)
        )
        druggability = 0.6 * vol_score + 0.4 * hydro_ratio

        pockets.append(
            {
                "pocket_id": p_idx + 1,
                "center_coordinates": [round(float(c), 2) for c in center],
                "volume_angstrom3": round(float(volume_a3), 1),
                "n_grid_points": len(pts),
                "n_lining_residues": len(lining_idx),
                "lining_residue_indices": [idx + 1 for idx in sorted(lining_idx)],
                "hydrophobicity_ratio": round(float(hydro_ratio), 2),
                "druggability_score": round(float(druggability), 3),
                "is_druggable": bool(druggability >= 0.45 and volume_a3 >= 150.0),
            }
        )

    # Sort descending by druggability score
    pockets.sort(key=lambda x: x["druggability_score"], reverse=True)
    logger.info(
        f"Detected {len(pockets)} candidate binding pockets. Top volume: {pockets[0]['volume_angstrom3'] if pockets else 0} A^3"
    )
    return pockets


def main():
    parser = argparse.ArgumentParser(description="Binding Pocket & Cavity Detector")
    parser.add_argument("--pdb", "-p", required=True, help="Input PDB file path")
    parser.add_argument("--spacing", "-s", type=float, default=1.5, help="Grid spacing in Angstroms")

    args = parser.parse_args()
    from structure_fetcher import parse_pdb_text

    with open(args.pdb, "r", encoding="utf-8") as f:
        content = f.read()
    parsed = parse_pdb_text(content)
    pockets = detect_binding_pockets_grid(
        parsed["ca_coordinates"], sequence=parsed["sequence"], grid_spacing=args.spacing
    )
    import json

    print(json.dumps(pockets, indent=2))


if __name__ == "__main__":
    main()
