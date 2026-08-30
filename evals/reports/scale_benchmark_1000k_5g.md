# BioNexus Scale Benchmark

- Config: 1,000,000 cells x 5,000 genes (seed 20260830, density 0.05, chunk 10,000)
- Machine: Windows-10-10.0.19041-SP0, 8 cores, 8.0 GB RAM
- Total wall: **482.069s** | throughput: 2,074 cells/s | peak memory: 4.13 GB (windows_peak_working_set_psutil)
- Observed density: 0.0501 | nnz: 250,614,499

| Stage | Wall (s) |
|---|---|
| generate | 357.716 |
| qc_mask | 4.526 |
| normalize_log1p | 5.182 |
| hvg_select | 5.428 |
| pca | 109.217 |

Zero-inflated structured synthetic Poisson counts measure the engineering envelope (throughput, memory) of the kernel stages. This is not biological validity and not a clinical performance claim. The committed run records its exact machine and memory class: a small-node run is not an HPC number. HPC reproduction: sbatch cluster/slurm/profiles/run_scale_benchmark.sbatch. Peak memory uses ru_maxrss on POSIX and the Windows peak working set elsewhere; the method is recorded alongside the value.
