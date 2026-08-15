#!/usr/bin/env python3
"""Write UMAP/dotplot PNGs with stable filenames (no scanpy save= prefix)."""

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


def plot_processed(
    adata,
    out_dir: str,
    *,
    color: str | None = None,
    genes: list[str] | None = None,
) -> dict:
    require("scanpy", for_method="plot_processed")
    import matplotlib.pyplot as plt
    import scanpy as sc

    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    key = color
    if key is None:
        key = "leiden" if "leiden" in adata.obs else ("cluster" if "cluster" in adata.obs else None)
    written: list[str] = []
    if "X_umap" in adata.obsm and key:
        fig = sc.pl.umap(adata, color=key, show=False, return_fig=True)
        path = dest / f"umap_{key}.png"
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        written.append(str(path))
    if genes and key:
        present = [g for g in genes if g in adata.var_names]
        if present:
            dp = sc.pl.dotplot(adata, var_names=present, groupby=key, show=False, return_fig=True)
            path = dest / "dotplot_markers.png"
            # DotPlot may be an object with .savefig or a Figure
            if hasattr(dp, "savefig"):
                dp.savefig(path, dpi=150, bbox_inches="tight")
            elif hasattr(dp, "fig"):
                dp.fig.savefig(path, dpi=150, bbox_inches="tight")
            else:
                plt.savefig(path, dpi=150, bbox_inches="tight")
            plt.close("all")
            written.append(str(path))
    qc_keys = [k for k in ("total_counts", "n_genes_by_counts", "pct_counts_mt") if k in adata.obs]
    if qc_keys:
        sc.pl.violin(adata, keys=qc_keys, groupby=key if key in adata.obs else None, show=False)
        path = dest / "violin_qc.png"
        fig = plt.gcf()
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        written.append(str(path))
    return attach_meta(
        {"figures": written, "color": key},
        method="scanpy.pl + matplotlib.savefig",
        backend="scanpy",
        evidence_grade=GRADE_A,
        limitations=["Filenames are stable: umap_{color}.png, dotplot_markers.png, violin_qc.png."],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot processed scRNA object")
    parser.add_argument("input")
    parser.add_argument("-o", "--output-dir", required=True)
    parser.add_argument("--color", default=None)
    parser.add_argument("--genes", nargs="*", default=None)
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    print(json.dumps(plot_processed(adata, args.output_dir, color=args.color, genes=args.genes), indent=2))


if __name__ == "__main__":
    main()
