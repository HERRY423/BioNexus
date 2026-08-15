#!/usr/bin/env python3
"""Summarize a SpatialData/.h5ad object before the squidpy gold chain."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from _common import attach_meta
from spatial_io import load_spatial_anndata, resolve_spatial_key, spatial_load_contract

from bionexus.contracts import GRADE_A


def inspect_spatial(adata, *, spatial_key: str | None = None) -> dict:
    import numpy as np

    key = resolve_spatial_key(adata, preferred=spatial_key or "spatial")
    coords = np.asarray(adata.obsm[key], dtype=float)
    platform = "unknown"
    if "in_tissue" in adata.obs:
        platform = "visium_like"
    elif "cell_id" in adata.obs or coords.shape[0] > 5000:
        platform = "cell_resolution_or_large"
    next_actions = [
        "spatial_pipeline.py (squidpy knn neighbors + Moran SVGs)",
        "Do not call fused-graph / NNLS helpers Cell2location or BayesSpace",
    ]
    return attach_meta(
        {
            "n_obs": int(adata.n_obs),
            "n_vars": int(adata.n_vars),
            "spatial_key": key,
            "coord_dim": int(coords.shape[1]) if coords.ndim == 2 else 0,
            "coord_min": coords.min(axis=0).tolist() if coords.size else [],
            "coord_max": coords.max(axis=0).tolist() if coords.size else [],
            "obs_columns": list(map(str, adata.obs.columns)),
            "layers": list(getattr(adata, "layers", {}).keys()),
            "embeddings": list(getattr(adata, "obsm", {}).keys()),
            "platform_guess": platform,
            "has_counts_layer": "counts" in adata.layers,
            "allowed_next_actions": next_actions,
        },
        method="spatial_inspect",
        backend="anndata",
        evidence_grade=GRADE_A,
        limitations=["Platform guess is a filename/obs heuristic, not a vendor parser."],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect spatial AnnData / SpatialData")
    parser.add_argument("input")
    parser.add_argument("--spatial-key", default="spatial")
    parser.add_argument("--table", default=None, help="SpatialData table name (required if multiple tables)")
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_spatial=True, skip=args.skip_doctor)
    adata = load_spatial_anndata(args.input, table_key=args.table)
    report = inspect_spatial(adata, spatial_key=args.spatial_key)
    report["load"] = spatial_load_contract(args.input, adata, report["spatial_key"])
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
