# BioNexus Scale Benchmark

- Config: 30,000 cells x 5,000 genes (seed 20260830)
- Machine: {'platform': 'Windows-10-10.0.19041-SP0', 'python': '3.13.14', 'machine': 'AMD64', 'ram_total_gb': 8.0, 'cpu_count': 8}
- Total wall: **84.374s** | throughput: 356 cells/s | peak RSS: nan GB

| Stage | Wall (s) |
|---|---|
| generate | 14.807 |
| qc_mask | 0.532 |
| normalize_log1p | 3.9 |
| hvg_select | 2.705 |
| pca | 62.43 |

Structured synthetic Poisson counts measure the engineering envelope (throughput, memory) of the kernel stages. This is not biological validity and not a clinical performance claim. Peak RSS uses ru_maxrss on POSIX; on Windows it is not reported.
