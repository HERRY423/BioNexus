#!/usr/bin/env python3
"""Official scanpy.pp.scrublet only. Refuses if that API is missing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.backends import require
from bionexus.contracts import GRADE_A, attach_meta, refuse


def run_scrublet(adata, *, expected_doublet_rate: float | None = None):
    require("scanpy", for_method="run_scrublet")
    import scanpy as sc

    if not hasattr(sc.pp, "scrublet"):
        return adata, refuse(
            method="scanpy.pp.scrublet",
            reason="scanpy.pp.scrublet is missing (need scanpy>=1.10). Not falling back to local kNN doublets.",
        )
    if "counts" not in adata.layers:
        return adata, refuse(
            method="scanpy.pp.scrublet",
            reason="Need layers['counts'] raw counts. Refusing to score log-like X.",
        )
    kwargs = {}
    if expected_doublet_rate is not None:
        kwargs["expected_doublet_rate"] = expected_doublet_rate
    n_comp = int(max(2, min(10, adata.n_obs // 5, max(2, adata.n_vars // 4))))
    view = adata.copy()
    view.X = view.layers["counts"]
    try:
        sc.pp.scrublet(view, n_prin_comps=n_comp, **kwargs)
    except (ValueError, Exception) as e:
        if any(k in str(e).lower() for k in ("scikit-image", "skimage", "threshold")):
            sc.pp.scrublet(view, n_prin_comps=n_comp, threshold=0.25, **kwargs)
        else:
            raise
    for col in ("doublet_score", "predicted_doublet"):
        if col in view.obs:
            adata.obs[col] = view.obs[col]
    n_doublets = None
    if "predicted_doublet" in adata.obs:
        n_doublets = int(adata.obs["predicted_doublet"].astype(bool).sum())
    return adata, attach_meta(
        {
            "n_obs": int(adata.n_obs),
            "n_predicted_doublets": n_doublets,
            "obs_score": "doublet_score" if "doublet_score" in adata.obs else None,
        },
        method="scanpy.pp.scrublet",
        backend="scanpy",
        evidence_grade=GRADE_A,
        limitations=["Official Scrublet via scanpy. Not scDblFinder. Not the local doublet_detection.py heuristic."],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="scanpy.pp.scrublet")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--expected-doublet-rate", type=float, default=None)
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    adata, contract = run_scrublet(adata, expected_doublet_rate=args.expected_doublet_rate)
    if contract.get("abstain"):
        print(json.dumps(contract, indent=2))
        sys.exit(2)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(args.output)
    print(json.dumps(contract, indent=2))


if __name__ == "__main__":
    main()
