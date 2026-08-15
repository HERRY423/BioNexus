#!/usr/bin/env python3
"""
Target Tractability & Pocket Druggability Scoring Module.
Integrates 3D pocket geometry, AlphaFold confidence in active site residues,
chemogenomic ChEMBL evidence, and modality feasibility (Small Molecule, PROTAC, Biologics).
"""

import argparse
import logging
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("DruggabilityScorer")


def evaluate_target_tractability(
    gene_symbol: str,
    pockets: List[Dict[str, Any]],
    mean_plddt: float = 85.0,
    has_chembl_ligands: bool = True,
    open_targets_score: float = 0.65,
    is_extracellular: bool = False,
) -> Dict[str, Any]:
    """
    Compute multi-modal target tractability & druggability assessment.
    Returns composite score and modality-specific recommendations.
    """
    top_pocket = pockets[0] if pockets else None
    pocket_druggability = top_pocket.get("druggability_score", 0.0) if top_pocket else 0.0
    pocket_volume = top_pocket.get("volume_angstrom3", 0.0) if top_pocket else 0.0

    # 1. Structural pocket score (0.0 to 1.0)
    struct_score = 0.7 * pocket_druggability + 0.3 * (min(100.0, mean_plddt) / 100.0)

    # 2. Chemogenomic precedent score
    chem_score = 0.9 if has_chembl_ligands else 0.3

    # 3. Genetic association score
    gen_score = min(1.0, max(0.0, open_targets_score))

    # Composite Tractability Score (Weighted: 40% Structure, 30% Chemistry, 30% Biology)
    composite_score = 0.40 * struct_score + 0.30 * chem_score + 0.30 * gen_score

    # Modality Feasibility Assessment
    modalities = []
    if pocket_druggability >= 0.50 and pocket_volume >= 250.0:
        modalities.append(
            {
                "modality": "Small Molecule (SMOL)",
                "feasibility": "High",
                "rationale": f"High-confidence druggable pocket detected (Volume: {pocket_volume:.1f} A^3, Score: {pocket_druggability:.2f}).",
            }
        )
    elif pocket_druggability >= 0.35:
        modalities.append(
            {
                "modality": "Small Molecule (SMOL)",
                "feasibility": "Moderate",
                "rationale": "Shallow or moderately enclosed pocket; may require covalent or fragment-based screening.",
            }
        )
    else:
        modalities.append(
            {
                "modality": "Small Molecule (SMOL)",
                "feasibility": "Low / Undruggable Pocket",
                "rationale": "Lack of well-defined concave binding cavity.",
            }
        )

    # PROTAC / Targeted Protein Degradation
    if struct_score >= 0.50:
        modalities.append(
            {
                "modality": "PROTAC / Molecular Glue",
                "feasibility": "High",
                "rationale": "Accessible surface binder pocket suitable for bifunctional degrader conjugation.",
            }
        )

    # Biologics / Antibodies
    if is_extracellular:
        modalities.append(
            {
                "modality": "Monoclonal Antibody / ADC",
                "feasibility": "High",
                "rationale": "Target possesses extracellular topological domain accessible to therapeutic antibodies.",
            }
        )

    # Overall Tractability Tier
    if composite_score >= 0.75:
        tier = "Tier 1: Highly Tractable & Validated Target"
    elif composite_score >= 0.55:
        tier = "Tier 2: Tractable Target with Moderate Feasibility"
    else:
        tier = "Tier 3: Challenging / High-Risk Target"

    return {
        "gene_symbol": gene_symbol,
        "composite_tractability_score": round(float(composite_score), 3),
        "tractability_tier": tier,
        "structural_score": round(float(struct_score), 3),
        "chemogenomic_score": round(float(chem_score), 3),
        "genetic_score": round(float(gen_score), 3),
        "top_pocket_volume_a3": pocket_volume,
        "top_pocket_druggability": pocket_druggability,
        "modality_recommendations": modalities,
    }


def main():
    parser = argparse.ArgumentParser(description="Target Tractability Scorer")
    parser.add_argument("--gene", "-g", required=True, help="Target gene symbol (e.g. 'EGFR')")
    parser.add_argument("--plddt", type=float, default=85.0, help="Mean AlphaFold pLDDT score")

    args = parser.parse_args()
    sample_pocket = [{"pocket_id": 1, "druggability_score": 0.78, "volume_angstrom3": 450.0}]
    res = evaluate_target_tractability(args.gene, sample_pocket, mean_plddt=args.plddt)
    import json

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
