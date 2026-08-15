#!/usr/bin/env python3
"""
Cross-Skill Intelligent Scientific Intent Classifier & Router.
Analyzes scientific research queries, extracts biological entities (genes, variants, diseases, modalities),
and constructs multi-skill execution workflows across all BioNexus skills and MCP tools.
"""

import argparse
import logging
import re
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("SkillRouter")

# Skill Capability Catalog
SKILL_REGISTRY = {
    "single-cell-rna-qc": {
        "domain": "Single-Cell Quality Control",
        "keywords": ["scrna", "single cell", "qc", "mad", "doublet", "ambient rna", "soup", "scrublet"],
        "primary_script": "skills/single-cell-rna-qc/scripts/qc_analysis.py",
    },
    "scvi-tools": {
        "domain": "Single-Cell Deep Probabilistic Modeling",
        "keywords": ["scvi", "scanvi", "vae", "batch integration", "label transfer", "latent space", "totalvi"],
        "primary_script": "skills/scvi-tools/scripts/train_model.py",
    },
    "spatial-transcriptomics": {
        "domain": "Spatial Transcriptomics & Microenvironment",
        "keywords": [
            "spatial",
            "visium",
            "xenium",
            "merfish",
            "niche",
            "deconvolution",
            "moran",
            "svg",
            "tissue slice",
        ],
        "primary_script": "skills/spatial-transcriptomics/scripts/spatial_clustering.py",
    },
    "variant-interpretation": {
        "domain": "Clinical Genomic Variant Interpretation",
        "keywords": [
            "variant",
            "mutation",
            "acmg",
            "pathogenic",
            "clinvar",
            "gnomad",
            "splice",
            "pgx",
            "pharmacogenomics",
        ],
        "primary_script": "skills/variant-interpretation/scripts/acmg_classifier.py",
    },
    "protein-structure-analysis": {
        "domain": "3D Protein Structure & Drug Design",
        "keywords": [
            "structure",
            "pdb",
            "alphafold",
            "plddt",
            "binding pocket",
            "docking",
            "vina",
            "tm-score",
            "druggability",
        ],
        "primary_script": "skills/protein-structure-analysis/scripts/structure_analyzer.py",
    },
    "multiome-integration": {
        "domain": "Multiome RNA+ATAC & Gene Regulatory Networks",
        "keywords": ["multiome", "atac", "chromatin", "regulon", "scenic", "motif", "footprint", "peak", "enhancer"],
        "primary_script": "skills/multiome-integration/scripts/grn_inference.py",
    },
    "nextflow-development": {
        "domain": "HPC & Cloud Nextflow Orchestration",
        "keywords": ["nextflow", "nf-core", "slurm", "pipeline", "batch", "samplesheet", "rnaseq", "sarek"],
        "primary_script": "skills/nextflow-development/scripts/cluster_profile_generator.py",
    },
    "instrument-data-to-allotrope": {
        "domain": "Lab Automation & Allotrope ASM Standardization",
        "keywords": ["plate reader", "allotrope", "asm", "lims", "tecan", "biotek", "nanodrop", "instrument"],
        "primary_script": "skills/instrument-data-to-allotrope/scripts/convert_to_asm.py",
    },
    "knowledge-graph-augmentation": {
        "domain": "Biomedical GraphRAG & Multi-Hop Path Reasoning",
        "keywords": ["knowledge graph", "graphrag", "target disease", "path reasoning", "subgraph"],
        "primary_script": "skills/knowledge-graph-augmentation/scripts/hypothesis_validator.py",
    },
}


def extract_biological_entities(query_text: str) -> Dict[str, List[str]]:
    """Extract gene symbols, variant notations, diseases, and technologies from free text."""
    text = query_text.strip()

    # Gene symbols: uppercase 2-6 alphanumeric (e.g. TP53, BRCA1, EGFR, KRAS)
    gene_matches = re.findall(r"\b([A-Z][A-Z0-9]{1,5})\b", text)
    stopwords = {"AND", "OR", "NOT", "THE", "FOR", "RNA", "DNA", "PDB", "QC", "ASM", "API", "HPC", "WGS", "WES", "PCR"}
    genes = [g for g in set(gene_matches) if g not in stopwords]

    # Variant matches: c.123A>G, p.Val600Glu, V600E, chr17:41245466:G:A
    var_matches = re.findall(
        r"\b(?:c\.[0-9+\-_]+[A-Za-z0-9>_]+|p\.[A-Za-z]+[0-9]+[A-Za-z*]+|[A-Z][0-9]+[A-Z]|chr[0-9XYMT]+:[0-9]+:[A-Z]+:[A-Z]+)\b",
        text,
        re.IGNORECASE,
    )

    # Diseases / indications
    disease_keywords = [
        "cancer",
        "adenocarcinoma",
        "melanoma",
        "carcinoma",
        "lymphoma",
        "leukemia",
        "diabetes",
        "alzheimer",
        "cardiovascular",
    ]
    diseases = [d for d in disease_keywords if d in text.lower()]

    return {"genes": genes, "variants": var_matches, "diseases": diseases}


def route_scientific_query(query_text: str) -> Dict[str, Any]:
    """
    Classify query intent, score matching skills, and construct an execution plan.
    """
    text_lower = query_text.lower()
    entities = extract_biological_entities(query_text)

    skill_scores = {}
    for skill_name, meta in SKILL_REGISTRY.items():
        score = 0
        for kw in meta["keywords"]:
            if kw in text_lower:
                score += 1.0
        if score > 0:
            skill_scores[skill_name] = score

    # Sort skills descending by relevance score
    ranked_skills = sorted(skill_scores.items(), key=lambda x: x[1], reverse=True)
    primary_skill = ranked_skills[0][0] if ranked_skills else "research-workflow-orchestrator"

    # Construct execution pipeline
    execution_steps = []
    if primary_skill == "variant-interpretation" or entities["variants"]:
        execution_steps.append({"step": 1, "tool": "search_gnomad", "purpose": "Query population allele frequencies"})
        execution_steps.append(
            {
                "step": 2,
                "script": "variant-interpretation/scripts/acmg_classifier.py",
                "purpose": "ACMG/AMP 28-rule Bayesian classification",
            }
        )
        execution_steps.append(
            {
                "step": 3,
                "script": "variant-interpretation/scripts/pharmacogenomics.py",
                "purpose": "CPIC actionable PGx lookup",
            }
        )
    elif primary_skill == "protein-structure-analysis" or ("structure" in text_lower or "docking" in text_lower):
        execution_steps.append(
            {"step": 1, "tool": "search_alphafold", "purpose": "Retrieve AI predicted 3D structure & pLDDT"}
        )
        execution_steps.append(
            {
                "step": 2,
                "script": "protein-structure-analysis/scripts/binding_pocket_detector.py",
                "purpose": "Detect 3D cavity & druggability",
            }
        )
        execution_steps.append(
            {
                "step": 3,
                "script": "protein-structure-analysis/scripts/drugability_scorer.py",
                "purpose": "Target tractability assessment",
            }
        )
    elif primary_skill == "spatial-transcriptomics":
        execution_steps.append(
            {
                "step": 1,
                "script": "spatial-transcriptomics/scripts/spatial_preprocessing.py",
                "purpose": "Coordinate normalization & QC",
            }
        )
        execution_steps.append(
            {
                "step": 2,
                "script": "spatial-transcriptomics/scripts/spatial_clustering.py",
                "purpose": "Spatial-aware MRF domain clustering",
            }
        )
        execution_steps.append(
            {
                "step": 3,
                "script": "spatial-transcriptomics/scripts/spatial_niche_analysis.py",
                "purpose": "Microenvironment niche discovery",
            }
        )
    else:
        execution_steps.append(
            {"step": 1, "tool": "search_opentargets", "purpose": "Evaluate genetic target-disease associations"}
        )
        execution_steps.append({"step": 2, "tool": "search_chembl", "purpose": "Query known bioactive small molecules"})
        execution_steps.append(
            {
                "step": 3,
                "script": "knowledge-graph-augmentation/scripts/hypothesis_validator.py",
                "purpose": "GraphRAG topological validation",
            }
        )

    return {
        "query": query_text,
        "extracted_entities": entities,
        "primary_skill": primary_skill,
        "skill_relevance_ranking": dict(ranked_skills),
        "recommended_execution_plan": execution_steps,
    }


def main():
    parser = argparse.ArgumentParser(description="Scientific Intent Router")
    parser.add_argument("--query", "-q", required=True, help="Scientific research prompt or question")

    args = parser.parse_args()
    res = route_scientific_query(args.query)
    import json

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
