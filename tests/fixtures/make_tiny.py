#!/usr/bin/env python3
"""Write tiny planted scRNA / spatial fixtures (keep each file well under 5 MB)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import scipy.sparse as sp


def write_tiny_scrna(dest: Path, n_per: int = 30, n_genes: int = 60) -> Path:
    import anndata as ad

    rng = np.random.default_rng(0)
    n_cells = n_per * 3
    counts = rng.poisson(0.4, size=(n_cells, n_genes)).astype(np.float32)
    counts[:n_per, 10:20] += 30
    counts[n_per : 2 * n_per, 20:30] += 30
    counts[2 * n_per :, 30:40] += 30
    genes = [f"Gene_{i}" for i in range(n_genes)]
    genes[10], genes[20], genes[30] = "CD3D", "MS4A1", "CD14"
    genes[0] = "MT-CO1"
    adata = ad.AnnData(X=sp.csr_matrix(counts))
    adata.obs_names = [f"c{i}" for i in range(n_cells)]
    adata.var_names = genes
    adata.obs["sample"] = ["s1"] * n_per + ["s2"] * n_per + ["s1"] * n_per
    adata.obs["true_type"] = ["T"] * n_per + ["B"] * n_per + ["Mono"] * n_per
    adata.layers["counts"] = adata.X.copy()
    dest.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(dest)
    return dest


def write_tiny_spatial(dest: Path, n_side: int = 8, n_genes: int = 40) -> Path:
    import anndata as ad

    rng = np.random.default_rng(1)
    n_spots = n_side * n_side
    coords = np.array([(i % n_side, i // n_side) for i in range(n_spots)], dtype=float)
    counts = rng.poisson(1.0, size=(n_spots, n_genes)).astype(np.float32)
    left = coords[:, 0] < (n_side / 2)
    counts[left, 0] += 40
    genes = [f"Gene_{j}" for j in range(n_genes)]
    genes[0] = "SVG_LEFT"
    adata = ad.AnnData(X=sp.csr_matrix(counts))
    adata.obs_names = [f"spot_{i}" for i in range(n_spots)]
    adata.var_names = genes
    adata.obsm["spatial"] = coords
    adata.obs["in_tissue"] = 1
    adata.layers["counts"] = adata.X.copy()
    dest.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(dest)
    return dest


def main() -> None:
    here = Path(__file__).resolve().parent
    write_tiny_scrna(here / "tiny_scrna.h5ad")
    write_tiny_spatial(here / "tiny_spatial.h5ad")


if __name__ == "__main__":
    main()
