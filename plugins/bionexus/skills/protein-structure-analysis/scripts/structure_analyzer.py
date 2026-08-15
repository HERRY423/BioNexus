#!/usr/bin/env python3
"""
Protein Structure Biophysical & Quality Analyzer.
Computes per-residue AlphaFold pLDDT confidence tiers, contact maps, radius of gyration,
secondary structure element estimation, and structural domain boundaries.
"""

import argparse
import logging
from typing import Any, Dict, Tuple

import numpy as np

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("StructureAnalyzer")


def analyze_plddt_confidence(plddt_scores: np.ndarray) -> Dict[str, Any]:
    """
    Stratify AlphaFold per-residue pLDDT scores into standard confidence tiers.
    pLDDT > 90: Very High (side-chain accuracy)
    70-90: Confident (backbone fold reliable)
    50-70: Low (flexible loop)
    < 50: Very Low / Intrinsically Disordered (IDR)
    """
    n_res = len(plddt_scores)
    if n_res == 0:
        return {"mean_plddt": 0.0, "status": "Empty"}

    very_high = np.sum(plddt_scores >= 90.0)
    confident = np.sum((plddt_scores >= 70.0) & (plddt_scores < 90.0))
    low = np.sum((plddt_scores >= 50.0) & (plddt_scores < 70.0))
    very_low = np.sum(plddt_scores < 50.0)

    # Detect structured core domain segments (stretches of >= 15 residues with pLDDT >= 70)
    is_structured = plddt_scores >= 70.0
    domains = []
    in_domain = False
    start_idx = 0
    for i, st in enumerate(is_structured):
        if st and not in_domain:
            in_domain = True
            start_idx = i
        elif not st and in_domain:
            in_domain = False
            if (i - start_idx) >= 15:
                domains.append({"start_res": start_idx + 1, "end_res": i, "length": i - start_idx})
    if in_domain and (n_res - start_idx) >= 15:
        domains.append({"start_res": start_idx + 1, "end_res": n_res, "length": n_res - start_idx})

    return {
        "mean_plddt": round(float(np.mean(plddt_scores)), 2),
        "median_plddt": round(float(np.median(plddt_scores)), 2),
        "percent_very_high": round((very_high / n_res) * 100.0, 1),
        "percent_confident": round((confident / n_res) * 100.0, 1),
        "percent_low": round((low / n_res) * 100.0, 1),
        "percent_disordered_very_low": round((very_low / n_res) * 100.0, 1),
        "overall_structural_quality": "High-Confidence Fold"
        if (very_high + confident) / n_res > 0.70
        else "Partially Disordered / Flexible",
        "structured_core_domains": domains,
    }


def compute_contact_map(
    ca_coords: np.ndarray, contact_threshold_angstrom: float = 8.0
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Compute pairwise CA distance matrix and binary contact map.
    Returns (distance_matrix, binary_contact_map).
    """
    n_res = len(ca_coords)
    if n_res == 0:
        return np.zeros((0, 0)), np.zeros((0, 0), dtype=bool)

    diff = ca_coords[:, np.newaxis, :] - ca_coords[np.newaxis, :, :]  # (N, N, 3)
    dist_matrix = np.sqrt(np.sum(diff**2, axis=-1))  # (N, N)
    contact_map = dist_matrix <= contact_threshold_angstrom
    return dist_matrix, contact_map


def compute_radius_of_gyration(ca_coords: np.ndarray) -> float:
    """Compute Radius of Gyration (Rg) measuring overall structural compactness."""
    if len(ca_coords) == 0:
        return 0.0
    center_of_mass = np.mean(ca_coords, axis=0)
    rg_sq = np.mean(np.sum((ca_coords - center_of_mass) ** 2, axis=1))
    return float(np.sqrt(rg_sq))


def estimate_secondary_structure(ca_coords: np.ndarray) -> Dict[str, Any]:
    """
    Estimate secondary structure fractions from CA distance geometry:
    - Alpha-helix: distance(i, i+3) in [4.8, 5.8] A and distance(i, i+4) in [5.8, 6.8] A
    - Beta-strand: distance(i, i+2) in [6.4, 7.2] A
    """
    n = len(ca_coords)
    if n < 5:
        return {"helix_fraction": 0.0, "strand_fraction": 0.0, "coil_fraction": 1.0}

    helix_count = 0
    strand_count = 0

    for i in range(n - 4):
        d_i3 = np.linalg.norm(ca_coords[i] - ca_coords[i + 3])
        d_i4 = np.linalg.norm(ca_coords[i] - ca_coords[i + 4])
        d_i2 = np.linalg.norm(ca_coords[i] - ca_coords[i + 2])

        if 4.5 <= d_i3 <= 6.0 and 5.5 <= d_i4 <= 7.0:
            helix_count += 1
        elif 6.2 <= d_i2 <= 7.4:
            strand_count += 1

    helix_frac = helix_count / n
    strand_frac = strand_count / n
    coil_frac = max(0.0, 1.0 - (helix_frac + strand_frac))

    return {
        "helix_percentage": round(helix_frac * 100.0, 1),
        "strand_percentage": round(strand_frac * 100.0, 1),
        "coil_percentage": round(coil_frac * 100.0, 1),
        "structural_class": "All-Alpha"
        if helix_frac > 0.45 and strand_frac < 0.1
        else ("All-Beta" if strand_frac > 0.35 and helix_frac < 0.1 else "Alpha/Beta Mixed"),
    }


def analyze_protein_structure_full(structure_data: Dict[str, Any]) -> Dict[str, Any]:
    """Perform full biophysical structural audit on parsed PDB/AlphaFold data."""
    ca_coords = structure_data.get("ca_coordinates", np.zeros((0, 3)))
    plddt = structure_data.get("b_factors_or_plddt", np.zeros(0))

    confidence_analysis = analyze_plddt_confidence(plddt)
    _, contact_map = compute_contact_map(ca_coords)
    rg = compute_radius_of_gyration(ca_coords)
    sec_struct = estimate_secondary_structure(ca_coords)

    total_contacts = int(np.sum(contact_map) - len(ca_coords)) // 2 if len(ca_coords) > 0 else 0
    contact_order = (total_contacts / len(ca_coords)) if len(ca_coords) > 0 else 0.0

    return {
        "n_residues": len(ca_coords),
        "radius_of_gyration_angstrom": round(rg, 2),
        "total_contacts": total_contacts,
        "contact_density_per_residue": round(contact_order, 2),
        "confidence_metrics": confidence_analysis,
        "secondary_structure": sec_struct,
    }


def main():
    parser = argparse.ArgumentParser(description="Protein Structure Biophysical Analyzer")
    parser.add_argument("--pdb-file", "-f", required=True, help="Input PDB file path")

    args = parser.parse_args()
    from structure_fetcher import parse_pdb_text

    with open(args.pdb_file, "r", encoding="utf-8") as f:
        content = f.read()
    parsed = parse_pdb_text(content)
    analysis = analyze_protein_structure_full(parsed)
    import json

    print(json.dumps(analysis, indent=2))


if __name__ == "__main__":
    main()
