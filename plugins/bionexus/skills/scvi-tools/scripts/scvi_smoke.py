#!/usr/bin/env python3
"""One-epoch scVI smoke. Refuses if scvi-tools is missing. Counts layer only."""

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


def run_scvi_smoke(adata, *, max_epochs: int = 1, n_latent: int = 4, batch_key: str | None = None):
    require("scvi", for_method="run_scvi_smoke")
    import scvi

    if "counts" not in adata.layers:
        raise ValueError("scVI smoke requires layers['counts'] raw counts. Do not train on log1p X.")
    setup_kwargs = {"layer": "counts"}
    if batch_key:
        setup_kwargs["batch_key"] = batch_key
    scvi.model.SCVI.setup_anndata(adata, **setup_kwargs)
    model = scvi.model.SCVI(adata, n_latent=n_latent, n_hidden=32, n_layers=1)
    model.train(max_epochs=max_epochs, check_val_every_n_epoch=None, enable_progress_bar=False)
    adata.obsm["X_scVI"] = model.get_latent_representation()
    return attach_meta(
        {
            "n_obs": int(adata.n_obs),
            "n_latent": n_latent,
            "max_epochs": max_epochs,
            "rep": "X_scVI",
        },
        method="scvi.model.SCVI.train",
        backend="scvi-tools",
        evidence_grade=GRADE_A,
        limitations=["Smoke run only. Not a production integration."],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="1-epoch scVI smoke")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-key", default=None)
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    contract = run_scvi_smoke(adata, max_epochs=args.epochs, batch_key=args.batch_key)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(args.output)
    print(json.dumps(contract, indent=2))


if __name__ == "__main__":
    main()
