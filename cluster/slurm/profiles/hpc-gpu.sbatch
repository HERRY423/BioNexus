#!/usr/bin/env bash
#SBATCH --job-name=bionexus-gpu-gates
#SBATCH --account=<your-account>
#SBATCH --partition=<gpu-partition>
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --mem=64G
#SBATCH --time=04:00:00
#SBATCH --output=logs/bionexus-gpu-%j.out
#SBATCH --error=logs/bionexus-gpu-%j.err

# ---------------------------------------------------------------------------
# Reference GPU profile: same BioNexus SIF, GPU node, driver injection.
#
# The GPU profile is the CPU image run with `--nv` (Apptainer injects the
# host CUDA driver); the locked Linux torch build carries CUDA kernels.
# Adapt the <...> placeholders, then:
#     mkdir -p logs results
#     sbatch cluster/slurm/profiles/hpc-gpu.sbatch
#
# Honest scope: NOT validated in CI (GitHub runners have no GPU). The image
# self-check asserts stack importability only — never that a GPU is present;
# torch.cuda.is_available() below is the node-level evidence.
# ---------------------------------------------------------------------------

set -uo pipefail
mkdir -p logs results

module purge
module load apptainer

IMAGE="/projects/<your-project>/containers/bionexus.sif"
export MPLBACKEND=Agg

# GPU profile: --nv injects host driver libraries into the container.
bn() {
    apptainer exec --nv --bind /scratch/${USER}:/scratch,"${SLURM_SUBMIT_DIR}":/work "${IMAGE}" bionexus "$@"
}

bn doctor --require-scverse || exit 1

# Node-level GPU evidence: recorded in the job log, asserted as available.
apptainer exec --nv --bind /scratch/${USER}:/scratch "${IMAGE}" \
    python -c "import torch; assert torch.cuda.is_available(), 'GPU allocated but torch.cuda unavailable: --nv/driver mismatch'; print('cuda OK:', torch.cuda.get_device_name(0))" || exit 1

# GPU-stage workloads (scvi-tools VAE, foundation-model inference) go here.
# The three-gate chain is unchanged; the analysis command simply runs under --nv.
