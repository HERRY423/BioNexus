#!/usr/bin/env python3
"""Scale benchmark for the BioNexus gold-chain kernel (sparse, streaming, honest).

Measures wall time and peak memory for the representative single-cell stages —
sparse count generation, QC masking, CPM/log1p normalization, HVG selection,
and TruncatedSVD PCA — at a configurable cell scale (default 500,000 cells).

Memory-bounded by construction: generation streams over cell chunks and HVG
accumulates over row chunks, so peak memory is O(chunk x genes), never
O(cells x genes). This is what makes 500k-1M-cell runs possible on a small
8 GB node — and lets an HPC node push the same harness further.

Honesty contract:
- The synthetic matrix is a zero-inflated structured Poisson simulation with
  planted cell groups, NOT real tissue; the benchmark measures the
  ENGINEERING envelope (throughput and memory), never biological validity.
  Structural nonzero density defaults to ~8% because real scRNA-seq count
  matrices are >= 90% zeros; a plain Poisson(1.5) draw is ~78% nonzero and
  does not represent single-cell sparsity (the pre-2026-08 harness used it,
  which is why its 500k-cell "cluster reference" was not actually runnable).
- The committed report (evals/reports/scale_benchmark_*.json) records the
  exact machine it ran on, including its memory class. A small-node run is
  labeled a small-node run; it is not an HPC number. HPC reproduction:
  sbatch cluster/slurm/profiles/run_scale_benchmark.sbatch
- Peak memory uses ru_maxrss on POSIX and the Windows peak working set via
  GetProcessMemoryInfo; the measurement method is recorded in the report.

Usage:
    python evals/scale_benchmark.py --cells 500000 --genes 5000 --density 0.08
    python evals/scale_benchmark.py --cells 30000 --genes 5000   # validation
    python evals/scale_benchmark.py --cells 1000000 --genes 5000 --density 0.05
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import svds

STAGES = ("generate", "qc_mask", "normalize_log1p", "hvg_select", "pca")

#: Fraction of entries that survive as nonzero BEFORE dropout when drawing
#: background Poisson(1.5) plus marker Poisson(6.0) columns (5/6 background,
#: 1/6 markers): (5/6)*P(Poisson(1.5)>0) + (1/6)*P(Poisson(6)>0) ~= 0.812.
_PRE_DROPOUT_NONZERO_RATE = 0.812


def _peak_memory_gb() -> tuple:
    """(peak_gb, method) — ru_maxrss on POSIX, peak working set on Windows."""
    import sys

    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        scale = 1 / 1024**3 if sys.platform == "darwin" else 1 / 1024**2
        return ru * scale, "ru_maxrss"
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import os

            import psutil  # optional

            peak = psutil.Process(os.getpid()).memory_info().peak_wset
            return peak / 1024**3, "windows_peak_working_set_psutil"
        except Exception:
            pass
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            handle = ctypes.WinDLL("kernel32", use_last_error=True).GetCurrentProcess()
            handle = ctypes.c_void_p(handle)
            ok = ctypes.WinDLL("kernel32", use_last_error=True).K32GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb
            )
            if ok:
                return counters.PeakWorkingSetSize / 1024**3, "windows_peak_working_set"
        except Exception:
            pass
    return float("nan"), "unavailable"


def _timed(stage: str, results: Dict[str, Any], fn: Callable[[], Any]) -> Any:
    t0 = time.perf_counter()
    value = fn()
    elapsed = round(time.perf_counter() - t0, 3)
    results["stages"][stage] = {"wall_seconds": elapsed}
    print(f"  [{stage}] {elapsed}s", flush=True)
    return value


def make_csr(
    n_cells: int,
    n_genes: int,
    seed: int,
    groups: int = 6,
    target_density: float = 0.08,
    chunk_cells: int = 10_000,
    progress: Optional[Callable[[str], None]] = None,
) -> sparse.csr_matrix:
    """Zero-inflated structured Poisson counts, generated in cell chunks.

    Streams over chunks so peak memory stays O(chunk_cells x n_genes). Each
    cell group keeps its planted marker columns (Poisson(6.0) boost) on top
    of the Poisson(1.5) background; a Bernoulli dropout mask then controls
    the structural nonzero density at ``target_density``.
    """
    if not 0 < target_density <= 1:
        raise ValueError("target_density must be within (0, 1]")
    rng = np.random.default_rng(seed)
    rows_per_group = max(n_cells // groups, 1)
    marker_sets = [
        rng.choice(n_genes, size=max(n_genes // groups, 1), replace=False) for _ in range(groups)
    ]
    keep_prob = min(1.0, target_density / _PRE_DROPOUT_NONZERO_RATE)
    blocks: List[sparse.csr_matrix] = []
    for start in range(0, n_cells, chunk_cells):
        stop = min(start + chunk_cells, n_cells)
        size = stop - start
        base = rng.poisson(1.5, size=(size, n_genes)).astype(np.float32)
        gid = np.minimum(np.arange(start, stop) // rows_per_group, groups - 1)
        for g in range(groups):
            sel = np.flatnonzero(gid == g)
            if sel.size:
                boost = rng.poisson(6.0, size=(sel.size, len(marker_sets[g]))).astype(np.float32)
                base[np.ix_(sel, marker_sets[g])] += boost
        base *= rng.random(size=(size, n_genes), dtype=np.float32) < keep_prob
        blocks.append(sparse.csr_matrix(base))
        if progress:
            progress(f"cells {start:,}-{stop:,} (nnz total {sum(b.nnz for b in blocks):,})")
    return sparse.vstack(blocks, format="csr")


def run_benchmark(
    n_cells: int,
    n_genes: int,
    seed: int,
    target_density: float = 0.08,
    chunk_cells: int = 10_000,
    svd_k: int = 30,
) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "config": {
            "n_cells": n_cells,
            "n_genes": n_genes,
            "seed": seed,
            "target_density": target_density,
            "chunk_cells": chunk_cells,
            "svd_k": svd_k,
            "density_model": "zero-inflated structured Poisson (background 1.5, marker 6.0)",
        },
        "stages": {},
    }

    x = _timed(
        "generate",
        results,
        lambda: make_csr(
            n_cells, n_genes, seed, target_density=target_density, chunk_cells=chunk_cells
        ),
    )
    results["stages"]["generate"]["nnz"] = int(x.nnz)
    results["stages"]["generate"]["matrix_gb"] = round(
        (x.data.nbytes + x.indices.nbytes + x.indptr.nbytes) / 1024**3, 3
    )
    results["stages"]["generate"]["density_observed"] = round(x.nnz / (n_cells * n_genes), 4)

    def qc_mask() -> sparse.csr_matrix:
        counts_per_cell = np.asarray(x.sum(axis=1)).ravel()
        genes_per_cell = np.diff(x.indptr)
        lo, hi = np.percentile(counts_per_cell, [1, 99])
        keep = (counts_per_cell >= lo) & (counts_per_cell <= hi) & (genes_per_cell > 0)
        return x[keep]

    x = _timed("qc_mask", results, lambda: qc_mask())

    def normalize() -> sparse.csr_matrix:
        # In-place CPM scaling + log1p: scale each nonzero by 1e4 / row count
        # without materializing a second matrix.
        counts = np.asarray(x.sum(axis=1)).ravel()
        np.maximum(counts, 1.0, out=counts)
        scale = (10_000.0 / counts).astype(np.float32)
        x.data *= np.repeat(scale, np.diff(x.indptr))
        np.log1p(x.data, out=x.data)
        return x

    x = _timed("normalize_log1p", results, lambda: normalize())

    def hvg() -> np.ndarray:
        # Row-chunked accumulation: memory-flat column sums / sums of squares.
        sums = np.zeros(n_genes, dtype=np.float64)
        sums_sq = np.zeros(n_genes, dtype=np.float64)
        step = 50_000
        for start in range(0, x.shape[0], step):
            chunk = x[start : start + step]
            sums += np.asarray(chunk.sum(axis=0)).ravel()
            sums_sq += np.asarray(chunk.multiply(chunk).sum(axis=0)).ravel()
        n = x.shape[0]
        means = sums / n
        variances = sums_sq / n - means**2
        disp = variances / np.maximum(means, 1e-8)
        return np.sort(np.argsort(disp)[-2000:])

    hvg_idx = _timed("hvg_select", results, lambda: hvg())

    def pca() -> np.ndarray:
        u, s, vt = svds(x[:, hvg_idx].astype(np.float64), k=svd_k)
        return u * s

    _timed("pca", results, lambda: pca())

    peak_gb, method = _peak_memory_gb()
    results["peak_memory_gb"] = round(peak_gb, 3) if peak_gb == peak_gb else None
    results["peak_memory_method"] = method
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
        import os

        info["ram_total_gb"] = None
        info["cpu_count"] = os.cpu_count() or 0
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description="BioNexus scale benchmark (engineering envelope)")
    parser.add_argument("--cells", type=int, default=500_000)
    parser.add_argument("--genes", type=int, default=5_000)
    parser.add_argument("--density", type=float, default=0.08, help="Structural nonzero density")
    parser.add_argument("--chunk-cells", type=int, default=10_000)
    parser.add_argument("--svd-k", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--label", default=None, help="Report filename label (default: <cells>k_<genes>g)")
    parser.add_argument("--out", default="evals/reports", help="Report output directory")
    args = parser.parse_args()

    print(
        f"BioNexus scale benchmark: {args.cells:,} cells x {args.genes:,} genes @ density {args.density}",
        flush=True,
    )
    results = run_benchmark(
        args.cells,
        args.genes,
        args.seed,
        target_density=args.density,
        chunk_cells=args.chunk_cells,
        svd_k=args.svd_k,
    )
    report = {
        "schema_version": "bionexus.scale-benchmark.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine": machine_fingerprint(),
        "honesty": (
            "Zero-inflated structured synthetic Poisson counts measure the engineering "
            "envelope (throughput, memory) of the kernel stages. This is not biological "
            "validity and not a clinical performance claim. The committed run records its "
            "exact machine and memory class: a small-node run is not an HPC number. HPC "
            "reproduction: sbatch cluster/slurm/profiles/run_scale_benchmark.sbatch. Peak "
            "memory uses ru_maxrss on POSIX and the Windows peak working set elsewhere; "
            "the method is recorded alongside the value."
        ),
        **results,
    }
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = args.label or f"{args.cells // 1000}k_{args.genes // 1000}g"
    (out_dir / f"scale_benchmark_{label}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    machine = report["machine"]
    lines = [
        "# BioNexus Scale Benchmark",
        "",
        f"- Config: {args.cells:,} cells x {args.genes:,} genes (seed {args.seed}, density {args.density}, chunk {args.chunk_cells:,})",
        f"- Machine: {machine['platform']}, {machine['cpu_count']} cores, {machine['ram_total_gb']} GB RAM",
        f"- Total wall: **{results['total_wall_seconds']}s** | throughput: {results['throughput_cells_per_second']:,} cells/s"
        f" | peak memory: {results['peak_memory_gb']} GB ({results['peak_memory_method']})",
        f"- Observed density: {results['stages']['generate']['density_observed']} | nnz: {results['stages']['generate']['nnz']:,}",
        "",
        "| Stage | Wall (s) |",
        "|---|---|",
    ]
    lines += [f"| {k} | {v['wall_seconds']} |" for k, v in results["stages"].items()]
    lines += ["", report["honesty"], ""]
    (out_dir / f"scale_benchmark_{label}.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] report -> {out_dir}/scale_benchmark_{label}.json/.md", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
