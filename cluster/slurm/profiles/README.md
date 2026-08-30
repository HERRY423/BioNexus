# Slurm reference profiles

| Profile | Purpose | CI-validated |
|---|---|---|
| `hpc-cpu.sbatch` | Three-gate analysis on a generic CPU node + offline deployment gate | gate semantics yes (bash tests); live scheduler no |
| `hpc-gpu.sbatch` | Same SIF on a GPU node via `--nv`, with node-level CUDA evidence | no (CI has no GPU) |
| `run_scale_benchmark.sbatch` | HPC reproduction of the committed scale-benchmark evidence | harness yes; HPC execution site-side |

All `<...>` placeholders (account, partition, project paths) are site
adaptation. See `../README.md` for the honest scope of what is and is not
validated, and `container/DEPLOYMENT_MANIFEST.json` for the deployment
evidence ledger (digests, lockfile, SBOM, benchmark provenance).
