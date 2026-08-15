#!/usr/bin/env python3
"""
ACMG/AMP 2015 Clinical Variant Pathogenicity Classification Engine.
Implements the 28 ACMG/AMP rules with both deterministic classification and
Tavtigian Bayesian posterior probability evidence synthesis (Hum Mutat 2018).
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.contracts import EvidenceCard, attach_meta  # noqa: E402

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("ACMGClassifier")

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs", "acmg_rules.yml")


def load_acmg_config(config_file: Optional[str] = None) -> Dict[str, Any]:
    """Load ACMG rules configuration containing likelihood ratios and rule criteria."""
    path = config_file or CONFIG_PATH
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    # Default fallback config if file missing
    return {
        "bayesian_prior": 0.10,
        "likelihood_ratios": {
            "very_strong": 350.0,
            "strong": 18.7,
            "moderate": 4.33,
            "supporting": 2.08,
            "benign_supporting": 0.4807,
            "benign_strong": 0.0535,
            "benign_stand_alone": 0.00286,
        },
    }


def classify_acmg_deterministic(criteria_codes: Set[str]) -> Tuple[str, List[str]]:
    """
    Apply standard ACMG/AMP 2015 deterministic combination rules.
    Returns (classification, list of satisfied logic clauses).
    """
    codes = {c.upper().strip() for c in criteria_codes}
    reasons = []

    # Count activated criteria by strength
    pvs = len([c for c in codes if c.startswith("PVS")])
    ps = len([c for c in codes if c.startswith("PS")])
    pm = len([c for c in codes if c.startswith("PM")])
    pp = len([c for c in codes if c.startswith("PP")])

    ba = len([c for c in codes if c.startswith("BA")])
    bs = len([c for c in codes if c.startswith("BS")])
    bp = len([c for c in codes if c.startswith("BP")])

    # Check Stand-alone Benign
    if ba >= 1:
        reasons.append("Stand-alone benign allele frequency (BA1)")
        return "Benign", reasons

    # Check Benign (>= 2 BS)
    if bs >= 2:
        reasons.append(f"At least 2 Strong Benign criteria ({bs} BS)")
        return "Benign", reasons

    # Check Likely Benign
    if bs >= 1 and bp >= 1:
        reasons.append(f"1 Strong Benign ({bs} BS) and at least 1 Supporting Benign ({bp} BP)")
        return "Likely Benign", reasons
    if bp >= 2:
        reasons.append(f"At least 2 Supporting Benign criteria ({bp} BP)")
        return "Likely Benign", reasons

    # Check Pathogenic combinations
    is_pathogenic = False
    if pvs >= 1:
        if ps >= 1:
            reasons.append("1 Very Strong (PVS) + >=1 Strong (PS)")
            is_pathogenic = True
        elif pm >= 2:
            reasons.append("1 Very Strong (PVS) + >=2 Moderate (PM)")
            is_pathogenic = True
        elif pm >= 1 and pp >= 1:
            reasons.append("1 Very Strong (PVS) + 1 Moderate (PM) + >=1 Supporting (PP)")
            is_pathogenic = True
        elif pp >= 2:
            reasons.append("1 Very Strong (PVS) + >=2 Supporting (PP)")
            is_pathogenic = True

    if ps >= 2:
        reasons.append(f">=2 Strong criteria ({ps} PS)")
        is_pathogenic = True
    elif ps >= 1:
        if pm >= 3:
            reasons.append("1 Strong (PS) + >=3 Moderate (PM)")
            is_pathogenic = True
        elif pm >= 2 and pp >= 2:
            reasons.append("1 Strong (PS) + 2 Moderate (PM) + >=2 Supporting (PP)")
            is_pathogenic = True
        elif pm >= 1 and pp >= 4:
            reasons.append("1 Strong (PS) + 1 Moderate (PM) + >=4 Supporting (PP)")
            is_pathogenic = True

    if is_pathogenic:
        # Check if conflicting benign evidence exists
        if (bs + bp) > 0:
            reasons.append("Conflicting benign evidence detected -> downgraded to VUS")
            return "Uncertain Significance", reasons
        return "Pathogenic", reasons

    # Check Likely Pathogenic combinations
    is_likely_pathogenic = False
    if pvs >= 1 and pm >= 1:
        reasons.append("1 Very Strong (PVS) + 1 Moderate (PM)")
        is_likely_pathogenic = True
    elif ps >= 1 and (1 <= pm <= 2):
        reasons.append("1 Strong (PS) + 1-2 Moderate (PM)")
        is_likely_pathogenic = True
    elif ps >= 1 and pp >= 2:
        reasons.append("1 Strong (PS) + >=2 Supporting (PP)")
        is_likely_pathogenic = True
    elif pm >= 3:
        reasons.append(">=3 Moderate criteria (PM)")
        is_likely_pathogenic = True
    elif pm >= 2 and pp >= 2:
        reasons.append("2 Moderate (PM) + >=2 Supporting (PP)")
        is_likely_pathogenic = True
    elif pm >= 1 and pp >= 4:
        reasons.append("1 Moderate (PM) + >=4 Supporting (PP)")
        is_likely_pathogenic = True

    if is_likely_pathogenic:
        if (bs + bp) > 0:
            reasons.append("Conflicting benign evidence detected -> downgraded to VUS")
            return "Uncertain Significance", reasons
        return "Likely Pathogenic", reasons

    # Default to VUS
    reasons.append("Insufficient or conflicting evidence to meet Pathogenic/Benign criteria")
    return "Uncertain Significance", reasons


def compute_bayesian_pathogenicity(
    criteria_codes: Set[str], config: Optional[Dict[str, Any]] = None
) -> Tuple[float, float, str]:
    """
    Compute Bayesian posterior probability P(Pathogenic | Evidence) following Tavtigian et al. (2018).
    Returns (posterior_prob, odds_pathogenicity, classification).
    """
    cfg = config or load_acmg_config()
    prior = cfg.get("bayesian_prior", 0.10)
    lrs = cfg.get("likelihood_ratios", {})

    lr_very_strong = lrs.get("very_strong", 350.0)
    lr_strong = lrs.get("strong", 18.7)
    lr_moderate = lrs.get("moderate", 4.33)
    lr_supporting = lrs.get("supporting", 2.08)

    lr_ba = lrs.get("benign_stand_alone", 1.0 / 350.0)
    lr_bs = lrs.get("benign_strong", 1.0 / 18.7)
    lr_bp = lrs.get("benign_supporting", 1.0 / 2.08)

    odds = 1.0
    for code in criteria_codes:
        c = code.upper().strip()
        if c.startswith("PVS"):
            odds *= lr_very_strong
        elif c.startswith("PS"):
            odds *= lr_strong
        elif c.startswith("PM"):
            odds *= lr_moderate
        elif c.startswith("PP"):
            odds *= lr_supporting
        elif c.startswith("BA"):
            odds *= lr_ba
        elif c.startswith("BS"):
            odds *= lr_bs
        elif c.startswith("BP"):
            odds *= lr_bp

    # Posterior P(P | E) = (Odds * Prior) / (Odds * Prior + (1 - Prior))
    numerator = odds * prior
    denominator = numerator + (1.0 - prior)
    posterior = numerator / denominator

    # Map probability to classification tier
    if posterior >= 0.99:
        tier = "Pathogenic"
    elif posterior >= 0.90:
        tier = "Likely Pathogenic"
    elif posterior <= 0.001:
        tier = "Benign"
    elif posterior < 0.10:
        tier = "Likely Benign"
    else:
        tier = "Uncertain Significance"

    return float(posterior), float(odds), tier


def evaluate_variant_acmg(
    variant_id: str, gene_symbol: str, criteria: List[str], evidence_details: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Comprehensive ACMG evaluation combining deterministic rules and Bayesian synthesis."""
    criteria_set = {c.upper().strip() for c in criteria}
    cfg = load_acmg_config()

    det_class, logic_clauses = classify_acmg_deterministic(criteria_set)
    post_prob, odds, bayes_class = compute_bayesian_pathogenicity(criteria_set, cfg)

    # Detailed rule catalog descriptions
    rules_meta = cfg.get("rules", {})
    annotated_criteria = []
    for code in sorted(criteria_set):
        rule_info = rules_meta.get(code, {})
        annotated_criteria.append(
            {
                "code": code,
                "name": rule_info.get("name", code),
                "strength": rule_info.get("strength", "Unknown"),
                "user_evidence": (evidence_details or {}).get(
                    code, "Caller supplied this code; not independently verified"
                ),
            }
        )

    report_body = {
        "variant_id": variant_id,
        "gene_symbol": gene_symbol,
        "deterministic_classification": det_class,
        "bayesian_classification": bayes_class,
        "posterior_probability_pathogenic": round(post_prob, 5),
        "odds_of_pathogenicity": round(odds, 2),
        "satisfied_criteria": sorted(list(criteria_set)),
        "criteria_breakdown": annotated_criteria,
        "logic_clauses": logic_clauses,
        "clinical_actionability": "Not a clinical actionability call; research combination only",
    }

    evidence_grade = "B" if criteria_set else "abstain"
    card = EvidenceCard(
        execution_fidelity="B" if criteria_set else "abstain",
        input_integrity="A" if (variant_id and gene_symbol) else "B",
        assumption_validity="B",
        statistical_support="A" if (post_prob >= 0.99 or post_prob <= 0.01) else "B",
        parameter_robustness="B",
        details={
            "posterior_probability_pathogenic": post_prob,
            "deterministic_classification": det_class,
            "bayesian_classification": bayes_class,
            "criteria_count": len(criteria_set),
        },
    )

    return attach_meta(
        report_body,
        method="acmg2015_combination_plus_tavtigian_lr",
        backend="local_combiner",
        evidence_grade=evidence_grade,
        limitations=[
            "Combines caller-supplied criteria only. Does not generate PVS1/PM2/PP3 from raw sequence.",
            "YAML implements a subset of Richards 2015 codes, not the full ClinGen SVI points system.",
            "Research-use only. Not CLIA/CAP and not a diagnostic interpretation.",
        ],
        abstain=len(criteria_set) == 0,
        abstain_reason="No ACMG criteria supplied" if len(criteria_set) == 0 else None,
        evidence_card=card,
    )


def main():
    parser = argparse.ArgumentParser(description="ACMG/AMP Variant Pathogenicity Classifier")
    parser.add_argument(
        "--variant", "-v", required=True, help="Variant identifier (e.g. 'chr13:32315508:C:T' or 'c.5266dupC')"
    )
    parser.add_argument("--gene", "-g", required=True, help="Gene symbol (e.g. 'BRCA1')")
    parser.add_argument(
        "--criteria", "-c", required=True, nargs="+", help="Satisfied ACMG criteria (e.g. PVS1 PM2 PP3)"
    )
    parser.add_argument("--output-json", "-o", help="Path to save JSON classification report")

    args = parser.parse_args()
    report = evaluate_variant_acmg(args.variant, args.gene, args.criteria)
    logger.info(
        f"Classification Result: {report['deterministic_classification']} (Posterior: {report['posterior_probability_pathogenic'] * 100:.2f}%)"
    )

    print(yaml.dump(report, sort_keys=False))

    if args.output_json:
        os.makedirs(os.path.dirname(os.path.abspath(args.output_json)) or ".", exist_ok=True)
        import json

        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        logger.info(f"Saved report to {args.output_json}")


if __name__ == "__main__":
    main()
