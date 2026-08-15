#!/usr/bin/env python3
"""
Donor/acceptor PWM log-odds scorer.
Not MaxEntScan or SpliceAI. Does not assign ACMG PVS1/PP3/BP7.
"""

import argparse
import logging
from typing import Any, Dict

import numpy as np

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("SplicePredictor")

# Human 5' Donor Splice Site Consensus PWM (Positions -3 to +6, where cleavage is between -1 and +1)
# Length = 9 bp: [exon -3, -2, -1 | intron +1, +2, +3, +4, +5, +6]
DONOR_PWM = {
    "A": [0.34, 0.60, 0.10, 0.00, 0.00, 0.52, 0.71, 0.08, 0.16],
    "C": [0.36, 0.13, 0.04, 0.00, 0.00, 0.03, 0.08, 0.06, 0.17],
    "G": [0.18, 0.13, 0.80, 1.00, 0.00, 0.42, 0.12, 0.81, 0.21],
    "T": [0.12, 0.14, 0.06, 0.00, 1.00, 0.03, 0.09, 0.05, 0.46],
}

# Human 3' Acceptor Splice Site Consensus PWM (Positions -14 to +1, cleavage between -1 and +1)
# Core motif [-3, -2, -1 | +1]: N C A G | G
ACCEPTOR_CORE_PWM = {
    "A": [0.20, 0.01, 0.99, 0.00, 0.23],
    "C": [0.45, 0.75, 0.00, 0.00, 0.14],
    "G": [0.10, 0.01, 0.01, 1.00, 0.52],
    "T": [0.25, 0.23, 0.00, 0.00, 0.11],
}


def score_sequence_pwm(seq: str, pwm: Dict[str, list]) -> float:
    """Calculate log-odds score of a nucleotide sequence against a splice PWM."""
    seq = seq.upper()
    pwm_len = len(next(iter(pwm.values())))
    if len(seq) < pwm_len:
        return 0.0

    score = 0.0
    for pos in range(pwm_len):
        base = seq[pos]
        p_base = pwm.get(base, [0.25] * pwm_len)[pos]
        # Log2 likelihood ratio vs background frequency (0.25)
        score += np.log2((max(p_base, 1e-4)) / 0.25)
    return float(score)


def predict_splice_disruption(ref_seq: str, alt_seq: str, splice_type: str = "donor") -> Dict[str, Any]:
    """
    Predict impact of variant on splice site strength.
    Computes reference score, mutant score, and Delta Score.
    """
    pwm = DONOR_PWM if splice_type.lower() == "donor" else ACCEPTOR_CORE_PWM
    pwm_len = len(next(iter(pwm.values())))

    ref_clean = ref_seq.upper().strip()[:pwm_len]
    alt_clean = alt_seq.upper().strip()[:pwm_len]

    ref_score = score_sequence_pwm(ref_clean, pwm)
    alt_score = score_sequence_pwm(alt_clean, pwm)
    delta_score = ref_score - alt_score  # Positive delta indicates loss of splice site

    # Relative percentage reduction
    max_score = score_sequence_pwm("CAGGTGAGT" if splice_type == "donor" else "NCAGG", pwm)
    rel_reduction = max(0.0, min(1.0, delta_score / (max_score + 1e-6)))

    if delta_score > 6.0 or rel_reduction > 0.70:
        impact = "Large PWM score drop (heuristic; not PVS1)"
    elif delta_score > 2.5 or rel_reduction > 0.30:
        impact = "Moderate PWM score drop (heuristic; not PP3)"
    elif delta_score < 0.5:
        impact = "Small PWM score change (heuristic; not BP7)"
    else:
        impact = "Intermediate PWM score change"

    return {
        "splice_type": splice_type,
        "ref_sequence": ref_clean,
        "alt_sequence": alt_clean,
        "ref_splice_score": round(ref_score, 3),
        "alt_splice_score": round(alt_score, 3),
        "delta_splice_score": round(delta_score, 3),
        "relative_reduction": round(rel_reduction, 3),
        "predicted_impact": impact,
        "acmg_evidence": [],
        "method": "donor_acceptor_pwm_logodds",
        "backend": "local_pwm",
        "evidence_grade": "C",
        "limitations": [
            "9-mer/5-mer PWM log-odds. Not MaxEntScan, SpliceAI, or SVI-calibrated PP3.",
            "No ACMG code is assigned from this score.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Splice Site Disruption Predictor")
    parser.add_argument(
        "--ref", "-r", required=True, help="Wild-type reference sequence across splice motif (e.g. 'CAGGTGAGT')"
    )
    parser.add_argument("--alt", "-a", required=True, help="Mutant sequence across splice motif (e.g. 'CAGATGAGT')")
    parser.add_argument("--type", "-t", default="donor", choices=["donor", "acceptor"], help="Splice site type")

    args = parser.parse_args()
    res = predict_splice_disruption(args.ref, args.alt, splice_type=args.type)
    import json

    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
