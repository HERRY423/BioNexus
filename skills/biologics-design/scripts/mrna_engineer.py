#!/usr/bin/env python3
"""Codon rewrite for human-preferred codons.

CAI is 1.0 by construction against this one-codon-per-AA table.
MFE is ViennaRNA if installed; otherwise a pair-count heuristic, not RNAfold.
"""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any, Dict, List

from _common import GRADE_A, GRADE_C, attach_meta, is_available

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("mRNAEngineer")

HUMAN_OPTIMAL_CODONS = {
    "A": "GCC",
    "C": "TGC",
    "D": "GAC",
    "E": "GAG",
    "F": "TTC",
    "G": "GGC",
    "H": "CAC",
    "I": "ATC",
    "K": "AAG",
    "L": "CTG",
    "M": "ATG",
    "N": "AAC",
    "P": "CCC",
    "Q": "CAG",
    "R": "CGG",
    "S": "AGC",
    "T": "ACC",
    "V": "GTG",
    "W": "TGG",
    "Y": "TAC",
    "*": "TGA",
}


def calculate_gc_content(dna_or_rna_seq: str) -> float:
    seq = dna_or_rna_seq.upper().replace("U", "T")
    if not seq:
        return 0.0
    return round((seq.count("G") + seq.count("C")) / len(seq) * 100.0, 2)


def _viennarna_mfe(rna_seq: str) -> Dict[str, Any]:
    import RNA  # type: ignore

    structure, mfe = RNA.fold(rna_seq)
    return {
        "estimated_folding_mfe_kcal_mol": round(float(mfe), 2),
        "mfe_structure": structure,
        "mfe_method": "viennarna_rnafold",
        "mfe_grade": GRADE_A,
    }


def _paircount_mfe_heuristic(rna_seq: str) -> Dict[str, Any]:
    gc_count = rna_seq.count("G") + rna_seq.count("C")
    au_count = rna_seq.count("A") + rna_seq.count("U")
    est = -(int(gc_count * 0.40) * 3.0 + int(au_count * 0.35) * 1.8)
    return {
        "estimated_folding_mfe_kcal_mol": round(float(est), 1),
        "mfe_structure": None,
        "mfe_method": "pair_count_heuristic",
        "mfe_grade": GRADE_C,
    }


def optimize_mrna_sequence(protein_sequence: str) -> Dict[str, Any]:
    prot = protein_sequence.strip().upper()
    unknown = [aa for aa in prot if aa not in HUMAN_OPTIMAL_CODONS]
    if unknown:
        raise ValueError(f"Non-standard residues cannot be codon-optimized: {sorted(set(unknown))}")

    optimized_dna = "".join(HUMAN_OPTIMAL_CODONS[aa] for aa in prot)
    mrna_seq = optimized_dna.replace("T", "U")
    gc_pct = calculate_gc_content(optimized_dna)

    if is_available("viennarna"):
        try:
            mfe_block = _viennarna_mfe(mrna_seq)
        except Exception as exc:
            logger.warning("ViennaRNA failed (%s); using pair-count heuristic.", exc)
            mfe_block = _paircount_mfe_heuristic(mrna_seq)
    else:
        mfe_block = _paircount_mfe_heuristic(mrna_seq)

    motifs: List[str] = []
    if "UUUUU" in mrna_seq:
        motifs.append("Poly-U tract (>4 nt); possible polymerase slippage / termination.")

    payload = {
        "protein_length": len(prot),
        "mrna_length_nt": len(mrna_seq),
        "optimized_mrna_sequence": mrna_seq,
        "codon_table": "one_optimal_codon_per_aa",
        "sharp_li_cai": None,
        "cai_definition": "Not computed. All-optimal-codon rewrite is not Sharp & Li CAI.",
        "gc_content_percent": gc_pct,
        "gc_status": "In 48-62% window" if 48.0 <= gc_pct <= 62.0 else "Outside 48-62% window",
        "translation_efficiency_tier": "Not predicted; only codon table applied",
        "flagged_motifs": motifs,
        **mfe_block,
    }
    return attach_meta(
        payload,
        method="human_optimal_codon_table",
        backend="viennarna" if mfe_block["mfe_method"] == "viennarna_rnafold" else "local_codon_table",
        evidence_grade=mfe_block["mfe_grade"],
        limitations=[
            "Does not optimize MFE, codon pair bias, or cryptic splice sites.",
            "Pair-count MFE is not Nussinov DP and not RNAfold."
            if mfe_block["mfe_method"] != "viennarna_rnafold"
            else "MFE from ViennaRNA RNAfold.",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Human optimal-codon rewrite")
    parser.add_argument("--protein", "-p", required=True, help="Amino-acid sequence")
    args = parser.parse_args()
    print(json.dumps(optimize_mrna_sequence(args.protein), indent=2))


if __name__ == "__main__":
    main()
