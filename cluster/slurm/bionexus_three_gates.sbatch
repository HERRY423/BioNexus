#!/usr/bin/env bash
#SBATCH --job-name=bionexus-three-gates
#SBATCH --account=<your-account>
#SBATCH --partition=<compute-partition>
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/bionexus-%j.out
#SBATCH --error=logs/bionexus-%j.err

# ---------------------------------------------------------------------------
# Three-gate BioNexus analysis inside the Apptainer image.
# Fill in <...> placeholders and the three GATE lines, then:
#     mkdir -p logs results
#     sbatch bionexus_three_gates.sbatch
# ---------------------------------------------------------------------------

set -uo pipefail
mkdir -p logs results

module purge
module load apptainer   # or singularity, per your cluster

IMAGE="/projects/<your-project>/containers/bionexus.sif"
export MPLBACKEND=Agg

# Bind every path the gates and the analysis touch (read-only for inputs).
SIF_BINDS="--bind /scratch/${USER}:/scratch,${SLURM_SUBMIT_DIR}:/work"

bn() {
    apptainer exec ${SIF_BINDS} "${IMAGE}" bionexus "$@"
}

# GATE 1: preflight — replace the data path/intent with your declared analysis.
# GATE 2: your analysis command (here: the gold-chain pseudobulk DE runner).
# GATE 3: verify — point at the results ledger your analysis wrote.
PREFLIGHT_ARGS="/work/data/flagship/kang2018_pbmc_ifnb/pbmc_ifnb_counts.h5ad --intent differential-expression"
ANALYSIS_CMD="apptainer exec ${SIF_BINDS} ${IMAGE} python /work/scripts/run_pseudobulk_de_analysis.py --input /work/data/flagship/kang2018_pbmc_ifnb/pbmc_ifnb_counts.h5ad --out /work/results"
VERIFY_ARGS="/work/results/claim_ledger.json"

bash /work/cluster/slurm/run_three_gates.sh \
    "${PREFLIGHT_ARGS}" \
    "${ANALYSIS_CMD}" \
    "${VERIFY_ARGS}"
