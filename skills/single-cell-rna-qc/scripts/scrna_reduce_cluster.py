#!/usr/bin/env python3
"""PCA, neighbors, UMAP, and Leiden (KMeans fallback if leidenalg missing)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.backends import require
from bionexus.contracts import GRADE_A, GRADE_C, attach_meta
from bionexus.provenance import sidecar


def reduce_and_cluster(
    adata,
    *,
    n_pcs: int = 30,
    n_neighbors: int = 15,
    resolution: float = 0.5,
    extra_resolutions: list[float] | None = None,
    random_state: int = 42,
):
    require("scanpy", for_method="reduce_and_cluster")
    import numpy as np
    import scanpy as sc

    n_pcs_use = int(min(n_pcs, max(2, adata.n_obs - 1), max(2, adata.n_vars - 1)))
    use_hvg = "highly_variable" in adata.var and int(adata.var["highly_variable"].sum()) >= 10
    pca_kwargs = {"n_comps": n_pcs_use, "random_state": random_state}
    try:
        sc.pp.pca(adata, mask_var="highly_variable" if use_hvg else None, **pca_kwargs)
    except TypeError:
        sc.pp.pca(adata, use_highly_variable=use_hvg, **pca_kwargs)
    sc.pp.neighbors(adata, n_neighbors=min(n_neighbors, adata.n_obs - 1), n_pcs=n_pcs_use)
    sc.tl.umap(adata, random_state=random_state)

    cluster_key = "leiden"
    cluster_method = "scanpy.tl.leiden"
    grade = GRADE_A
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
        try:
            sc.tl.leiden(adata, resolution=resolution, key_added="leiden")
        except Exception:
            from sklearn.cluster import KMeans

            n_clusters = int(max(2, min(8, adata.n_obs // 20)))
            labels = KMeans(n_clusters=n_clusters, random_state=random_state, n_init=10).fit_predict(
                adata.obsm["X_pca"]
            )
            adata.obs["cluster"] = np.asarray(labels).astype(str)
            cluster_key = "cluster"
            cluster_method = "sklearn_kmeans_fallback_not_leiden"
            grade = GRADE_C

    extra_keys = []
    if grade == GRADE_A:
        for res in extra_resolutions or []:
            if abs(float(res) - float(resolution)) < 1e-9:
                continue
            key = f"leiden_{res}"
            try:
                sc.tl.leiden(
                    adata,
                    resolution=float(res),
                    key_added=key,
                    flavor="igraph",
                    n_iterations=2,
                    directed=False,
                )
                extra_keys.append(key)
            except Exception:
                try:
                    sc.tl.leiden(adata, resolution=float(res), key_added=key)
                    extra_keys.append(key)
                except Exception:
                    break

    n_clusters = int(adata.obs[cluster_key].nunique())
    contract = attach_meta(
        {
            "n_pcs": n_pcs_use,
            "n_neighbors": n_neighbors,
            "resolution": resolution,
            "extra_cluster_keys": extra_keys,
            "cluster_key": cluster_key,
            "n_clusters": n_clusters,
        },
        method=cluster_method,
        backend="scanpy" if grade == GRADE_A else "sklearn",
        evidence_grade=grade,
        limitations=[
            "KMeans fallback is not Leiden."
            if grade == GRADE_C
            else "Leiden resolution is a granularity knob, not a biological truth.",
        ],
        abstain=grade == GRADE_C,
        abstain_reason="leidenalg/igraph missing; clusters are KMeans on PCA." if grade == GRADE_C else None,
    )
    adata.uns["cluster_contract"] = contract
    return adata, contract


def main() -> None:
    parser = argparse.ArgumentParser(description="PCA + neighbors + UMAP + Leiden")
    parser.add_argument("input")
    parser.add_argument("-o", "--output", required=True)
    parser.add_argument("--resolution", type=float, default=0.5)
    parser.add_argument("--n-pcs", type=int, default=30)
    parser.add_argument("--skip-doctor", action="store_true")
    args = parser.parse_args()
    from bionexus.gate import require_doctor

    require_doctor(require_scverse=True, skip=args.skip_doctor)
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    adata, contract = reduce_and_cluster(adata, n_pcs=args.n_pcs, resolution=args.resolution)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(args.output)
    Path(args.output).with_suffix(".provenance.json").write_text(
        json.dumps(
            sidecar(
                activity_name="scrna_reduce_cluster",
                input_files=[args.input],
                output_files=[args.output],
                method=contract["method"],
                backend=contract["backend"],
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(contract, indent=2))


if __name__ == "__main__":
    main()
