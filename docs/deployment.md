# Lab-Grade Deployment Guide

Everything a computing core or laboratory needs to run BioNexus as a
reproducible, air-gap-capable deployment on HPC or workstation hardware —
with an honest ledger of what is machine-verified evidence versus site
adaptation. The single source of truth for deployment artifacts is
[`container/DEPLOYMENT_MANIFEST.json`](../container/DEPLOYMENT_MANIFEST.json)
(digest drift and SBOM/lockfile consistency are CI- and test-enforced).

## 1. Reproducible image: digest-pinned base + hashed lockfile

`container/apptainer.def` pins two layers:

- **Base image by OCI digest**: `From: python@sha256:0bee7276...` — CI
  re-resolves `python:3.11-slim-bookworm` from Docker Hub on every build and
  fails when the digest no longer matches, so a silently moved base can never
  produce a "rebuilt identical" image.
- **Python stack from a lockfile**: `container/requirements-lock.txt` pins
  208 packages to exact versions with wheel SHA-256 hashes (compiled via
  `uv pip compile --python-version 3.11 --generate-hashes`, command recorded
  in the manifest). pip's hash-checking mode verifies every wheel at install
  time — which doubles as the offline supply-chain control. The bionexus
  source tree installs with `--no-deps -e .` on top.

Rebuild:

```bash
apptainer build bionexus.sif container/apptainer.def
apptainer exec bionexus.sif bionexus doctor --json
apptainer exec bionexus.sif bionexus offline-check --enforce
```

The build fails closed: a broken import, missing backend, or failed offline
gate means no image exists. CI (`.github/workflows/container.yml`) performs
the build, digest verification, firewall-entry-point checks, a preflight
smoke gate on committed real data, and records the SIF SHA-256 with the
release.

## 2. SBOM

`container/sbom-python.json` is a CycloneDX 1.5 SBOM of the exact locked
versions the image installs (209 components — not pyproject specifiers):

```bash
python scripts/generate_sbom.py --from-lockfile container/requirements-lock.txt \
    -o container/sbom-python.json
```

CI regenerates it inside the built image and asserts component-level
equality with the committed file — an SBOM that does not describe the image
is treated as drift, not documentation.

## 3. Offline mode (air-gapped labs / HPC)

`BIONEXUS_OFFLINE=1` is the deployment-level switch: it forces the
`OFFLINE_STRICT` egress mode — zero external HTTP, zero hosted MCP endpoints
— regardless of any other configuration, and cannot be relaxed at runtime
(`DataGovernanceGuard.set_mode` refuses while the flag is set). Core
workflows (doctor, replay-provider evals, local zero-key MCP tools, the
three firewall gates, the scale benchmark) run without touching the network.

```bash
bionexus offline-check --enforce          # deployment gate (exit 1 = not ready)
bionexus doctor --offline                 # full doctor + offline profile section
```

The gate verifies: the flag forces `OFFLINE_STRICT`, the replay eval
provider is available (evals without provider APIs), the local MCP server is
available, and every hosted endpoint is refused *by policy before any
connection attempt*. It runs inside the container `%test` and in the Slurm
reference profiles.

## 4. CPU / GPU profiles

One image, two run profiles (the locked Linux torch build carries CUDA
kernels; Apptainer injects the host driver):

| Profile | Invocation | Evidence |
|---|---|---|
| CPU | `apptainer exec bionexus.sif bionexus ...` | CI-validated end to end |
| GPU | `apptainer exec --nv bionexus.sif bionexus ...` | node-level: `torch.cuda.is_available()` asserted in the job log; not CI-validated (no GPU in CI) |

`bionexus doctor` reports the active backend tier either way; the GPU
profile's honest scope (driver injection, node allocation) is documented in
`cluster/slurm/profiles/hpc-gpu.sbatch`.

## 5. Slurm reference profiles

| File | Purpose |
|---|---|
| `cluster/slurm/profiles/hpc-cpu.sbatch` | CPU node: doctor → offline gate → three-gate chain |
| `cluster/slurm/profiles/hpc-gpu.sbatch` | GPU node via `--nv`, with node-level CUDA evidence |
| `cluster/slurm/profiles/run_scale_benchmark.sbatch` | HPC reproduction of the scale-benchmark evidence |

All `<...>` placeholders (account, partition, module names, project paths)
are site adaptation — submission against a live scheduler is intentionally
not claimed as CI-validated (see `cluster/slurm/README.md`).

## 6. Scale benchmark: executed evidence, honestly labeled

The harness (`evals/scale_benchmark.py`) is **memory-bounded by
construction** — chunked sparse generation, in-place CPM/log1p, streaming
HVG — so peak memory is O(chunk × genes). Committed, really executed
reports (each records its machine fingerprint, wall time per stage, peak
memory with measurement method, and observed matrix density):

| Report | Scale | Machine class | Result |
|---|---|---|---|
| `scale_benchmark_30k_5g.json` | 30k × 5k @ 8% nonzero | small single node (8 cores / 8 GB) | 16.6 s, peak 0.87 GB |
| `scale_benchmark_500k_5g.json` | 500k × 5k @ 8% nonzero | small single node (8 cores / 8 GB) | 278 s, peak 3.75 GB |
| `scale_benchmark_1000k_5g.json` | 1M × 5k @ 5% nonzero | small single node (8 cores / 8 GB) | 482 s, peak 4.13 GB |

Honest labeling, stated in every report and in the manifest:

- These are **real executed runs** of the committed harness on a small
  8-core / 8 GB node — the synthetic counts measure the engineering
  envelope (throughput, memory), never biological validity, and a small-node
  run is **not an HPC number**.
- What the runs prove: the 500k–1M-cell pipeline is memory-feasible on
  commodity nodes because generation/normalization/HVG never materialize the
  dense matrix (the previous harness's 500k-cell "cluster reference" — a
  ~78%-dense Poisson draw — was not actually runnable anywhere).
- What they do not prove: top-lab HPC evidence requires running
  `cluster/slurm/profiles/run_scale_benchmark.sbatch` on the target cluster
  and committing the node's report. The harness records the machine
  fingerprint, so the committed report is the evidence.

## 7. Adoption boundary

A pinned digest, hash-verified lockfile, SBOM, offline gate, or benchmark
report is **deployment engineering evidence**. It is not independent
scientific validation (that is the BNS-023 Independent Validation Network's
quota: ≥ 3 independent datasets × ≥ 2 external labs × ≥ 1 non-author
reviewer, with frozen calibration profiles) and not institutional adoption
or endorsement.
