#!/usr/bin/env python3
"""scverse gold chain: optional MAD QC → preprocess → PCA/UMAP/cluster → markers.

.h5ad in, .h5ad + provenance sidecar + markers CSV out.
Does not assign cell-type labels. Clusters stay numeric.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scrna_markers import find_cluster_markers
from scrna_preprocess import preprocess_scrna
from scrna_reduce_cluster import reduce_and_cluster

from bio_research.backends import require
from bio_research.contracts import attach_meta
from bio_research.provenance import sidecar


def run_scrna_gold_chain(
    adata,
    *,
    run_qc: bool = True,
    n_top_genes: int = 2000,
    resolution: float = 0.5,
    extra_resolutions: list[float] | None = None,
    n_marker_genes: int = 20,
):
    require("scanpy", for_method="run_scrna_gold_chain")
    steps = []
    if run_qc:
        from qc_core import (
            apply_hard_threshold,
            calculate_qc_metrics_fast,
            detect_outliers_mad,
            filter_cells,
            filter_genes,
        )

        n_before = int(adata.n_obs)
        calculate_qc_metrics_fast(adata)
        keep = ~detect_outliers_mad(adata, "total_counts", n_mads=5, verbose=False)
        keep = keep & ~detect_outliers_mad(adata, "n_genes_by_counts", n_mads=5, verbose=False)
        if "pct_counts_mt" in adata.obs:
            keep = keep & ~apply_hard_threshold(adata, "pct_counts_mt", 8.0, operator=">", verbose=False)
        adata = filter_cells(adata, keep)
        filter_genes(adata, min_cells=3, inplace=True)
        steps.append({"step": "qc", "n_before": n_before, "n_after": int(adata.n_obs)})

    adata, pre_c = preprocess_scrna(adata, n_top_genes=n_top_genes)
    steps.append(pre_c)
    adata, cl_c = reduce_and_cluster(
        adata, resolution=resolution, extra_resolutions=extra_resolutions or [0.3, 0.8]
    )
    steps.append(cl_c)
    markers, mk_c = find_cluster_markers(adata, n_genes=n_marker_genes)
    steps.append(mk_c)
    summary = attach_meta(
        {
            "n_cells": int(adata.n_obs),
            "n_genes": int(adata.n_vars),
            "cluster_key": cl_c.get("cluster_key"),
            "n_clusters": cl_c.get("n_clusters"),
            "allowed_next_actions": [
                "Read markers CSV; clusters are numeric only",
                "scrna_pseudobulk.py before any condition DE",
                "scrna_plot.py for UMAP/dotplot",
                "scvi-tools if batch correction is required",
            ],
            "forbidden_next": [
                "Invent cell-type labels from marker names",
                "Publish rank_genes_groups p-values as condition DE",
            ],
            "steps": steps,
        },
        method="scanpy_gold_chain",
        backend="scanpy",
        evidence_grade=cl_c.get("evidence_grade", "A"),
        limitations=["This plugin does not assign cell-type identity. Leiden/KMeans labels are numeric only."],
    )
    adata.uns["pipeline_contract"] = summary
    return adata, markers, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="scverse scRNA gold chain")
    parser.add_argument("input", help=".h5ad or 10x .h5")
    parser.add_argument("-o", "--output", default=None, help="Clustered .h5ad")
    parser.add_argument("--config", default=None, help="JSON config; CLI flags override keys")
    parser.add_argument("--markers-csv", default=None)
    parser.add_argument("--skip-qc", action="store_true")
    parser.add_argument("--skip-doctor", action="store_true")
    parser.add_argument("--resolution", type=float, default=None)
    parser.add_argument("--n-top-genes", type=int, default=None)
    parser.add_argument("--n-marker-genes", type=int, default=None)
    parser.add_argument("--extra-resolutions", nargs="*", type=float, default=None)
    parser.add_argument("--run-scrublet", action="store_true", help="Run scanpy.pp.scrublet after QC")
    args = parser.parse_args()
    from bio_research.gate import require_doctor
    from bio_research.pipeline_config import load_pipeline_config, merge_config

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    cfg = merge_config(
        load_pipeline_config(args.config),
        {
            "output": args.output,
            "markers_csv": args.markers_csv,
            "resolution": args.resolution,
            "n_top_genes": args.n_top_genes,
            "n_marker_genes": args.n_marker_genes,
            "extra_resolutions": args.extra_resolutions,
        },
    )
    output = cfg.get("output")
    if not output:
        parser.error("--output is required (flag or config.output)")
    run_qc = not args.skip_qc
    if "run_qc" in cfg and not args.skip_qc:
        run_qc = bool(cfg["run_qc"])
    if args.skip_qc:
        run_qc = False
    import scanpy as sc

    path = args.input
    if path.endswith(".h5") and not path.endswith(".h5ad"):
        adata = sc.read_10x_h5(path)
    else:
        adata = sc.read_h5ad(path)
    out = Path(str(output))
    extra = cfg.get("extra_resolutions") or [0.3, 0.8]
    if args.run_scrublet or bool(cfg.get("run_scrublet")):
        from scrna_scrublet import run_scrublet

        adata, scrub = run_scrublet(adata)
        if scrub.get("abstain"):
            print(json.dumps(scrub, indent=2))
            sys.exit(2)
    adata, markers, summary = run_scrna_gold_chain(
        adata,
        run_qc=run_qc,
        n_top_genes=int(cfg.get("n_top_genes", 2000)),
        resolution=float(cfg.get("resolution", 0.5)),
        extra_resolutions=[float(x) for x in extra],
        n_marker_genes=int(cfg.get("n_marker_genes", 20)),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(out)
    markers_csv = cfg.get("markers_csv")
    csv_path = Path(markers_csv) if markers_csv else out.with_name(out.stem + "_markers.csv")
    markers.to_csv(csv_path, index=False)
    out.with_suffix(".provenance.json").write_text(
        json.dumps(
            sidecar(
                activity_name="scrna_gold_chain",
                input_files=[args.input],
                output_files=[str(out), str(csv_path)],
                method="scanpy_gold_chain",
                backend="scanpy",
                parameters={
                    "config": args.config,
                    "run_qc": run_qc,
                    "resolution": cfg.get("resolution", 0.5),
                    "n_top_genes": cfg.get("n_top_genes", 2000),
                },
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
