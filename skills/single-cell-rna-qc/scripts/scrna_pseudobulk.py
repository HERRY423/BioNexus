#!/usr/bin/env python3
"""Aggregate counts by sample × group for proper condition DE.

This is the supported path instead of publishing rank_genes_groups p-values.
Downstream: pydeseq2 / DESeq2, not this plugin.
"""

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


def pseudobulk_counts(adata, *, by: list[str], layer: str = "counts"):
    require("scanpy", for_method="pseudobulk_counts")
    import numpy as np
    import pandas as pd
    from scipy import sparse

    missing = [k for k in by if k not in adata.obs]
    if missing:
        raise ValueError(f"Missing obs columns for pseudobulk: {missing}")
    if layer in adata.layers:
        matrix = adata.layers[layer]
    else:
        matrix = adata.X
    if sparse.issparse(matrix):
        frame = pd.DataFrame.sparse.from_spmatrix(matrix, index=adata.obs_names, columns=adata.var_names)
        frame = frame.sparse.to_dense()
    else:
        frame = pd.DataFrame(np.asarray(matrix), index=adata.obs_names, columns=adata.var_names)
    keys = adata.obs[by].astype(str)
    grouped = frame.groupby([keys[c] for c in by], sort=True).sum()
    grouped.index = grouped.index.set_names(by)
    design = grouped.index.to_frame(index=False)
    sample_ids = ["__".join(map(str, row)) for row in design.to_numpy()]
    design.insert(0, "sample_id", sample_ids)
    grouped.index = pd.Index(sample_ids, name="sample_id")
    contract = attach_meta(
        {
            "by": by,
            "layer": layer if layer in adata.layers else "X",
            "n_pseudobulk_samples": int(grouped.shape[0]),
            "n_genes": int(grouped.shape[1]),
            "design_columns": list(design.columns),
            "next": "Export counts + design.tsv and run pydeseq2/DESeq2. This is not a DE test.",
        },
        method="sum_counts_by_obs_keys",
        backend="pandas",
        evidence_grade=GRADE_A,
        limitations=["Aggregation only. No size-factor, GLM, or p-values."],
    )
    return grouped, design, contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Pseudobulk count aggregation")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True, help="Output counts CSV")
    parser.add_argument("--by", nargs="+", required=True, help="obs columns, e.g. sample leiden")
    parser.add_argument("--layer", default="counts")
    parser.add_argument("--design", default=None, help="Design TSV path (default: <output>_design.tsv)")
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    table, design, contract = pseudobulk_counts(adata, by=args.by, layer=args.layer)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out)
    design_path = Path(args.design) if args.design else out.with_name(out.stem + "_design.tsv")
    design.to_csv(design_path, sep="\t", index=False)
    contract["design_path"] = str(design_path)
    print(json.dumps(contract, indent=2))


if __name__ == "__main__":
    main()
