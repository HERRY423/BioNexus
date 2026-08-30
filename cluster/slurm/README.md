# Slurm deployment: three gates around every analysis

BioNexus's firewall entry points — `bionexus preflight` (before compute),
`bionexus audit` (static rule engine over scripts/notebooks), `bionexus verify`
(results against their Claim–Evidence Ledger) — chain into Slurm jobs so that
**a refused preflight cancels compute, and rejected results fail the verify
job** even when the compute itself succeeded.

## Contents

| File | Purpose |
|---|---|
| `run_three_gates.sh` | Gate-chain runner: preflight → analysis → verify with exact exit-code propagation. Tested by `tests/unit/test_slurm_gates.py` (real bash, stub CLI). |
| `bionexus_three_gates.sbatch` | Single-job sbatch template running all three gates inside the Apptainer image. |
| `submit_dependency_chain.sh` | Slurm-native alternative: three dependent jobs (`--dependency=afterok`), one gate per job. |
| `profiles/hpc-cpu.sbatch` | Reference CPU profile: doctor -> offline deployment gate -> three-gate chain. |
| `profiles/hpc-gpu.sbatch` | Reference GPU profile: same SIF via `--nv`, with node-level CUDA evidence. |
| `profiles/run_scale_benchmark.sbatch` | HPC reproduction of the committed scale-benchmark evidence (evals/reports/). |

## Key properties

1. **Preflight exit 1/2 aborts before compute.** In the dependency-chain form,
   a FAILED preflight job cancels the `afterok` analysis job at the scheduler
   level — refused science never reaches a compute node.
2. **Verify failure fails the job.** If the results ledger carries claims
   beyond their evidence (ABSTAIN / CONFLICTED / unwarranted causal language),
   the verify job exits nonzero so downstream `--dependency=afterok` chains
   cannot consume unwarranted results.
3. **Exit codes propagate unchanged** — gate semantics (0 proceed incl.
   capped/degraded, 1 refused/blocked, 2 missing evidence) are the
   `bionexus preflight` fail-closed table (BNS-AD-014) verbatim.

## Honest scope: what is and is not validated

- **Validated**: the gate-chain semantics of `run_three_gates.sh` (exit-code
  propagation, short-circuit behavior) are covered by real bash tests; the
  three `bionexus` entry points and the container self-check run in CI
  (`.github/workflows/container.yml` builds the SIF and smoke-runs a gate on
  real committed data).
- **Not validated in CI**: submission against a *live Slurm scheduler*
  (`sbatch`/`squeue` behavior, module names, partition/account placeholders).
  The `<...>` placeholders in the templates must be adapted per site. If your
  cluster's scheduler behaves differently (e.g. `afterok` cancellation
  policies with `--kill-on-invalid-dependency`), verify the chain with a
  two-minute dry run before production use.
