#!/usr/bin/env python3
"""pydeseq2 on a pseudobulk counts table + design TSV. Refuses if pydeseq2 is missing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.backends import require
from bionexus.contracts import GRADE_A, attach_meta


def run_pydeseq2(
    counts,
    design,
    *,
    condition: str,
    reference: str | None = None,
    contrast_level: str | None = None,
):
    require("pydeseq2", for_method="run_pydeseq2")
    import numpy as np
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    counts = counts.copy()
    design = design.copy()
    if "sample_id" in design.columns:
        design = design.set_index("sample_id")
    if condition not in design.columns:
        raise ValueError(f"condition '{condition}' not in design columns {list(design.columns)}")
    counts.index = counts.index.astype(str)
    design.index = design.index.astype(str)
    shared = counts.index.intersection(design.index)
    if len(shared) < 4:
        raise ValueError(f"Need >=4 shared sample ids for pydeseq2, got {len(shared)}")
    counts = counts.loc[shared]
    design = design.loc[shared]
    if not np.issubdtype(counts.values.dtype, np.number):
        raise ValueError("counts must be numeric")
    counts = counts.round().astype(int)
    levels = list(design[condition].astype(str).unique())
    if len(levels) < 2:
        raise ValueError(f"condition '{condition}' has <2 levels")
    ref = reference or levels[0]
    alt = contrast_level or next(lv for lv in levels if lv != ref)
    try:
        dds = DeseqDataSet(counts=counts, metadata=design, design=f"~{condition}", refit_cooks=True)
    except TypeError:
        dds = DeseqDataSet(counts=counts, metadata=design, design_factors=condition, refit_cooks=True)
    dds.deseq2()
    stats = DeseqStats(dds, contrast=[condition, alt, ref])
    stats.summary()
    table = stats.results_df.reset_index().rename(columns={"index": "gene"})
    return table, attach_meta(
        {
            "n_samples": int(counts.shape[0]),
            "n_genes": int(counts.shape[1]),
            "condition": condition,
            "contrast": [condition, alt, ref],
            "n_tested": int(len(table)),
        },
        method="pydeseq2.DeseqStats",
        backend="pydeseq2",
        evidence_grade=GRADE_A,
        limitations=["Wald tests on aggregated counts. This is not DESeq2-in-R and not rank_genes_groups."],
    )


def _read_table(path: Path):
    import pandas as pd

    if path.suffix.lower() == ".tsv":
        return pd.read_csv(path, sep="\t", index_col=0)
    return pd.read_csv(path, index_col=0)


def main() -> None:
    parser = argparse.ArgumentParser(description="pydeseq2 on pseudobulk counts")
    parser.add_argument("counts", help="Counts CSV/TSV (samples x genes)")
    parser.add_argument("--design", required=True, help="Design TSV/CSV with the same sample index")
    parser.add_argument("--condition", required=True, help="Design column to test")
    parser.add_argument("--reference", default=None)
    parser.add_argument("--contrast-level", default=None)
    parser.add_argument("-o", "--output", required=True, help="DE results CSV")
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(skip=args.skip_doctor)
    counts = _read_table(Path(args.counts))
    design = _read_table(Path(args.design))
    table, contract = run_pydeseq2(
        counts,
        design,
        condition=args.condition,
        reference=args.reference,
        contrast_level=args.contrast_level,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out, index=False)
    print(json.dumps(contract, indent=2, default=str))


if __name__ == "__main__":
    main()
