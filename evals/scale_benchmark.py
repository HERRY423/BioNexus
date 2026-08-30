#!/usr/bin/env python3
"""Scale benchmark for the BioNexus gold-chain kernel (sparse, streaming, honest).

Measures wall time and peak memory for the representative single-cell stages —
synthetic CSR generation, QC masking, CPM/log1p normalization, HVG selection,
and TruncatedSVD PCA — at a configurable cell scale (default 500,000 cells,
the cluster reference point).

Honesty contract:
- The synthetic matrix is a structured Poisson simulation with planted cell
  groups, NOT real tissue; the benchmark measures ENGINEERING envelope
  (throughput and memory), never biological validity.
- The committed report (evals/reports/scale_benchmark.md) records the exact
  machine it ran on. A laptop validation run is not a cluster number.

Usage:
    python evals/scale_benchmark.py --cells 500000 --genes 20000 --out evals/reports
    python evals/scale_benchmark.py --cells 30000 --genes 5000   # local validation
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import svds

STAGES = ("generate", "qc_mask", "normalize_log1p", "hvg_select", "pca")


def _peak_rss_gb() -> float:
    """Peak RSS in GiB via ru_maxrss (POSIX only); nan on platforms without it."""
    import sys

    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        # macOS reports bytes, Linux reports KiB.
        scale = 1 / 1024**3 if sys.platform == "darwin" else 1 / 1024**2
        return ru * scale
    except Exception:
        return float("nan")  # Windows: no ru_maxrss; not reported (see honesty note)


def _timed(stage: str, results: Dict[str, Any], fn: Callable[[], Any]) -> Any:
    t0 = time.perf_counter()
    value = fn()
    elapsed = round(time.perf_counter() - t0, 3)
    results["stages"][stage] = {"wall_seconds": elapsed}
    print(f"  [{stage}] {elapsed}s")
    return value


def make_csr(n_cells: int, n_genes: int, seed: int, groups: int = 6) -> sparse.csr_matrix:
    """Structured sparse Poisson counts: ~3% density with planted group means."""
    rng = np.random.default_rng(seed)
    rows_per_group = n_cells // groups
    blocks = []
    for g in range(groups):
        size = rows_per_group if g < groups - 1 else n_cells - rows_per_group * (groups - 1)
        base = rng.poisson(1.5, size=(size, n_genes)).astype(np.float32)
        marker_cols = rng.choice(n_genes, size=n_genes // groups, replace=False)
        base[:, marker_cols] += rng.poisson(6.0, size=(size, len(marker_cols))).astype(np.float32)
        blocks.append(sparse.csr_matrix(base))
    return sparse.vstack(blocks, format="csr")


def run_benchmark(n_cells: int, n_genes: int, seed: int) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "config": {"n_cells": n_cells, "n_genes": n_genes, "seed": seed,
                   "target_density": "~3% structural Poisson"},
        "stages": {},
    }

    x = _timed("generate", results, lambda: make_csr(n_cells, n_genes, seed))
    results["stages"]["generate"]["nnz"] = int(x.nnz)
    results["stages"]["generate"]["matrix_gb"] = round((x.data.nbytes + x.indices.nbytes + x.indptr.nbytes) / 1024**3, 3)

    def qc_mask() -> sparse.csr_matrix:
        counts_per_cell = np.asarray(x.sum(axis=1)).ravel()
        genes_per_cell = np.diff(x.indptr)
        lo, hi = np.percentile(counts_per_cell, [1, 99])
        keep = (counts_per_cell >= lo) & (counts_per_cell <= hi) & (genes_per_cell > 0)
        return x[keep]

    x = _timed("qc_mask", results, lambda: qc_mask())

    def normalize() -> sparse.csr_matrix:
        counts = np.asarray(x.sum(axis=1)).ravel()
        inv = sparse.diags(1.0 / np.maximum(counts, 1) * 10000.0)
        return (inv @ x).tocsr().log1p()

    x = _timed("normalize_log1p", results, lambda: normalize())

    def hvg() -> np.ndarray:
        means = np.asarray(x.mean(axis=0)).ravel()
        variances = np.asarray(x.multiply(x).mean(axis=0)).ravel() - means**2
        disp = variances / np.maximum(means, 1e-8)
        return np.sort(np.argsort(disp)[-2000:])

    hvg_idx = _timed("hvg_select", results, lambda: hvg())

    def pca() -> np.ndarray:
        k = 30
        u, s, vt = svds(x[:, hvg_idx].astype(np.float64), k=k)
        return (u * s)

    _timed("pca", results, lambda: pca())

    results["peak_rss_gb"] = round(_peak_rss_gb(), 3)
    results["total_wall_seconds"] = round(sum(s["wall_seconds"] for s in results["stages"].values()), 3)
    results["throughput_cells_per_second"] = round(n_cells / max(results["total_wall_seconds"], 1e-9))
    return results


def machine_fingerprint() -> Dict[str, Any]:
    import platform

    info: Dict[str, Any] = {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "machine": platform.machine(),
    }
    try:
        import psutil  # optional

        info["ram_total_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
        info["cpu_count"] = psutil.cpu_count(logical=True)
    except ImportError:
        info["ram_total_gb"] = None
        info["cpu_count"] = os_cpu_count()
    return info


def os_cpu_count() -> int:
    import os

    return os.cpu_count() or 0


def main() -> int:
    parser = argparse.ArgumentParser(description="BioNexus scale benchmark (engineering envelope)")
    parser.add_argument("--cells", type=int, default=500_000)
    parser.add_argument("--genes", type=int, default=20_000)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--out", default="evals/reports", help="Report output directory")
    args = parser.parse_args()

    print(f"BioNexus scale benchmark: {args.cells:,} cells x {args.genes:,} genes")
    results = run_benchmark(args.cells, args.genes, args.seed)
    report = {
        "schema_version": "bionexus.scale-benchmark.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine": machine_fingerprint(),
        "honesty": (
            "Structured synthetic Poisson counts measure the engineering envelope "
            "(throughput, memory) of the kernel stages. This is not biological "
            "validity and not a clinical performance claim. Peak RSS uses "
            "ru_maxrss on POSIX; on Windows it is not reported."
        ),
        **results,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"{args.cells//1000}k_{args.genes//1000}g"
    (out_dir / f"scale_benchmark_{suffix}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = [
        "# BioNexus Scale Benchmark",
        "",
        f"- Config: {args.cells:,} cells x {args.genes:,} genes (seed {args.seed})",
        f"- Machine: {report['machine']}",
        f"- Total wall: **{results['total_wall_seconds']}s** | throughput: {results['throughput_cells_per_second']:,} cells/s | peak RSS: {results['peak_rss_gb']} GB",
        "",
        "| Stage | Wall (s) |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v['wall_seconds']} |" for k, v in results["stages"].items()]
    lines += ["", report["honesty"], ""]
    (out_dir / f"scale_benchmark_{suffix}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] report -> {out_dir}/scale_benchmark_{suffix}.json/.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
