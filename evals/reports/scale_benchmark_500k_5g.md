# BioNexus Scale Benchmark

- Config: 500,000 cells x 5,000 genes (seed 20260830, density 0.08, chunk 10,000)
- Machine: Windows-10-10.0.19041-SP0, 8 cores, 8.0 GB RAM
- Total wall: **278.134s** | throughput: 1,798 cells/s | peak memory: 3.745 GB (windows_peak_working_set_psutil)
- Observed density: 0.0802 | nnz: 200,488,896

| Stage | Wall (s) |
|---|---|
| generate | 190.025 |
| qc_mask | 1.725 |
| normalize_log1p | 3.814 |
| hvg_select | 4.699 |
| pca | 77.871 |

Zero-inflated structured synthetic Poisson counts measure the engineering envelope (throughput, memory) of the kernel stages. This is not biological validity and not a clinical performance claim. The committed run records its exact machine and memory class: a small-node run is not an HPC number. HPC reproduction: sbatch cluster/slurm/profiles/run_scale_benchmark.sbatch. Peak memory uses ru_maxrss on POSIX and the Windows peak working set elsewhere; the method is recorded alongside the value.
