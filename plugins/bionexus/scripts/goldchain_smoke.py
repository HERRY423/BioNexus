#!/usr/bin/env python3
"""Fixture-first gold-chain smoke. Optional public pbmc3k inspect (network)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "skills" / "single-cell-rna-qc" / "scripts"))
sys.path.insert(0, str(ROOT / "skills" / "spatial-transcriptomics" / "scripts"))


def smoke_scrna(path: Path) -> dict:
    import scanpy as sc
    from scrna_inspect import inspect_adata
    from scrna_pipeline import run_scrna_gold_chain

    adata = sc.read_h5ad(path)
    inspect = inspect_adata(adata)
    out, markers, summary = run_scrna_gold_chain(
        adata, run_qc=False, n_top_genes=min(80, adata.n_vars), resolution=0.8, n_marker_genes=5
    )
    return {
        "inspect_n_obs": inspect["n_obs"],
        "n_clusters": summary.get("n_clusters"),
        "method": summary["method"],
        "n_marker_rows": int(len(markers)),
        "source": str(path),
    }


def smoke_spatial(path: Path) -> dict:
    import scanpy as sc
    from spatial_pipeline import run_spatial_gold_chain

    adata = sc.read_h5ad(path)
    out, svg, summary = run_spatial_gold_chain(adata, cluster=False, top_n=5)
    return {
        "method": summary["method"],
        "graph": summary["graph"],
        "n_svg": int(len(svg)),
        "source": str(path),
    }


def try_pbmc3k() -> dict:
    import scanpy as sc
    from scrna_inspect import inspect_adata

    adata = sc.datasets.pbmc3k()
    if adata.n_obs > 400:
        adata = adata[list(adata.obs_names[:400])].copy()
    return inspect_adata(adata)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pbmc3k", action="store_true")
    args = parser.parse_args()
    report: dict = {}
    scrna = ROOT / "tests" / "fixtures" / "tiny_scrna.h5ad"
    spatial = ROOT / "tests" / "fixtures" / "tiny_spatial.h5ad"
    if scrna.is_file():
        report["scrna"] = smoke_scrna(scrna)
    if spatial.is_file():
        report["spatial"] = smoke_spatial(spatial)
    if args.pbmc3k:
        try:
            report["pbmc3k"] = try_pbmc3k()
        except Exception as exc:
            report["pbmc3k"] = {"skipped": str(exc)}
    print(json.dumps(report, indent=2, default=str))
    if report.get("scrna", {}).get("method") != "scanpy_gold_chain":
        sys.exit(1)
    if spatial.is_file() and report.get("spatial", {}).get("method") != "squidpy_spatial_gold_chain":
        sys.exit(1)


if __name__ == "__main__":
    main()
