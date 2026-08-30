#!/usr/bin/env bash
#SBATCH --job-name=bionexus-cpu-gates
#SBATCH --account=<your-account>
#SBATCH --partition=<cpu-partition>
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=logs/bionexus-cpu-%j.out
#SBATCH --error=logs/bionexus-cpu-%j.err

# ---------------------------------------------------------------------------
# Reference CPU profile: three-gate analysis on a generic HPC CPU node.
# Adapt the <...> placeholders (account, partition, project paths), then:
#     mkdir -p logs results
#     sbatch cluster/slurm/profiles/hpc-cpu.sbatch
# This is a reference profile, not a validated site configuration — module
# names and scheduler behaviors are site-specific (see cluster/slurm/README).
# ---------------------------------------------------------------------------

set -uo pipefail
mkdir -p logs results

module purge
module load apptainer   # or singularity, per your cluster

IMAGE="/projects/<your-project>/containers/bionexus.sif"
export MPLBACKEND=Agg

# CPU profile: no --nv flag.
bn() {
    apptainer exec --bind /scratch/${USER}:/scratch,"${SLURM_SUBMIT_DIR}":/work "${IMAGE}" bionexus "$@"
}

# Deployment self-check (fails the job on a broken image / wrong site paths).
bn doctor --require-scverse || exit 1

# Offline deployment profile (delete on clusters that allow egress):
export BIONEXUS_OFFLINE=1
bn offline-check || exit 1

# Three gates around the analysis (see bionexus_three_gates.sbatch):
bash /work/cluster/slurm/run_three_gates.sh \
    "/work/data/flagship/kang2018_pbmc_ifnb/pbmc_ifnb_counts.h5ad --intent differential-expression" \
    "apptainer exec --bind /scratch/${USER}:/scratch,\"${SLURM_SUBMIT_DIR}\":/work \"${IMAGE}\" python /work/scripts/run_pseudobulk_de_analysis.py --input /work/data/flagship/kang2018_pbmc_ifnb/pbmc_ifnb_counts.h5ad --out /work/results" \
    "/work/results/claim_ledger.json"
