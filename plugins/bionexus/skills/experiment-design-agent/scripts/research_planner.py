#!/usr/bin/env python3
"""
Automated Phased Preclinical Research Study Planner.
Generates comprehensive 5-phase end-to-end scientific study designs integrating
Target Discovery, Single-Cell Genomics, Spatial Microenvironments, Multiome GRNs, and Clinical Genetics.
"""

import argparse
import logging
from typing import Any, Dict

import yaml

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("ResearchPlanner")


def create_preclinical_research_plan(
    target_gene: str,
    disease_indication: str,
    modality: str = "Small Molecule",
    clinical_objective: str = "Overcome therapeutic resistance and validate target tractability",
) -> Dict[str, Any]:
    """
    Generate complete 5-phase preclinical investigation master plan.
    """
    logger.info(f"Generating research plan for target '{target_gene}' in '{disease_indication}'...")

    phases = [
        {
            "phase_number": 1,
            "phase_title": "Target Discovery, Structural Druggability & Tractability",
            "objective": f"Validate {target_gene} genetic association and identify high-affinity 3D binding pockets.",
            "computational_methods": [
                "Open Targets Platform query for genetic disease score and tractability",
                "ChEMBL search for bioactivity assays (IC50 / Ki) and known chemical matter",
                "AlphaFold DB structure fetch and per-residue pLDDT confidence profiling",
                "Grid-based 3D binding pocket detection and druggability scoring",
            ],
            "milestone_go_no_go": "Target possesses genetic association score > 0.40 and a druggable pocket (Volume > 300 A^3, Score > 0.50).",
        },
        {
            "phase_number": 2,
            "phase_title": "Single-Cell Genomics & Cellular Heterogeneity",
            "objective": f"Map {target_gene} cell-type specific expression and downstream activation programs.",
            "computational_methods": [
                "scRNA-seq QC with MAD thresholding, Scrublet doublet simulation, and SoupX ambient RNA subtraction",
                "scVI / scANVI deep generative modeling for multi-batch integration",
                "Bayesian differential expression to identify downstream target gene signatures",
            ],
            "milestone_go_no_go": f"Specific enrichment of {target_gene} in target disease cell populations vs non-malignant controls.",
        },
        {
            "phase_number": 3,
            "phase_title": "Spatial Transcriptomics & Microenvironment Niche Mapping",
            "objective": f"Locate {target_gene} within tissue histological domains and quantify cell-cell signaling.",
            "computational_methods": [
                "Spatial coordinate normalization and tissue spot QC (10x Visium / Xenium)",
                "Spatial-aware MRF graph clustering to identify histological domains",
                "Spot-level deconvolution only if a signature matrix is supplied (NNLS; not Cell2location)",
                "Distance-decay ligand-receptor interaction potential analysis",
            ],
            "milestone_go_no_go": f"Colocalization of {target_gene} expressing cells within active immunosuppressive or invasive tumor niches.",
        },
        {
            "phase_number": 4,
            "phase_title": "Multiome Cis-Regulatory Networks & TF Regulons",
            "objective": f"Reconstruct the gene regulatory network (GRN) governing {target_gene} transcriptional control.",
            "computational_methods": [
                "Joint single-cell RNA+ATAC Weighted Nearest Neighbor (WNN) multimodal integration",
                "Distance-constrained peak-to-gene cis-regulatory correlation linking",
                "Optional ExtraTrees co-expression (not SCENIC+/GRNBoost2 unless those libraries are installed)",
                "Do not claim TF footprinting without BAM-level Tn5-bias-corrected coverage",
            ],
            "milestone_go_no_go": f"Identification of at least 1 master regulator TF directly driving {target_gene} expression.",
        },
        {
            "phase_number": 5,
            "phase_title": "Clinical Genomics & Pharmacogenomic Stratification",
            "objective": f"Screen patient cohorts for {target_gene} functional variants and stratify therapeutic response.",
            "computational_methods": [
                "gnomAD PopMax allele frequency filtering to rule out benign population polymorphisms",
                "ACMG/AMP combination of caller-supplied criteria (not a diagnostic engine)",
                "CPIC lookup table for a small allele set if a matching star allele is provided",
                "Research interpretation summary only — never a CLIA/CAP report",
            ],
            "milestone_go_no_go": "Delineation of pathogenic vs benign variant landscape to guide clinical trial inclusion criteria.",
        },
    ]

    plan = {
        "study_title": f"Preclinical Investigation & Translational Strategy: {target_gene} in {disease_indication}",
        "target_gene": target_gene,
        "disease_indication": disease_indication,
        "therapeutic_modality": modality,
        "primary_clinical_objective": clinical_objective,
        "total_phases": len(phases),
        "phases": phases,
        "risk_assessment": {
            "critical_risk": "On-target toxicity in healthy tissues with high basal expression.",
            "mitigation_strategy": "Evaluate GTEx 54-tissue RNA expression profile and select tissue-targeted delivery or prodrug strategy.",
        },
    }
    return plan


def main():
    parser = argparse.ArgumentParser(description="Research Plan Generator")
    parser.add_argument("--target", "-t", required=True, help="Target gene symbol (e.g. 'KRAS')")
    parser.add_argument(
        "--disease", "-d", required=True, help="Disease indication (e.g. 'Pancreatic Ductal Adenocarcinoma')"
    )
    parser.add_argument("--out", "-o", default="research_plan.yml", help="Output YAML plan path")

    args = parser.parse_args()
    plan = create_preclinical_research_plan(args.target, args.disease)
    with open(args.out, "w", encoding="utf-8") as f:
        yaml.dump(plan, f, sort_keys=False)
    logger.info(f"Saved research plan to {args.out}")


if __name__ == "__main__":
    main()
