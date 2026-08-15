#!/usr/bin/env python3
"""
Pharmacogenomics (PGx) Clinical Annotation Engine.
Translates genomic variants into actionable drug response recommendations
based on CPIC (Clinical Pharmacogenetics Implementation Consortium) Level 1A/1B guidelines.
"""

import argparse
import logging
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("Pharmacogenomics")

# Curated CPIC Level 1A actionable Gene-Drug-Variant catalog
PGX_CATALOG = {
    "DPYD": {
        "drug": "Fluorouracil / Capecitabine / Tegafur",
        "indication": "Colorectal, Breast, and Gastrointestinal Cancers",
        "guideline_source": "CPIC Level 1A",
        "phenotype": "Dihydropyrimidine Dehydrogenase (DPD) Deficiency",
        "variants": {
            "c.1905+1G>A": {
                "activity_score": 0.0,
                "recommendation": "Complete DPD deficiency (*2A). Strongly avoid 5-FU or decrease dose by >= 50% with TDM.",
            },
            "c.1679T>G": {
                "activity_score": 0.0,
                "recommendation": "Non-functional *13 allele. High risk of life-threatening neutropenia and mucositis. Dose reduce 50%.",
            },
            "c.2846A>T": {
                "activity_score": 0.5,
                "recommendation": "Decreased function allele. Reduce starting dose by 25-50%.",
            },
        },
        "default_recommendation": "Consult CPIC DPYD guideline. If activity score < 1.0, initiate dose reduction.",
    },
    "CYP2C19": {
        "drug": "Clopidogrel (Plavix)",
        "indication": "Acute Coronary Syndromes / Percutaneous Coronary Intervention",
        "guideline_source": "CPIC Level 1A",
        "phenotype": "CYP2C19 Intermediate / Poor Metabolizer",
        "variants": {
            "*2": {
                "activity_score": 0.0,
                "recommendation": "Loss of function. Impaired bioactivation of clopidogrel. Use alternative antiplatelet (Prasugrel or Ticagrelor).",
            },
            "*3": {
                "activity_score": 0.0,
                "recommendation": "Loss of function. Avoid clopidogrel; prescribe Prasugrel or Ticagrelor.",
            },
            "*17": {
                "activity_score": 2.0,
                "recommendation": "Ultra-rapid metabolizer. Standard clopidogrel dose with bleeding surveillance.",
            },
        },
        "default_recommendation": "Evaluate CYP2C19 star allele diplotype for antiplatelet selection.",
    },
    "TPMT": {
        "drug": "Azathioprine / 6-Mercaptopurine / Thioguanine",
        "indication": "Acute Lymphoblastic Leukemia / Autoimmune Disorders",
        "guideline_source": "CPIC Level 1A",
        "phenotype": "Thiopurine S-Methyltransferase Deficiency",
        "variants": {
            "*3A": {
                "activity_score": 0.0,
                "recommendation": "Poor metabolizer. High risk of fatal myelosuppression. Reduce thiopurine starting dose by 90%.",
            },
            "*3C": {"activity_score": 0.0, "recommendation": "Reduced activity. Reduce dose by 30-50%."},
        },
        "default_recommendation": "Adjust thiopurine dosing based on combined TPMT / NUDT15 genotype.",
    },
    "SLCO1B1": {
        "drug": "Simvastatin",
        "indication": "Hypercholesterolemia / Cardiovascular Disease",
        "guideline_source": "CPIC Level 1A",
        "phenotype": "OATP1B1 Transporter Decreased Function",
        "variants": {
            "c.521T>C": {
                "activity_score": 0.5,
                "recommendation": "High risk of simvastatin-induced myopathy / rhabdomyolysis (*5 allele). Prescribe lower dose or Rosuvastatin / Pravastatin.",
            }
        },
        "default_recommendation": "Select alternative statin (e.g. Pravastatin) if SLCO1B1 function is impaired.",
    },
}


def lookup_pharmacogenomics(gene_symbol: str, variant_str: Optional[str] = None) -> Dict[str, Any]:
    """Lookup CPIC actionable recommendations for a gene and optional variant."""
    gene = gene_symbol.strip().upper()
    entry = PGX_CATALOG.get(gene)

    if not entry:
        return {
            "gene": gene,
            "has_cpic_guideline": False,
            "status": "No CPIC Level 1A actionable PGx guideline registered.",
        }

    matched_variant = None
    rec_text = entry["default_recommendation"]

    if variant_str:
        for var_key, var_data in entry.get("variants", {}).items():
            if var_key.lower() in variant_str.lower():
                matched_variant = var_key
                rec_text = var_data["recommendation"]
                break

    return {
        "gene": gene,
        "has_cpic_guideline": True,
        "drug": entry["drug"],
        "indication": entry["indication"],
        "guideline_level": entry["guideline_source"],
        "phenotype": entry["phenotype"],
        "matched_variant": matched_variant,
        "clinical_recommendation": rec_text,
    }


def main():
    parser = argparse.ArgumentParser(description="Pharmacogenomic (PGx) Actionability Lookup")
    parser.add_argument("--gene", "-g", required=True, help="Gene symbol (e.g. 'DPYD', 'CYP2C19', 'TPMT')")
    parser.add_argument("--variant", "-v", default=None, help="Variant name (e.g. 'c.1905+1G>A' or '*2')")

    args = parser.parse_args()
    res = lookup_pharmacogenomics(args.gene, variant_str=args.variant)
    import json

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
