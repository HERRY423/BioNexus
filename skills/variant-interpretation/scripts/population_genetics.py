#!/usr/bin/env python3
"""
Population Genetics & gnomAD Allele Frequency Stratification Module.
Evaluates continental ancestry frequencies, calculates PopMax thresholds,
and determines ACMG population frequency criteria (BA1 / BS1 / PM2).
"""

import argparse
import logging
from typing import Any, Dict

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("PopulationGenetics")


def evaluate_population_frequencies(
    subpop_frequencies: Dict[str, float], inheritance_mode: str = "autosomal_dominant", disease_prevalence: float = 1e-4
) -> Dict[str, Any]:
    """
    Evaluate continental subpopulation allele frequencies against ACMG thresholds.
    subpop_frequencies: e.g. {'afr': 0.0001, 'nfe': 0.00002, 'eas': 0.0, 'amr': 0.00005}
    """
    if not subpop_frequencies:
        return {
            "status": "no_frequencies_supplied",
            "popmax_af": None,
            "popmax_subpop": "none",
            "activated_acmg_criteria": [],
            "rationale": "No subpopulation frequencies supplied; PM2 is withheld.",
        }

    popmax_subpop = max(subpop_frequencies, key=subpop_frequencies.get)
    popmax_af = subpop_frequencies[popmax_subpop]
    global_mean_af = sum(subpop_frequencies.values()) / len(subpop_frequencies)

    activated_rules = []
    rationale_list = []

    # 1. Stand-Alone Benign (BA1: AF >= 5.0%)
    if popmax_af >= 0.05:
        activated_rules.append("BA1")
        rationale_list.append(
            f"PopMax allele frequency in {popmax_subpop.upper()} is {popmax_af * 100:.2f}% (>= 5.0% BA1 threshold)."
        )

    # 2. Strong Benign (BS1: AF >= 1.0% for dominant, >= 2.0% for recessive)
    bs1_cutoff = 0.01 if inheritance_mode.lower() == "autosomal_dominant" else 0.02
    if popmax_af >= bs1_cutoff and "BA1" not in activated_rules:
        activated_rules.append("BS1")
        rationale_list.append(
            f"PopMax allele frequency in {popmax_subpop.upper()} is {popmax_af * 100:.2f}% (>= {bs1_cutoff * 100:.1f}% BS1 threshold for {inheritance_mode})."
        )

    # 3. Moderate Pathogenic (PM2: PopMax AF < 0.001% or absent)
    if popmax_af < 0.00001 and not activated_rules:
        activated_rules.append("PM2")
        rationale_list.append(
            f"PopMax allele frequency ({popmax_af:.2e}) is below 0.001% PM2 rarity threshold across all populations."
        )

    return {
        "inheritance_mode": inheritance_mode,
        "popmax_af": round(popmax_af, 6),
        "popmax_subpopulation": popmax_subpop.upper(),
        "global_mean_af": round(global_mean_af, 6),
        "subpopulation_breakdown": subpop_frequencies,
        "activated_acmg_criteria": activated_rules,
        "rationales": rationale_list,
    }


def main():
    parser = argparse.ArgumentParser(description="gnomAD Population Genetics Evaluator")
    parser.add_argument(
        "--subpops", "-s", nargs="+", help="Key=value subpopulation frequencies (e.g. nfe=0.0002 afr=0.00001)"
    )
    parser.add_argument(
        "--mode", "-m", default="autosomal_dominant", choices=["autosomal_dominant", "autosomal_recessive", "x_linked"]
    )

    args = parser.parse_args()
    freq_map = {}
    if args.subpops:
        for item in args.subpops:
            k, v = item.split("=")
            freq_map[k.strip().lower()] = float(v)

    res = evaluate_population_frequencies(freq_map, inheritance_mode=args.mode)
    import json

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
