#!/usr/bin/env python3
"""Batch integration on a preprocessed object.

Harmony if installed; otherwise ComBat. Never silent. scVI remains the
preferred deep model via the scvi-tools skill.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.backends import is_available, require
from bionexus.contracts import GRADE_A, GRADE_B, attach_meta, refuse


def integrate_batches(adata, *, batch_key: str, method: str = "auto"):
    require("scanpy", for_method="integrate_batches")
    import scanpy as sc

    if batch_key not in adata.obs:
        raise ValueError(f"batch_key '{batch_key}' not in adata.obs")
    if "X_pca" not in adata.obsm:
        sc.pp.pca(adata)

    chosen = method
    if method == "auto":
        chosen = "harmony" if is_available("harmonypy") else "combat"

    if chosen == "harmony":
        try:
            import harmonypy  # noqa: F401

            sc.external.pp.harmony_integrate(adata, key=batch_key)
            adata.obsm["X_pca_integrated"] = adata.obsm.get("X_pca_harmony", adata.obsm["X_pca"])
            return attach_meta(
                {"batch_key": batch_key, "rep": "X_pca_harmony"},
                method="scanpy.external.pp.harmony_integrate",
                backend="harmonypy",
                evidence_grade=GRADE_A,
                limitations=["Harmony on PCA. For nonlinear batches use scvi-tools."],
            )
        except Exception as exc:
            if method == "harmony":
                return refuse(method="harmony_integrate", reason=f"Harmony failed: {exc}")
            chosen = "combat"

    sc.pp.combat(adata, key=batch_key)
    return attach_meta(
        {"batch_key": batch_key, "rep": "X after combat"},
        method="scanpy.pp.combat",
        backend="scanpy",
        evidence_grade=GRADE_B,
        limitations=["ComBat is linear. Prefer Harmony or scVI when available."],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch integration")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--batch-key", required=True)
    parser.add_argument("--method", default="auto", choices=["auto", "harmony", "combat"])
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    contract = integrate_batches(adata, batch_key=args.batch_key, method=args.method)
    if contract.get("refused"):
        print(json.dumps(contract, indent=2))
        sys.exit(2)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(args.output)
    print(json.dumps(contract, indent=2))


if __name__ == "__main__":
    main()
