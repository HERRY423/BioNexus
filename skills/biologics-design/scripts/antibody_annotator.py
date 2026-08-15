#!/usr/bin/env python3
"""Antibody Fv annotation.

Uses abnumber (IMGT/Chothia) when installed. Otherwise a Cys/Trp regex
heuristic that must not be reported as IMGT numbering.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
from typing import Any, Dict, Optional

from _common import GRADE_A, GRADE_C, attach_meta, is_available

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("AntibodyAnnotator")


def detect_chain_type(sequence: str) -> str:
    """Classify VH vs VL from common J-region / FR2 motifs."""
    seq = sequence.strip().upper()
    if re.search(r"W[GQ]QG", seq) or re.search(r"WVR[QA]", seq):
        return "Heavy"
    if re.search(r"FG[GQ]G", seq) or re.search(r"WY[QL]Q", seq):
        return "Light"
    return "Heavy" if "VQL" in seq[:10] else "Light"


def _annotate_with_abnumber(sequence: str, chain_type: Optional[str]) -> Dict[str, Any]:
    from abnumber import Chain

    seq = sequence.strip().upper()
    chain = Chain(seq, scheme="imgt")
    is_heavy = bool(getattr(chain, "is_heavy_chain", chain_type != "Light"))
    prefix = "CDR-H" if is_heavy else "CDR-L"
    regions = {
        "FR1": str(chain.fr1_seq),
        f"{prefix}1": str(chain.cdr1_seq),
        "FR2": str(chain.fr2_seq),
        f"{prefix}2": str(chain.cdr2_seq),
        "FR3": str(chain.fr3_seq),
        f"{prefix}3": str(chain.cdr3_seq),
        "FR4": str(chain.fr4_seq),
    }
    cdr3 = regions[f"{prefix}3"]
    handle = {
        "chain_type": "Heavy" if is_heavy else "Light",
        "sequence_length": len(seq),
        "full_sequence": seq,
        "regions": regions,
        "cdr_lengths": {
            f"{prefix}1_length": len(regions[f"{prefix}1"]),
            f"{prefix}2_length": len(regions[f"{prefix}2"]),
            f"{prefix}3_length": len(cdr3),
        },
        "cdr3_sequence": cdr3,
        "cdr3_length": len(cdr3),
        "is_valid_fv": bool(len(cdr3) >= 3 and len(seq) >= 90),
        "numbering_scheme": "imgt",
    }
    return attach_meta(
        handle,
        method="abnumber_imgt",
        backend="abnumber",
        evidence_grade=GRADE_A,
        limitations=["IMGT numbering via abnumber. Chothia available only if requested separately."],
    )


def _annotate_regex_heuristic(sequence: str, chain_type: Optional[str]) -> Dict[str, Any]:
    seq = sequence.strip().upper()
    chain = chain_type or detect_chain_type(seq)

    cys_matches = [m.start() for m in re.finditer(r"C", seq)]
    cys1_pos = next((c for c in cys_matches if 15 <= c <= 30), cys_matches[0] if cys_matches else -1)
    cys2_pos = next(
        (c for c in reversed(cys_matches) if 80 <= c <= 115), cys_matches[-1] if len(cys_matches) >= 2 else -1
    )

    if chain == "Heavy":
        fr4_match = re.search(r"W[GA]QG", seq)
    else:
        fr4_match = re.search(r"FG[A-Z]G", seq)
    fr4_start = fr4_match.start() if fr4_match else (cys2_pos + 15 if cys2_pos > 0 else max(0, len(seq) - 12))

    if cys2_pos != -1 and fr4_start > cys2_pos:
        cdr3_seq = seq[cys2_pos + 1 : fr4_start]
        fr3_seq = seq[cys1_pos + 15 : cys2_pos + 1] if cys1_pos > 0 else seq[: cys2_pos + 1]
    else:
        cdr3_seq = seq[max(0, len(seq) - 25) : len(seq) - 10]
        fr3_seq = seq[35 : max(0, len(seq) - 25)]

    trp_match = re.search(r"W[VIL][RKQ][QA]", seq)
    trp_pos = trp_match.start() if trp_match else (cys1_pos + 12 if cys1_pos > 0 else 35)
    fr1_seq = seq[: cys1_pos + 4] if cys1_pos > 0 else seq[:26]
    cdr1_seq = seq[len(fr1_seq) : trp_pos]
    fr2_seq = seq[trp_pos : trp_pos + 14]
    cdr2_seq = seq[trp_pos + 14 : trp_pos + 24]
    fr4_seq = seq[fr4_start:]
    cdr_prefix = "CDR-H" if chain == "Heavy" else "CDR-L"

    handle = {
        "chain_type": chain,
        "sequence_length": len(seq),
        "full_sequence": seq,
        "regions": {
            "FR1": fr1_seq,
            f"{cdr_prefix}1": cdr1_seq,
            "FR2": fr2_seq,
            f"{cdr_prefix}2": cdr2_seq,
            "FR3": fr3_seq,
            f"{cdr_prefix}3": cdr3_seq,
            "FR4": fr4_seq,
        },
        "cdr_lengths": {
            f"{cdr_prefix}1_length": len(cdr1_seq),
            f"{cdr_prefix}2_length": len(cdr2_seq),
            f"{cdr_prefix}3_length": len(cdr3_seq),
        },
        "cdr3_sequence": cdr3_seq,
        "cdr3_length": len(cdr3_seq),
        "is_valid_fv": bool(len(cdr3_seq) >= 3 and len(seq) >= 90),
        "numbering_scheme": "regex_anchor_heuristic",
    }
    return attach_meta(
        handle,
        method="regex_cys_trp_anchors",
        backend="local_heuristic",
        evidence_grade=GRADE_C,
        limitations=[
            "Not IMGT or Chothia numbering. CDR2 is a fixed-length slice.",
            "Install abnumber (ANARCI) for scheme-faithful numbering.",
        ],
    )


def annotate_variable_domain_imgt(sequence: str, chain_type: Optional[str] = None) -> Dict[str, Any]:
    """Annotate FR/CDR regions. Name kept for compatibility; method field is authoritative."""
    if is_available("abnumber"):
        try:
            return _annotate_with_abnumber(sequence, chain_type)
        except Exception as exc:
            logger.warning("abnumber failed (%s); falling back to regex heuristic.", exc)
    return _annotate_regex_heuristic(sequence, chain_type)


def main() -> None:
    parser = argparse.ArgumentParser(description="Antibody Fv annotator (abnumber or regex heuristic)")
    parser.add_argument("--seq", "-s", required=True, help="Antibody Fv amino-acid sequence")
    parser.add_argument("--chain", "-c", choices=["Heavy", "Light"], help="Optional chain type")
    args = parser.parse_args()
    print(json.dumps(annotate_variable_domain_imgt(args.seq, chain_type=args.chain), indent=2))


if __name__ == "__main__":
    main()
