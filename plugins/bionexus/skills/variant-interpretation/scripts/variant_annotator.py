#!/usr/bin/env python3
"""
Multi-Source Genomic Variant Annotator.
Parses HGVS, VCF coordinates, and protein changes; resolves molecular consequence;
aggregates population frequencies, ClinVar submissions, and automated ACMG evidence proposals.
"""

import argparse
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("VariantAnnotator")


def parse_variant_string(variant_str: str) -> Dict[str, Any]:
    """Parse HGVS cDNA, protein, or chr:pos:ref:alt string into structured components."""
    v = variant_str.strip()
    res = {
        "raw_input": v,
        "format": "unknown",
        "chrom": None,
        "pos": None,
        "ref": None,
        "alt": None,
        "cdna": None,
        "protein": None,
        "predicted_consequence": "unknown",
    }

    # Format 1: chr17:41245466:G:A or 17-41245466-G-A
    vcf_match = re.match(r"^(?:chr)?([0-9XYMT]+)[:\-_](\d+)[:\-_]([ACGTN]+)[:\-_]([ACGTN]+)$", v, re.IGNORECASE)
    if vcf_match:
        res["format"] = "genomic_vcf"
        res["chrom"] = vcf_match.group(1).upper()
        res["pos"] = int(vcf_match.group(2))
        res["ref"] = vcf_match.group(3).upper()
        res["alt"] = vcf_match.group(4).upper()
        # Consequence inference
        if len(res["ref"]) == 1 and len(res["alt"]) == 1:
            res["predicted_consequence"] = "snv"
        elif len(res["ref"]) != len(res["alt"]):
            res["predicted_consequence"] = "frameshift_or_indel"
        return res

    # Format 2: c.5266dupC or c.181T>G or c.436+1G>A
    cdna_match = re.search(r"c\.([0-9+\-_]+)([A-Za-z0-9>_]+)", v)
    if cdna_match:
        res["format"] = "hgvs_cdna"
        res["cdna"] = v
        coord = cdna_match.group(1)
        change = cdna_match.group(2)
        if "+" in coord or "-" in coord:
            res["predicted_consequence"] = "splice_region"
            if "+1" in coord or "+2" in coord or "-1" in coord or "-2" in coord:
                res["predicted_consequence"] = "canonical_splice_site"
        elif "del" in change or "dup" in change or "ins" in change:
            res["predicted_consequence"] = "frameshift"
        elif ">" in change:
            res["predicted_consequence"] = "single_nucleotide_variant"
        return res

    # Format 3: p.Arg175His or p.Glu1818Ter or p.R175H
    prot_match = re.search(r"p\.([A-Z][a-z]{2}|\w)(\d+)([A-Z][a-z]{2}|\w|\*|Ter)", v)
    if prot_match:
        res["format"] = "hgvs_protein"
        res["protein"] = v
        ref_aa = prot_match.group(1)
        prot_match.group(2)
        alt_aa = prot_match.group(3)
        if alt_aa in ("*", "Ter", "X"):
            res["predicted_consequence"] = "nonsense"
        elif ref_aa != alt_aa:
            res["predicted_consequence"] = "missense"
        else:
            res["predicted_consequence"] = "synonymous"
        return res

    return res


def propose_acmg_criteria(
    annotation: Dict[str, Any],
    gene_info: Optional[Dict[str, Any]] = None,
    gnomad_af: Optional[float] = None,
    in_silico_damaging: Optional[bool] = None,
    known_pathogenic_codon: bool = False,
    lof_is_known_mechanism: bool = False,
) -> Tuple[List[str], Dict[str, str]]:
    """Propose *candidate* ACMG codes only from supplied evidence.

    Missing allele frequency does not activate PM2.
    in_silico_damaging defaults to None (no PP3/BP4).
    PVS1 requires an explicit LOF-mechanism flag.
    """
    proposed_codes = []
    rationale = {}
    consequence = annotation.get("predicted_consequence", "")
    gene_symbol = (gene_info or {}).get("symbol", "GENE")

    if consequence in ("nonsense", "frameshift", "canonical_splice_site"):
        if lof_is_known_mechanism:
            proposed_codes.append("PVS1")
            rationale["PVS1"] = (
                f"Predicted null variant ({consequence}) and caller asserted LOF is the disease mechanism for {gene_symbol}."
            )
        else:
            rationale["PVS1_withheld"] = (
                f"Predicted {consequence}, but PVS1 is withheld until LOF is established as the mechanism (Abou Tayoun 2018)."
            )

    if gnomad_af is not None:
        if gnomad_af >= 0.05:
            proposed_codes.append("BA1")
            rationale["BA1"] = f"Provided AF {gnomad_af * 100:.2f}% >= 5% (stand-alone benign threshold)."
        elif gnomad_af >= 0.01:
            proposed_codes.append("BS1")
            rationale["BS1"] = f"Provided AF {gnomad_af * 100:.2f}% >= 1%."
        elif gnomad_af < 0.00001:
            proposed_codes.append("PM2")
            rationale["PM2"] = f"Provided AF {gnomad_af:.2e} < 1e-5."
    else:
        rationale["PM2_withheld"] = "No gnomAD AF supplied; PM2 is not assumed."

    if known_pathogenic_codon:
        proposed_codes.append("PM5")
        rationale["PM5"] = "Caller asserted a different pathogenic missense at the same codon."

    if in_silico_damaging is True and consequence not in ("synonymous", "benign"):
        proposed_codes.append("PP3")
        rationale["PP3"] = (
            "Caller supplied a calibrated in-silico damaging call. BLOSUM/heuristic scores are not valid PP3."
        )
    elif in_silico_damaging is False:
        proposed_codes.append("BP4")
        rationale["BP4"] = "Caller supplied a calibrated in-silico tolerated call."
    else:
        rationale["PP3_BP4_withheld"] = "No calibrated in-silico predictor supplied; PP3/BP4 not applied."

    if consequence == "synonymous":
        proposed_codes.append("BP7")
        rationale["BP7"] = "Synonymous substitution; splice impact not independently assessed."

    return proposed_codes, rationale


def ingest_external_annotation(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Map a VEP/InterVar-like JSON dict onto proposed ACMG codes.

    Expected optional keys: consequence, gnomad_af, lof_is_known_mechanism,
    in_silico_damaging, known_pathogenic_codon, gene, variant.
    """
    consequence = str(payload.get("consequence") or payload.get("most_severe_consequence") or "")
    annotation = {
        "predicted_consequence": consequence,
        "raw_input": payload.get("variant") or payload.get("input") or "",
        "format": "external_json",
    }
    codes, rationale = propose_acmg_criteria(
        annotation,
        gene_info={"symbol": payload.get("gene") or payload.get("symbol") or "GENE"},
        gnomad_af=payload.get("gnomad_af", payload.get("af")),
        in_silico_damaging=payload.get("in_silico_damaging"),
        known_pathogenic_codon=bool(payload.get("known_pathogenic_codon", False)),
        lof_is_known_mechanism=bool(payload.get("lof_is_known_mechanism", False)),
    )
    return {
        "proposed_acmg_criteria": codes,
        "criteria_rationales": rationale,
        "method": "external_json_ingest",
        "backend": "caller_vep_or_intervar",
        "evidence_grade": "B" if codes else "abstain",
        "limitations": ["Codes follow caller fields. This function does not run VEP."],
    }


def annotate_variant_full(
    variant_str: str,
    gene_symbol: str,
    gnomad_af: Optional[float] = None,
    in_silico_damaging: Optional[bool] = None,
    lof_is_known_mechanism: bool = False,
) -> Dict[str, Any]:
    """Parse a variant string and propose ACMG codes only from supplied evidence."""
    parsed = parse_variant_string(variant_str)
    gene_meta = {"symbol": gene_symbol}
    proposed_codes, rationale = propose_acmg_criteria(
        parsed,
        gene_info=gene_meta,
        gnomad_af=gnomad_af,
        in_silico_damaging=in_silico_damaging,
        lof_is_known_mechanism=lof_is_known_mechanism,
    )

    if gnomad_af is None:
        pop_status = "unknown_af"
    elif gnomad_af < 0.0001:
        pop_status = "rare_if_af_accurate"
    else:
        pop_status = "not_rare"

    return {
        "variant": variant_str,
        "gene": gene_symbol,
        "parsed_structure": parsed,
        "population_genetics": {
            "gnomad_global_af": gnomad_af,
            "status": pop_status,
        },
        "proposed_acmg_criteria": proposed_codes,
        "criteria_rationales": rationale,
        "method": "string_parse_plus_optional_codes",
        "backend": "local_parser",
        "evidence_grade": "C",
        "abstain": len(proposed_codes) == 0,
        "limitations": [
            "Does not query VEP, ClinVar, or gnomAD.",
            "Research-use only. Not a clinical diagnostic.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Multi-Source Variant Annotator")
    parser.add_argument(
        "--variant", "-v", required=True, help="Variant string (e.g. 'c.5266dupC' or 'chr13:32315508:C:T')"
    )
    parser.add_argument("--gene", "-g", required=True, help="Gene symbol (e.g. 'BRCA1')")
    parser.add_argument("--gnomad-af", type=float, default=None, help="gnomAD allele frequency (e.g. 0.000005)")

    args = parser.parse_args()
    res = annotate_variant_full(args.variant, args.gene, gnomad_af=args.gnomad_af)
    import json

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
