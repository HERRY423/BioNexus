#!/usr/bin/env python3
"""Subset cells or genes and drop stale embeddings when requested."""

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

STALE_OBSM = ("X_pca", "X_umap", "X_tsne")


def subset_adata(
    adata,
    *,
    obs_key: str | None = None,
    keep_values: list[str] | None = None,
    genes: list[str] | None = None,
    clear_embeddings: bool = False,
):
    require("scanpy", for_method="subset_adata")
    n0, g0 = int(adata.n_obs), int(adata.n_vars)
    view = adata
    if obs_key:
        if obs_key not in view.obs:
            raise ValueError(f"obs key '{obs_key}' not found")
        wanted = set(str(v) for v in (keep_values or []))
        mask = view.obs[obs_key].astype(str).isin(wanted)
        view = view[mask].copy()
    if genes:
        present = [g for g in genes if g in view.var_names]
        if not present:
            raise ValueError("None of the requested genes are in var_names")
        view = view[:, present].copy()
    if clear_embeddings:
        for key in STALE_OBSM:
            if key in view.obsm:
                del view.obsm[key]
        for key in ("neighbors", "pca", "umap"):
            view.uns.pop(key, None)
    contract = attach_meta(
        {"n_obs_before": n0, "n_vars_before": g0, "n_obs": int(view.n_obs), "n_vars": int(view.n_vars)},
        method="anndata_subset",
        backend="anndata",
        evidence_grade=GRADE_A,
        limitations=["Clear embeddings after a non-trivial subset before re-clustering."],
    )
    view.uns["subset_contract"] = contract
    return view, contract


def main() -> None:
    parser = argparse.ArgumentParser(description="Subset AnnData")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--obs", dest="obs_key", default=None)
    parser.add_argument("--keep", nargs="*", default=None)
    parser.add_argument("--genes", nargs="*", default=None)
    parser.add_argument("--clear-embeddings", action="store_true")
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    view, contract = subset_adata(
        adata,
        obs_key=args.obs_key,
        keep_values=args.keep,
        genes=args.genes,
        clear_embeddings=args.clear_embeddings,
    )
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    view.write_h5ad(args.output)
    print(json.dumps(contract, indent=2))


if __name__ == "__main__":
    main()
