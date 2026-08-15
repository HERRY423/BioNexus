#!/usr/bin/env python3
"""Summarize an unknown AnnData / 10x file before the gold chain."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.contracts import GRADE_A, attach_meta


def _matrix_stats(matrix) -> dict:
    import numpy as np
    from scipy import sparse

    if sparse.issparse(matrix):
        sample = matrix.data if matrix.nnz else np.array([0.0])
        max_val = float(sample.max()) if sample.size else 0.0
        min_val = float(sample.min()) if sample.size else 0.0
        mean_nz = float(sample.mean()) if sample.size else 0.0
        integerish = bool(np.allclose(sample[: min(5000, sample.size)], np.round(sample[: min(5000, sample.size)])))
    else:
        arr = np.asarray(matrix, dtype=float)
        max_val = float(arr.max()) if arr.size else 0.0
        min_val = float(arr.min()) if arr.size else 0.0
        mean_nz = float(arr.mean()) if arr.size else 0.0
        integerish = bool(np.allclose(arr, np.round(arr)))
    likely_log = bool(max_val < 20.0 and min_val >= 0.0 and not integerish)
    return {
        "max": max_val,
        "min": min_val,
        "mean_nonzero_or_mean": mean_nz,
        "integerish": integerish,
        "likely_log_transformed": likely_log,
    }


def inspect_adata(adata) -> dict:
    embeddings = list(getattr(adata, "obsm", {}).keys())
    layers = list(getattr(adata, "layers", {}).keys())
    cluster_keys = [c for c in ("leiden", "leiden_0.5", "leiden_0.8", "cluster", "louvain") if c in adata.obs]
    species = "unknown"
    names = " ".join(map(str, list(adata.var_names[:50])))
    if any(str(n).startswith("MT-") or str(n).startswith("ENSG") for n in adata.var_names.astype(str)[:80]):
        species = "human"
    elif any(str(n).startswith("mt-") or str(n).startswith("ENSMUS") for n in adata.var_names.astype(str)[:80]):
        species = "mouse"
    x_stats = _matrix_stats(adata.X)
    batch_keys = [c for c in ("batch", "sample", "donor", "orig.ident", "library_id", "chemistry") if c in adata.obs]
    lib_stats = None
    try:
        import numpy as np
        from scipy import sparse

        matrix = adata.X
        if sparse.issparse(matrix):
            lib = np.asarray(matrix.sum(axis=1)).ravel()
        else:
            lib = np.asarray(matrix, dtype=float).sum(axis=1)
        if lib.size:
            lib_stats = {
                "median": float(np.median(lib)),
                "p05": float(np.percentile(lib, 5)),
                "p95": float(np.percentile(lib, 95)),
                "min": float(lib.min()),
                "max": float(lib.max()),
            }
    except Exception:
        lib_stats = None
    next_actions = []
    if "counts" not in layers and x_stats["likely_log_transformed"]:
        next_actions.append("X looks log-like and counts layer is missing; do not train scVI on X")
    elif "counts" not in layers:
        next_actions.append("scrna_pipeline.py (will copy X into layers['counts'])")
    else:
        next_actions.append("scrna_pipeline.py if this is raw/filtered counts")
    if cluster_keys:
        next_actions.append("scrna_pseudobulk.py if comparing conditions")
    if batch_keys:
        next_actions.append("scrna_integrate.py or scvi-tools if those keys are technical batches")
    report = attach_meta(
        {
            "n_obs": int(adata.n_obs),
            "n_vars": int(adata.n_vars),
            "obs_columns": list(map(str, adata.obs.columns)),
            "var_columns": list(map(str, adata.var.columns)),
            "layers": layers,
            "embeddings": embeddings,
            "cluster_keys": cluster_keys,
            "batch_key_candidates": batch_keys,
            "library_size": lib_stats,
            "species_guess": species,
            "has_counts_layer": "counts" in layers,
            "x_stats": x_stats,
            "sample_var_names": list(map(str, adata.var_names[:8])),
            "allowed_next_actions": next_actions,
            "name_preview": names[:200],
        },
        method="anndata_inspect",
        backend="anndata",
        evidence_grade=GRADE_A,
        limitations=["Species guess and log detection are heuristics."],
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect scRNA file")
    parser.add_argument("input")
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    import scanpy as sc

    path = args.input
    if path.endswith(".h5") and not path.endswith(".h5ad"):
        adata = sc.read_10x_h5(path)
    else:
        adata = sc.read_h5ad(path)
    print(json.dumps(inspect_adata(adata), indent=2, default=str))


if __name__ == "__main__":
    main()
