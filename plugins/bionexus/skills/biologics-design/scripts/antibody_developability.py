#!/usr/bin/env python3
"""Sequence-level antibody liability scan.

This is a motif screen (deamidation, isomerization, sequons, unpaired Cys,
CDR3 hydrophobic runs). It is not Spatial Aggregation Propensity (SAP),
which requires a 3D structure and SASA.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Dict, List, Optional

from _common import GRADE_C, attach_meta

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("AntibodyDevelopability")

HYDROPHOBIC_AAS = {"L", "I", "V", "F", "W", "M", "Y"}
POSITIVE_AAS = {"R", "K"}
NEGATIVE_AAS = {"D", "E"}


def calculate_net_charge(seq: str, ph: float = 7.4) -> float:
    """Crude side-chain count at ~pH 7.4. Not Henderson–Hasselbalch."""
    del ph
    pos = sum(seq.count(aa) for aa in POSITIVE_AAS)
    neg = sum(seq.count(aa) for aa in NEGATIVE_AAS)
    his = seq.count("H") * 0.1
    return round(float(pos - neg + his), 2)


def evaluate_antibody_developability(
    annotated_handle: Dict[str, Any],
    human_germline_identity: Optional[float] = None,
) -> Dict[str, Any]:
    seq = annotated_handle.get("full_sequence", "")
    chain = annotated_handle.get("chain_type", "Heavy")
    cdr3 = annotated_handle.get("cdr3_sequence", "")
    liabilities: List[Dict[str, Any]] = []

    if seq.count("C") % 2 != 0:
        liabilities.append(
            {
                "type": "Unpaired Cysteine",
                "severity": "HIGH",
                "description": f"Odd cysteine count ({seq.count('C')}); disulfide scrambling risk.",
            }
        )

    hydro_matches = re.findall(r"[LIVFWMY]{3,}", cdr3)
    if hydro_matches:
        liabilities.append(
            {
                "type": "Hydrophobic Patch in CDR3",
                "severity": "HIGH" if len(hydro_matches[0]) >= 4 else "MEDIUM",
                "description": f"Contiguous hydrophobic stretch '{hydro_matches[0]}' in CDR3.",
            }
        )

    cdr3_charge = calculate_net_charge(cdr3)
    if abs(cdr3_charge) >= 3.0:
        liabilities.append(
            {
                "type": "Extreme CDR3 Net Charge",
                "severity": "MEDIUM",
                "description": f"CDR3 net charge {cdr3_charge} (count-based, not pKa).",
            }
        )

    for match in re.finditer(r"N[GST]", seq):
        liabilities.append(
            {
                "type": "Asn Deamidation Motif",
                "severity": "MEDIUM" if match.group(0) == "NG" else "LOW",
                "description": f"Motif '{match.group(0)}' at position {match.start() + 1}.",
            }
        )
    for match in re.finditer(r"D[GST]", seq):
        liabilities.append(
            {
                "type": "Asp Isomerization Motif",
                "severity": "MEDIUM" if match.group(0) == "DG" else "LOW",
                "description": f"Motif '{match.group(0)}' at position {match.start() + 1}.",
            }
        )
    for match in re.finditer(r"N[^P][ST]", seq):
        liabilities.append(
            {
                "type": "Fv N-Glycosylation Motif",
                "severity": "HIGH",
                "description": f"Sequon '{match.group(0)}' at position {match.start() + 1}.",
            }
        )

    high_count = sum(1 for item in liabilities if item["severity"] == "HIGH")
    med_count = sum(1 for item in liabilities if item["severity"] == "MEDIUM")
    if high_count == 0 and med_count <= 2:
        tier = "Tier 1: few sequence motifs flagged"
        score = 0.90 - 0.05 * med_count
    elif high_count <= 1 and med_count <= 4:
        tier = "Tier 2: motif flags suggest sequence optimization"
        score = 0.75 - 0.10 * high_count - 0.05 * med_count
    else:
        tier = "Tier 3: many sequence-level liability motifs"
        score = 0.40

    payload = {
        "chain_type": chain,
        "sequence_length": len(seq),
        "cdr3_length": len(cdr3),
        "cdr3_charge": cdr3_charge,
        "total_net_charge": calculate_net_charge(seq),
        "humanness_score": None if human_germline_identity is None else round(float(human_germline_identity), 3),
        "humanness_source": "caller_supplied" if human_germline_identity is not None else "not_computed",
        "developability_tier": tier,
        "developability_score": round(max(0.1, score), 2),
        "total_liabilities_count": len(liabilities),
        "liabilities": liabilities,
    }
    return attach_meta(
        payload,
        method="sequence_motif_liability_scan",
        backend="local_regex",
        evidence_grade=GRADE_C,
        limitations=[
            "Not Spatial Aggregation Propensity (SAP). SAP needs 3D SASA.",
            "Charge is residue counting, not pKa titration.",
            "Humanness is not inferred; pass an IMGT V-gene identity to populate it.",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sequence-level antibody liability scan")
    parser.add_argument("--seq", "-s", required=True, help="Antibody Fv sequence")
    parser.add_argument("--germline-identity", type=float, default=None, help="Optional IMGT V-gene identity [0-1]")
    args = parser.parse_args()
    from antibody_annotator import annotate_variable_domain_imgt

    handle = annotate_variable_domain_imgt(args.seq)
    print(json.dumps(evaluate_antibody_developability(handle, args.germline_identity), indent=2))


if __name__ == "__main__":
    main()
