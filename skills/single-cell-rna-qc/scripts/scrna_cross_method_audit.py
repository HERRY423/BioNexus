#!/usr/bin/env python3
"""Cross-method concordance audit for single-cell results (EvidenceCard dimension 6).

Compares two ranked result tables produced by *independent* methods — typically the
scanpy Wilcoxon marker ranking vs the PyDESeq2 pseudobulk DE ranking — and grades
their agreement (Spearman rho + top-k Jaccard) so EvidenceCard dimension 6 can move
from UNTESTED to an audited grade. This audit quantifies statistical agreement only;
it cannot establish which method is biologically correct.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.validation import _read_scored_table, rank_concordance


def _maybe_negate(scored: dict, lower_is_better: bool) -> dict:
    """Negate scores when a table ranks by 'smaller is better' (e.g. pvalues)."""
    return {k: -v for k, v in scored.items()} if lower_is_better else scored


def audit_marker_methods(
    primary_table: str | Path,
    orthogonal_table: str | Path,
    *,
    top_k: int = 20,
    primary_lower_is_better: bool = False,
    orthogonal_lower_is_better: bool = False,
) -> dict:
    """
    Run the rank-concordance audit over two single-cell result tables.

    ``*_lower_is_better`` must be set for tables ranked by decreasing significance,
    such as pvalue/padj columns (the marker ``scores`` column is higher-is-better).
    """
    payload = rank_concordance(
        _maybe_negate(_read_scored_table(primary_table), primary_lower_is_better),
        _maybe_negate(_read_scored_table(orthogonal_table), orthogonal_lower_is_better),
        top_k=top_k,
    )
    if not payload.get("refused"):
        payload["inputs"] = {
            "primary": str(primary_table),
            "orthogonal": str(orthogonal_table),
            "primary_lower_is_better": primary_lower_is_better,
            "orthogonal_lower_is_better": orthogonal_lower_is_better,
        }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Wilcoxon vs pseudobulk DE rank concordance audit")
    parser.add_argument("--primary", required=True, help="Primary ranked table (e.g. scanpy markers.csv)")
    parser.add_argument("--orthogonal", required=True, help="Orthogonal ranked table (e.g. pydeseq2 results.csv)")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument(
        "--primary-lower-is-better",
        action="store_true",
        help="Primary table ranks by decreasing value (e.g. pvalue/padj columns)",
    )
    parser.add_argument(
        "--orthogonal-lower-is-better",
        action="store_true",
        help="Orthogonal table ranks by decreasing value (e.g. pvalue/padj columns)",
    )
    parser.add_argument("-o", "--output", default=None, help="Optional path to write the audit JSON")
    args = parser.parse_args()

    payload = audit_marker_methods(
        args.primary,
        args.orthogonal,
        top_k=args.top_k,
        primary_lower_is_better=args.primary_lower_is_better,
        orthogonal_lower_is_better=args.orthogonal_lower_is_better,
    )
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))
    sys.exit(2 if payload.get("refused") else (1 if payload.get("audit", {}).get("grade") == "CONFLICTED" else 0))


if __name__ == "__main__":
    main()
