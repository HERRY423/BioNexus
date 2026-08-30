#!/usr/bin/env bash
#SBATCH --job-name=bionexus-scale-bench
#SBATCH --account=<your-account>
#SBATCH --partition=<cpu-partition>
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=64G
#SBATCH --time=02:00:00
#SBATCH --output=logs/bionexus-bench-%j.out
#SBATCH --error=logs/bionexus-bench-%j.err

# ---------------------------------------------------------------------------
# HPC reproduction of the committed scale-benchmark evidence
# (evals/reports/scale_benchmark_*.json).
#
# The committed reports are single small-node runs (8 cores / 8 GB Windows
# node — see each report's machine fingerprint). Top-lab HPC evidence is
# this exact harness executed on your cluster: run this profile, then commit
# the produced report from logs/ as evals/reports/scale_benchmark_<label>.json
# with the node fingerprint it records. Adapt <...> placeholders first.
# ---------------------------------------------------------------------------

set -uo pipefail
mkdir -p logs

module purge
module load apptainer

IMAGE="/projects/<your-project>/containers/bionexus.sif"

# Same commands that produced the committed evidence (see each report's
# config block). Scale/density can be raised on larger-memory nodes — the
# harness is memory-bounded by construction (chunked generation + streaming
# HVG), so peak memory stays O(chunk x genes).
apptainer exec --bind "${SLURM_SUBMIT_DIR}":/work "${IMAGE}" \
    python /work/evals/scale_benchmark.py \
        --cells 500000 --genes 5000 --density 0.08 \
        --label 500k_5g_hpc --out /work/evals/reports

apptainer exec --bind "${SLURM_SUBMIT_DIR}":/work "${IMAGE}" \
    python /work/evals/scale_benchmark.py \
        --cells 1000000 --genes 5000 --density 0.05 \
        --label 1000k_5g_hpc --out /work/evals/reports
