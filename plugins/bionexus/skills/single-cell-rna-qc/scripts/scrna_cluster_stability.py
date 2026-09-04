#!/usr/bin/env python3
"""Execute a declared Leiden resolution/resampling grid and retain every partition."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from bionexus.clustering_stability import assess_clustering_stability


def run_grid(adata, *, dataset_sha256, resolutions, fractions, seeds, min_ari=None):
    """Bounded caller-declared execution. Inputs are copied; no label identities inferred."""
    import numpy as np
    from scrna_preprocess import preprocess_scrna
    from scrna_reduce_cluster import reduce_and_cluster

    if not adata.obs_names.is_unique or adata.n_obs < 3:
        raise ValueError("unique cell ids and at least 3 cells are required")
    if not resolutions or any(not np.isfinite(r) or r <= 0 for r in resolutions):
        raise ValueError("resolutions must be positive and finite")
    if not fractions or any(not np.isfinite(f) or not 0 < f <= 1 for f in fractions):
        raise ValueError("sampling fractions must be in (0, 1]")
    grid = list(itertools.product(resolutions, fractions, seeds))
    if len(grid) < 2 or len(grid) > 100 or len(set(grid)) != len(grid):
        raise ValueError("declare 2..100 distinct perturbations")
    if any(int(adata.n_obs * fraction) < 3 for fraction in fractions):
        raise ValueError("a sampling fraction leaves too few cells for the backend")
    packet = {"dataset_sha256": dataset_sha256, "declared_min_ari": min_ari, "runs": []}
    for index, (resolution, fraction, seed) in enumerate(grid):
        selected = np.sort(np.random.default_rng(seed).choice(adata.n_obs, int(adata.n_obs * fraction), replace=False))
        subset, _ = preprocess_scrna(adata[selected].copy(), n_top_genes=min(2000, adata.n_vars))
        clustered, contract = reduce_and_cluster(subset, resolution=resolution, random_state=seed)
        if contract.get("method") != "scanpy.tl.leiden":
            raise RuntimeError("Canonical Leiden execution required; a fallback cannot establish Leiden stability")
        key = contract["cluster_key"]
        packet["runs"].append(
            {
                "run_id": f"run-{index}",
                "perturbation": f"resolution={resolution};fraction={fraction};seed={seed}",
                "cell_ids": clustered.obs_names.astype(str).tolist(),
                "labels": clustered.obs[key].astype(str).tolist(),
                "backend_contract": contract,
            }
        )
    return packet, assess_clustering_stability(packet, dataset_sha256=dataset_sha256)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--output", type=Path, required=True, help="New directory for the raw partitions and assessment"
    )
    parser.add_argument("--resolutions", type=float, nargs="+", required=True)
    parser.add_argument("--fractions", type=float, nargs="+", required=True)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument(
        "--min-ari", type=float, default=None, help="Caller-declared criterion, never an approved empirical cutoff"
    )
    args = parser.parse_args()
    import anndata as ad

    digest = hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.output.mkdir(parents=True, exist_ok=False)
    packet, assessment = run_grid(
        ad.read_h5ad(args.input),
        dataset_sha256=digest,
        resolutions=args.resolutions,
        fractions=args.fractions,
        seeds=args.seeds,
        min_ari=args.min_ari,
    )
    if hashlib.sha256(args.input.read_bytes()).hexdigest() != digest:
        raise RuntimeError("Input changed during execution")
    for name, value in (("partitions.json", packet), ("assessment.json", assessment)):
        (args.output / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(assessment, indent=2))
    return 1 if assessment["status"] == "INVALID" else 0


if __name__ == "__main__":
    raise SystemExit(main())
