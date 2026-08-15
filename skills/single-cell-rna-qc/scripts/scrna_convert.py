#!/usr/bin/env python3
"""Load 10x mtx/h5, CSV, or h5ad and write a counts .h5ad."""

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


def convert_to_h5ad(source: str, dest: str):
    require("scanpy", for_method="convert_to_h5ad")
    import scanpy as sc

    path = Path(source)
    if path.suffix.lower() in {".rds", ".rdata"}:
        raise ValueError(
            "Seurat/SingleCellExperiment .rds is not converted here. "
            "In R: library(zellkonverter); writeH5AD(sce, 'out.h5ad')"
        )
    method = "scanpy.read_h5ad"
    if path.is_dir():
        adata = sc.read_10x_mtx(str(path))
        method = "scanpy.read_10x_mtx"
    elif path.suffix.lower() == ".h5" and path.suffixes[-1].lower() != ".h5ad":
        adata = sc.read_10x_h5(str(path))
        method = "scanpy.read_10x_h5"
    elif path.suffix.lower() in {".csv", ".tsv"}:
        delim = "\t" if path.suffix.lower() == ".tsv" else ","
        adata = sc.read_csv(str(path), delimiter=delim)
        method = "scanpy.read_csv"
    elif str(path).endswith(".h5ad"):
        adata = sc.read_h5ad(str(path))
        method = "scanpy.read_h5ad"
    else:
        raise ValueError(f"Unsupported input: {source}. Use 10x dir, .h5, .h5ad, .csv, or .tsv.")

    if "counts" not in adata.layers:
        adata.layers["counts"] = adata.X.copy()
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(dest)
    return attach_meta(
        {"n_obs": int(adata.n_obs), "n_vars": int(adata.n_vars), "output": dest},
        method=method,
        backend="scanpy",
        evidence_grade=GRADE_A,
        limitations=["Does not convert Seurat .rds; use R/zellkonverter first."],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert counts to .h5ad")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    print(json.dumps(convert_to_h5ad(args.input, args.output), indent=2))


if __name__ == "__main__":
    main()
