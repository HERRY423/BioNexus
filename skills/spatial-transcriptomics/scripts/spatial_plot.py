#!/usr/bin/env python3
"""squidpy.pl.spatial_scatter with stable filenames. Refuses without squidpy."""

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
from bionexus.contracts import GRADE_A, attach_meta


def plot_spatial(adata, out_dir: str, *, color: str | None = None, spatial_key: str = "spatial"):
    require("squidpy", for_method="plot_spatial")
    import matplotlib.pyplot as plt
    import squidpy as sq

    if not hasattr(sq.pl, "spatial_scatter"):
        raise RuntimeError("squidpy.pl.spatial_scatter is missing")
    dest = Path(out_dir)
    dest.mkdir(parents=True, exist_ok=True)
    key = resolve_spatial_key(adata, preferred=spatial_key)
    color_key = color
    if color_key is None:
        color_key = "leiden" if "leiden" in adata.obs else ("cluster" if "cluster" in adata.obs else None)
    kwargs = {"spatial_key": key, "shape": None, "img": False}
    if color_key:
        kwargs["color"] = color_key
    try:
        sq.pl.spatial_scatter(adata, **kwargs)
    except TypeError:
        kwargs.pop("img", None)
        sq.pl.spatial_scatter(adata, **kwargs)
    fig = plt.gcf()
    name = f"spatial_{color_key}.png" if color_key else "spatial_scatter.png"
    path = dest / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return attach_meta(
        {"figures": [str(path)], "color": color_key, "spatial_key": key},
        method="squidpy.pl.spatial_scatter",
        backend="squidpy",
        evidence_grade=GRADE_A,
        limitations=["Stable filename spatial_{color}.png. Not a BayesSpace domain map."],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="squidpy spatial_scatter")
    parser.add_argument("input")
    parser.add_argument("-o", "--output-dir", required=True)
    parser.add_argument("--color", default=None)
    parser.add_argument("--spatial-key", default="spatial")
    parser.add_argument("--table", default=None)
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_spatial=True, skip=args.skip_doctor)
    adata = load_spatial_anndata(args.input, table_key=args.table)
    print(json.dumps(plot_spatial(adata, args.output_dir, color=args.color, spatial_key=args.spatial_key), indent=2))


if __name__ == "__main__":
    main()
