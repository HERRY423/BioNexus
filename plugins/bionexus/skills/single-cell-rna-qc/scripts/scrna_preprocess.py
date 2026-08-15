#!/usr/bin/env python3
"""Normalize, log1p, and mark HVGs. Keeps raw counts in .layers['counts']."""

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
from bionexus.provenance import sidecar


def preprocess_scrna(
    adata,
    *,
    n_top_genes: int = 2000,
    target_sum: float = 1e4,
):
    """scanpy normalize_total + log1p + highly_variable_genes. Does not subset."""
    require("scanpy", for_method="preprocess_scrna")
    import scanpy as sc

    if "counts" not in adata.layers:
        adata.layers["counts"] = adata.X.copy()
    sc.pp.normalize_total(adata, target_sum=target_sum)
    sc.pp.log1p(adata)
    sc.pp.highly_variable_genes(adata, n_top_genes=n_top_genes, subset=False)
    n_hvg = int(adata.var["highly_variable"].sum()) if "highly_variable" in adata.var else 0
    contract = attach_meta(
        {"n_cells": int(adata.n_obs), "n_genes": int(adata.n_vars), "n_hvg": n_hvg, "target_sum": target_sum},
        method="scanpy.pp.normalize_total+log1p+highly_variable_genes",
        backend="scanpy",
        evidence_grade=GRADE_A,
        limitations=["HVGs are marked, not subset. Condition DE still needs pseudobulk."],
    )
    adata.uns["preprocess_contract"] = contract
    return adata, contract


def main() -> None:
    parser = argparse.ArgumentParser(description="scRNA preprocess (scanpy)")
    parser.add_argument("input", help="Filtered .h5ad")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--n-top-genes", type=int, default=2000)
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    adata, contract = preprocess_scrna(adata, n_top_genes=args.n_top_genes)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(args.output)
    sidecar_path = Path(args.output).with_suffix(".provenance.json")
    sidecar_path.write_text(
        json.dumps(
            sidecar(
                activity_name="scrna_preprocess",
                input_files=[args.input],
                output_files=[args.output],
                method=contract["method"],
                backend="scanpy",
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(contract, indent=2))


if __name__ == "__main__":
    main()
