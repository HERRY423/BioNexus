#!/usr/bin/env python3
"""Exploratory cluster markers via scanpy.rank_genes_groups (Wilcoxon).

Not sample-level differential expression. For condition DE, pseudobulk first.
This plugin does not assign cell-type identity. Clusters stay numeric.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.backends import require
from bionexus.contracts import GRADE_B, attach_meta
from bionexus.provenance import sidecar


def find_cluster_markers(
    adata,
    *,
    groupby: str | None = None,
    n_genes: int = 20,
) -> tuple[Any, Dict[str, Any]]:
    require("scanpy", for_method="find_cluster_markers")
    import pandas as pd
    import scanpy as sc

    if groupby is None:
        groupby = "leiden" if "leiden" in adata.obs else "cluster"
    if groupby not in adata.obs:
        raise ValueError(f"No cluster key '{groupby}' in adata.obs. Run reduce/cluster first.")

    use_raw = adata.raw is not None
    sc.tl.rank_genes_groups(adata, groupby=groupby, method="wilcoxon", use_raw=use_raw)
    frames: List[Any] = []
    groups = list(adata.obs[groupby].astype(str).unique())
    for group in groups:
        frame = sc.get.rank_genes_groups_df(adata, group=group)
        frame.insert(0, "cluster", group)
        frames.append(frame.head(n_genes))
    table = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    contract = attach_meta(
        {
            "groupby": groupby,
            "n_groups": len(groups),
            "n_genes_per_group": n_genes,
            "next": "Use scrna_pseudobulk.py before condition DE; do not assign cell types",
        },
        method="scanpy.tl.rank_genes_groups_wilcoxon",
        backend="scanpy",
        evidence_grade=GRADE_B,
        limitations=[
            "Per-cell Wilcoxon inflates p-values; cells are not independent samples.",
            "Exploratory cluster markers only. Numeric clusters are not cell types.",
        ],
    )
    adata.uns["markers_contract"] = contract
    return table, contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Exploratory cluster markers")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True, help="Clustered .h5ad to update")
    parser.add_argument("--csv", help="Optional markers CSV")
    parser.add_argument("--groupby", default=None)
    parser.add_argument("--n-genes", type=int, default=20)
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    table, contract = find_cluster_markers(adata, groupby=args.groupby, n_genes=args.n_genes)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(args.output)
    if args.csv:
        table.to_csv(args.csv, index=False)
    sidecar(
        activity_name="scrna_markers",
        input_files=[args.input],
        output_files=[args.output],
        method=contract["method"],
        backend="scanpy",
    )
    print(json.dumps({"contract": contract, "n_marker_rows": int(len(table))}, indent=2, default=str))


if __name__ == "__main__":
    main()
