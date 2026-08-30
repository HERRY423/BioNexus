#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Slurm-native three-gate dependency chain.
#
# Instead of one job running all three gates, submit three dependent jobs so
# each gate gets its own resources, logs, and sbatch state:
#
#   JOB1 preflight  -> JOB2 analysis (--dependency=afterok:JOB1)
#                      -> JOB3 verify (--dependency=afterok:JOB2)
#
# Property: if preflight refuses, JOB2 never starts (afterok on a FAILED job
# is cancelled by the scheduler); if verify rejects the results, JOB3 fails
# and nothing downstream of *it* may consume the results. Submit:
#
#   bash submit_dependency_chain.sh
# ---------------------------------------------------------------------------
set -euo pipefail

IMAGE="/projects/<your-project>/containers/bionexus.sif"
DATA=/scratch/${USER}/cohort.h5ad
LEDGER=/scratch/${USER}/results/claim_ledger.json

module purge && module load apptainer

echo "== [1/3] submitting preflight gate =="
J1=$(sbatch --parsable --job-name=bn-preflight --mem=16G --time=00:30:00 \
    --wrap="apptainer exec ${IMAGE} bionexus preflight ${DATA} --intent differential-expression")
echo "   preflight job: ${J1}"

echo "== [2/3] submitting analysis (afterok:${J1}) =="
J2=$(sbatch --parsable --job-name=bn-analysis --cpus-per-task=8 --mem=64G --time=04:00:00 \
    --dependency="afterok:${J1}" \
    --wrap="apptainer exec ${IMAGE} python /work/scripts/run_pseudobulk_de_analysis.py --input ${DATA} --out /scratch/${USER}/results")
echo "   analysis job: ${J2}"

echo "== [3/3] submitting verify gate (afterok:${J2}) =="
J3=$(sbatch --parsable --job-name=bn-verify --mem=4G --time=00:20:00 \
    --dependency="afterok:${J2}" \
    --wrap="apptainer exec ${IMAGE} bionexus verify ${LEDGER}")
echo "   verify job: ${J3}"

echo "Chain: ${J1} -> ${J2} -> ${J3}"
echo "squeue -j ${J1},${J2},${J3}   # a FAILED preflight cancels the rest"
