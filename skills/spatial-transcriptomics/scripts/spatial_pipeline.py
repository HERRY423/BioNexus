#!/usr/bin/env python3
"""squidpy spatial gold chain: knn graph → Moran SVGs → optional Leiden.

Refuses if squidpy is missing. Does not silently fall back to local Moran.
Does not claim Cell2location / BayesSpace / SpaGCN.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from spatial_io import load_spatial_anndata, resolve_spatial_key

from bionexus.backends import require
from bionexus.contracts import GRADE_A, GRADE_B, GRADE_C, EvidenceCard, attach_meta
from bionexus.integrity import audit_expression_matrix, audit_spatial_coordinates
from bionexus.pipeline_config import load_pipeline_config, merge_config
from bionexus.provenance import sidecar


def run_spatial_gold_chain(
    adata,
    *,
    spatial_key: str = "spatial",
    n_neighs: int = 6,
    top_n: int = 50,
    cluster: bool = True,
    resolution: float = 0.5,
):
    require("squidpy", for_method="run_spatial_gold_chain")
    import numpy as np
    import pandas as pd
    import squidpy as sq

    key = resolve_spatial_key(adata, preferred=spatial_key)
    coords_grade, coords_notes, coords_stats = audit_spatial_coordinates(adata.obsm.get(key))

    # Audit expression input integrity
    input_counts_grade, input_counts_notes, input_stats = audit_expression_matrix(
        adata.layers.get("counts", adata.X), expected_type="counts"
    )

    limitations = [
        "knn graph (not Delaunay). Moran ranking preferred over unadjusted p-values.",
        "Expression Leiden is optional and is not a spatial domain model.",
    ]

    if "counts" not in adata.layers:
        if input_counts_grade == GRADE_A:
            adata.layers["counts"] = adata.X.copy()
        else:
            adata.layers["counts"] = adata.X.copy()
            limitations.append(
                "layers['counts'] was missing and adata.X appears non-integer/log-normalized; "
                "normalized expression was stored as counts fallback."
            )

    knn = getattr(sq.gr, "spatial_neighbors_knn", None)
    if knn is not None:
        knn(adata, spatial_key=key, n_neighs=int(n_neighs))
        graph_name = "squidpy.gr.spatial_neighbors_knn"
    else:
        sq.gr.spatial_neighbors(
            adata,
            spatial_key=key,
            coord_type="generic",
            n_neighs=int(n_neighs),
            delaunay=False,
        )
        graph_name = "squidpy.gr.spatial_neighbors"
    sq.gr.spatial_autocorr(adata, mode="moran")
    moran = adata.uns.get("moranI")
    if moran is None:
        raise RuntimeError("squidpy.gr.spatial_autocorr did not write uns['moranI']")
    svg = pd.DataFrame(moran).reset_index().rename(columns={"index": "gene"})
    if "I" in svg.columns:
        svg = svg.rename(columns={"I": "morans_i"})
    if "pval_norm_fdr_bh" in svg.columns and "fdr_q_value" not in svg.columns:
        svg["fdr_q_value"] = svg["pval_norm_fdr_bh"]
    elif "fdr_q_value" not in svg.columns:
        svg["fdr_q_value"] = np.nan
    svg = svg.sort_values(by="morans_i", ascending=False).reset_index(drop=True)
    svg["svg_rank"] = np.arange(1, len(svg) + 1)
    adata.var["spatial_morans_i"] = np.nan
    overlap = [g for g in svg["gene"].astype(str) if g in adata.var_names]
    if overlap:
        adata.var.loc[overlap, "spatial_morans_i"] = svg.set_index("gene").loc[overlap, "morans_i"]

    cluster_key = None
    n_clusters = None
    cluster_error = None
    x_log1p = False
    if cluster:
        try:
            import scanpy as sc

            n_pcs = int(min(20, max(2, adata.n_obs - 1), max(2, adata.n_vars - 1)))
            sc.pp.normalize_total(adata, target_sum=1e4)
            sc.pp.log1p(adata)
            x_log1p = True
            sc.pp.pca(adata, n_comps=n_pcs)
            sc.pp.neighbors(adata, n_neighbors=min(15, adata.n_obs - 1), n_pcs=n_pcs)
            try:
                sc.tl.leiden(
                    adata,
                    resolution=resolution,
                    key_added="leiden",
                    flavor="igraph",
                    n_iterations=2,
                    directed=False,
                )
            except Exception:
                sc.tl.leiden(adata, resolution=resolution, key_added="leiden")
            cluster_key = "leiden"
            n_clusters = int(adata.obs["leiden"].nunique())
        except Exception as exc:
            cluster_error = str(exc)
            cluster_key = None

    if cluster_error:
        limitations.append(f"Leiden requested but failed: {cluster_error}")
    if x_log1p:
        limitations.append("X was log1p-normalized after Moran; raw counts remain in layers['counts'].")

    # Evaluate statistical support from SVG significance
    sig_svg = 0
    if "fdr_q_value" in svg.columns and not svg["fdr_q_value"].isna().all():
        sig_svg = int(np.sum(svg["fdr_q_value"] < 0.05))
    elif "pval_norm" in svg.columns and not svg["pval_norm"].isna().all():
        sig_svg = int(np.sum(svg["pval_norm"] < 0.05))
    stat_grade = GRADE_A if sig_svg > 0 else GRADE_B

    # Composite EvidenceCard
    effective_input_grade = (
        GRADE_C
        if (coords_grade == GRADE_C or input_counts_grade == GRADE_C)
        else (GRADE_B if (coords_grade == GRADE_B or input_counts_grade == GRADE_B) else GRADE_A)
    )
    card = EvidenceCard(
        execution_fidelity=GRADE_A if not cluster_error else GRADE_C,
        input_integrity=effective_input_grade,
        assumption_validity=GRADE_A if effective_input_grade == GRADE_A else GRADE_B,
        statistical_support=stat_grade,
        parameter_robustness=GRADE_B,
        details={
            "spatial_coords_grade": coords_grade,
            "expression_integrity_grade": input_counts_grade,
            "input_notes": coords_notes + input_counts_notes,
            "graph": graph_name,
            "significant_svg_count": sig_svg,
        },
    )

    summary = attach_meta(
        {
            "n_obs": int(adata.n_obs),
            "n_vars": int(adata.n_vars),
            "spatial_key": key,
            "n_neighs": int(n_neighs),
            "graph": graph_name,
            "n_svg": int(min(top_n, len(svg))),
            "cluster_key": cluster_key,
            "n_clusters": n_clusters,
            "cluster_requested": bool(cluster),
            "cluster_error": cluster_error,
            "x_log1p": x_log1p,
            "allowed_next_actions": [
                "Rank genes by Moran's I; treat FDR as squidpy default",
                "Clusters are numeric only; this plugin does not assign cell types",
            ],
            "forbidden_next": [
                "Call this Cell2location, BayesSpace, or SpaGCN",
                "Use local heuristic Moran when squidpy ran",
            ],
        },
        method="squidpy_spatial_gold_chain",
        backend="squidpy",
        evidence_grade=GRADE_A if not cluster_error else GRADE_C,
        limitations=limitations,
        abstain=bool(cluster_error),
        abstain_reason=f"Leiden requested but failed: {cluster_error}" if cluster_error else None,
        evidence_card=card,
    )
    adata.uns["spatial_pipeline_contract"] = summary
    return adata, svg.head(top_n), summary


def main() -> None:
    parser = argparse.ArgumentParser(description="squidpy spatial gold chain")
    parser.add_argument("input", help="SpatialData .zarr or AnnData .h5ad with obsm['spatial']")
    parser.add_argument("-o", "--output", default=None, help="Output .h5ad")
    parser.add_argument("--config", default=None)
    parser.add_argument("--svg-csv", default=None)
    parser.add_argument("--spatial-key", default=None)
    parser.add_argument("--n-neighs", type=int, default=None)
    parser.add_argument("--top-n", type=int, default=None)
    parser.add_argument("--resolution", type=float, default=None)
    parser.add_argument("--skip-cluster", action="store_true")
    parser.add_argument("--table", default=None, help="SpatialData table name (required if multiple tables)")
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_spatial=True, skip=args.skip_doctor)
    cfg = merge_config(
        load_pipeline_config(args.config),
        {
            "output": args.output,
            "svg_csv": args.svg_csv,
            "spatial_key": args.spatial_key,
            "n_neighs": args.n_neighs,
            "top_n": args.top_n,
            "resolution": args.resolution,
        },
    )
    output = cfg.get("output")
    if not output:
        parser.error("--output is required (flag or config.output)")
    cluster = True
    if "cluster" in cfg:
        cluster = bool(cfg["cluster"])
    if args.skip_cluster:
        cluster = False
    adata = load_spatial_anndata(args.input, table_key=args.table)
    n_neighs = cfg.get("n_neighs")
    top_n = cfg.get("top_n")
    resolution = cfg.get("resolution")
    adata, svg, summary = run_spatial_gold_chain(
        adata,
        spatial_key=str(cfg.get("spatial_key") or "spatial"),
        n_neighs=6 if n_neighs is None else int(n_neighs),
        top_n=50 if top_n is None else int(top_n),
        cluster=cluster,
        resolution=0.5 if resolution is None else float(resolution),
    )
    out = Path(str(output))
    out.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(out)
    csv_path = Path(cfg["svg_csv"]) if cfg.get("svg_csv") else out.with_name(out.stem + "_svg.csv")
    svg.to_csv(csv_path, index=False)
    out.with_suffix(".provenance.json").write_text(
        json.dumps(
            sidecar(
                activity_name="spatial_gold_chain",
                input_files=[args.input],
                output_files=[str(out), str(csv_path)],
                method="squidpy_spatial_gold_chain",
                backend="squidpy",
                parameters={
                    "n_neighs": cfg.get("n_neighs") or 6,
                    "spatial_key": cfg.get("spatial_key") or "spatial",
                },
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
