#!/usr/bin/env python3
"""Variant substitution scores.

Tries ESM-2 masked-marginal ΔLLR when transformers/fair-esm can load weights.
Otherwise returns a BLOSUM62 score under its own name. BLOSUM is never mapped
to ACMG PP3/BP4.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from typing import Any, Dict, Optional

import numpy as np
from _common import GRADE_A, GRADE_C, attach_meta, is_available

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("PLMFitnessScorer")

AMINO_ACIDS = "ARNDCQEGHILKMFPSTWYV"
AA_TO_IDX = {aa: i for i, aa in enumerate(AMINO_ACIDS)}
BLOSUM62_RAW = np.array(
    [
        [4, -1, -2, -2, 0, -1, -1, 0, -2, -1, -1, -1, -1, -2, -1, 1, 0, -3, -2, 0],
        [-1, 5, 0, -2, -3, 1, 0, -2, 0, -3, -2, 2, -1, -3, -2, -1, -1, -3, -2, -3],
        [-2, 0, 6, 1, -3, 0, 0, 0, 1, -3, -3, 0, -2, -3, -2, 1, 0, -4, -2, -3],
        [-2, -2, 1, 6, -3, 0, 2, -1, -1, -3, -4, -1, -3, -3, -1, 0, -1, -4, -3, -3],
        [0, -3, -3, -3, 9, -3, -4, -3, -3, -1, -1, -3, -1, -2, -3, -1, -1, -2, -2, -1],
        [-1, 1, 0, 0, -3, 5, 2, -2, 0, -3, -2, 1, 0, -3, -1, 0, -1, -2, -1, -2],
        [-1, 0, 0, 2, -4, 2, 5, -2, 0, -3, -3, 1, -2, -3, -1, 0, -1, -3, -2, -2],
        [0, -2, 0, -1, -3, -2, -2, 6, -2, -4, -4, -2, -3, -3, -2, 0, -2, -2, -3, -3],
        [-2, 0, 1, -1, -3, 0, 0, -2, 8, -3, -3, -1, -2, -1, -2, -1, -2, -2, 2, -3],
        [-1, -3, -3, -3, -1, -3, -3, -4, -3, 4, 2, -3, 1, 0, -3, -2, -1, -3, -1, 3],
        [-1, -2, -3, -4, -1, -2, -3, -4, -3, 2, 4, -2, 2, 0, -3, -2, -1, -2, -1, 1],
        [-1, 2, 0, -1, -3, 1, 1, -2, -1, -3, -2, 5, -1, -3, -1, 0, -1, -3, -2, -2],
        [-1, -1, -2, -3, -1, 0, -2, -3, -2, 1, 2, -1, 5, 0, -2, -1, -1, -1, -1, 1],
        [-2, -3, -3, -3, -2, -3, -3, -3, -1, 0, 0, -3, 0, 6, -4, -2, -2, 1, 3, -1],
        [-1, -2, -2, -1, -3, -1, -1, -2, -2, -3, -3, -1, -2, -4, 7, -1, -1, -4, -3, -2],
        [1, -1, 1, 0, -1, 0, 0, 0, -1, -2, -2, 0, -1, -2, -1, 4, 1, -3, -2, -2],
        [0, -1, 0, -1, -1, -1, -1, -2, -2, -1, -1, -1, -1, -2, -1, 1, 5, -2, -2, 0],
        [-3, -3, -4, -4, -2, -2, -3, -2, -2, -3, -2, -3, -1, 1, -4, -3, -2, 11, 2, -3],
        [-2, -2, -2, -3, -2, -1, -2, -3, 2, -1, -1, -2, -1, 3, -3, -2, -2, 2, 7, -1],
        [0, -3, -3, -3, -1, -2, -2, -3, -3, 3, 1, -2, 1, -1, -2, -2, 0, -3, -1, 4],
    ]
)
AA3 = {
    "ALA": "A",
    "CYS": "C",
    "ASP": "D",
    "GLU": "E",
    "PHE": "F",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LYS": "K",
    "LEU": "L",
    "MET": "M",
    "ASN": "N",
    "PRO": "P",
    "GLN": "Q",
    "ARG": "R",
    "SER": "S",
    "THR": "T",
    "VAL": "V",
    "TRP": "W",
    "TYR": "Y",
}


def parse_mutation(wildtype_seq: str, mutation_str: str) -> Dict[str, Any]:
    wt_seq = wildtype_seq.strip().upper()
    mut_clean = mutation_str.upper().replace("P.", "")
    for three, one in AA3.items():
        mut_clean = mut_clean.replace(three, one)
    match = re.search(r"([A-Z])([0-9]+)([A-Z*])", mut_clean)
    if not match:
        raise ValueError(f"Could not parse single-point mutation from '{mutation_str}'")
    wt_aa, pos, mut_aa = match.group(1), int(match.group(2)), match.group(3)
    if pos < 1 or pos > len(wt_seq):
        raise ValueError(f"Position {pos} out of bounds for length {len(wt_seq)}")
    actual_wt = wt_seq[pos - 1]
    if actual_wt != wt_aa:
        logger.warning("Position %s is %s, mutation specified %s; using sequence residue.", pos, actual_wt, wt_aa)
        wt_aa = actual_wt
    return {"wt_seq": wt_seq, "wt_aa": wt_aa, "pos": pos, "mut_aa": mut_aa}


def _blosum_score(wt_aa: str, mut_aa: str, conservation_weight: float = 1.2) -> float:
    if mut_aa == "*":
        return -10.5
    if wt_aa not in AA_TO_IDX or mut_aa not in AA_TO_IDX:
        return -3.0
    i_wt, i_mut = AA_TO_IDX[wt_aa], AA_TO_IDX[mut_aa]
    return float((BLOSUM62_RAW[i_wt, i_mut] - BLOSUM62_RAW[i_wt, i_wt]) * 0.75 * conservation_weight)


def _esm_delta_llr(wt_seq: str, pos: int, wt_aa: str, mut_aa: str) -> Optional[float]:
    """Masked-marginal log P(mut) - log P(wt) at 1-based pos. None if model cannot load."""
    if mut_aa == "*" or os.environ.get("BIONEXUS_ALLOW_ESM", "").strip() not in {"1", "true", "TRUE"}:
        # Default off so unit tests / CI never download multi-hundred-MB weights.
        return None
    try:
        import torch
        from transformers import AutoModelForMaskedLM, AutoTokenizer
    except Exception:
        return None

    model_id = os.environ.get("BIONEXUS_ESM_MODEL", "facebook/esm2_t6_8M_UR50D")
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForMaskedLM.from_pretrained(model_id)
        model.eval()
        masked = list(wt_seq)
        masked[pos - 1] = tokenizer.mask_token
        encoded = tokenizer("".join(masked), return_tensors="pt")
        with torch.no_grad():
            logits = model(**encoded).logits[0]
        mask_index = (encoded.input_ids[0] == tokenizer.mask_token_id).nonzero(as_tuple=True)[0]
        if len(mask_index) == 0:
            return None
        log_probs = torch.log_softmax(logits[int(mask_index[0])], dim=-1)
        wt_id = tokenizer.convert_tokens_to_ids(wt_aa)
        mut_id = tokenizer.convert_tokens_to_ids(mut_aa)
        if wt_id is None or mut_id is None:
            return None
        return float(log_probs[mut_id] - log_probs[wt_id])
    except Exception as exc:
        logger.warning("ESM backend unavailable (%s).", exc)
        return None


def score_variant_delta_llr(
    wildtype_seq: str,
    mutation_str: str,
    conservation_weight: float = 1.2,
) -> Dict[str, Any]:
    parsed = parse_mutation(wildtype_seq, mutation_str)
    wt_aa, pos, mut_aa = parsed["wt_aa"], parsed["pos"], parsed["mut_aa"]

    esm_score = None
    if is_available("esm") or is_available("fair_esm"):
        esm_score = _esm_delta_llr(parsed["wt_seq"], pos, wt_aa, mut_aa)

    if esm_score is not None:
        score = esm_score
        method = "esm2_masked_marginal_llr"
        backend = "transformers"
        grade = GRADE_A
        score_kind = "esm2_masked_marginal_llr"
        acmg = "not_mapped; use a calibrated predictor (AlphaMissense/REVEL) for PP3/BP4"
        limitations = ["ESM-2 masked-marginal ΔLLR. Not ClinGen-calibrated for PP3/BP4."]
    else:
        score = _blosum_score(wt_aa, mut_aa, conservation_weight)
        method = "blosum62_substitution"
        backend = "blosum62"
        grade = GRADE_C
        score_kind = "blosum62_delta"
        acmg = "abstain"
        limitations = [
            "BLOSUM62 is position-independent and is not a protein language model.",
            "Do not use this score as ACMG PP3/BP4.",
        ]

    if score >= -1.5:
        effect_class, tier = "Neutral", "More similar substitution in BLOSUM/ESM units"
    elif score >= -4.5:
        effect_class, tier = "Moderate", "Intermediate substitution score"
    else:
        effect_class, tier = "Deleterious", "Strongly dissimilar substitution score"

    payload = {
        "mutation": f"{wt_aa}{pos}{mut_aa}",
        "wildtype_aa": wt_aa,
        "position": pos,
        "mutant_aa": mut_aa,
        "score": round(float(score), 3),
        "score_kind": score_kind,
        "delta_llr": round(float(score), 3) if score_kind.startswith("esm2") else None,
        "predicted_effect": effect_class,
        "fitness_tier": tier,
        "acmg_computational_evidence": acmg,
    }
    return attach_meta(
        payload,
        method=method,
        backend=backend,
        evidence_grade=grade,
        limitations=limitations,
        abstain=(method == "blosum62_substitution"),
        abstain_reason="No ESM weights loaded; BLOSUM62 is not ACMG computational evidence."
        if method == "blosum62_substitution"
        else None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Substitution score (ESM-2 or BLOSUM62)")
    parser.add_argument("--sequence", "-s", required=True)
    parser.add_argument("--mutation", "-m", required=True)
    args = parser.parse_args()
    print(json.dumps(score_variant_delta_llr(args.sequence, args.mutation), indent=2))


if __name__ == "__main__":
    main()
