#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# BioNexus three-gate chain for Slurm: preflight -> <analysis command> -> verify.
#
# Fail-closed semantics:
#   gate 1 (preflight)  exit 1 (refused/blocked) or 2 (missing evidence) -> job
#                       aborted BEFORE compute; sbatch job marked FAILED.
#   gate 2 (analysis)   your command; its exit code is propagated unchanged.
#   gate 3 (verify)     exit nonzero (ABSTAIN / CONFLICTED / unwarranted claim)
#                       marks the job FAILED even when compute succeeded, so a
#                       downstream --dependency=afterok chain cannot pick up
#                       unwarranted results.
#
# Usage inside a batch script:
#   bash run_three_gates.sh \
#     "/scratch/cohort.h5ad --intent differential-expression" \
#     "python my_analysis.py --input cohort.h5ad --out results/ledger.json" \
#     "results/ledger.json"
#
# Both gate commands may be prefixed with an image, e.g.
#   "apptainer exec --bind /scratch:/scratch bionexus.sif bionexus preflight ..."
# ---------------------------------------------------------------------------

set -uo pipefail

PREFLIGHT_ARGS="${1:?usage: run_three_gates.sh '<preflight args>' '<analysis command>' '<verify args>'}"
ANALYSIS_CMD="${2:?usage: run_three_gates.sh '<preflight args>' '<analysis command>' '<verify args>'}"
VERIFY_ARGS="${3:?usage: run_three_gates.sh '<preflight args>' '<analysis command>' '<verify args>'}"

echo "[gate 1/3] bionexus preflight ${PREFLIGHT_ARGS}"
bionexus preflight ${PREFLIGHT_ARGS}
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "[gate 1/3] PREFLIGHT exit ${rc}: computation blocked before it started." >&2
    exit "$rc"
fi
echo "[gate 1/3] preflight passed (exit 0)."

echo "[gate 2/3] analysis: ${ANALYSIS_CMD}"
bash -c "${ANALYSIS_CMD}"
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "[gate 2/3] ANALYSIS FAILED (exit ${rc}). Verify gate not reached." >&2
    exit "$rc"
fi
echo "[gate 2/3] analysis completed."

echo "[gate 3/3] bionexus verify ${VERIFY_ARGS}"
bionexus verify ${VERIFY_ARGS}
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "[gate 3/3] VERIFY exit ${rc}: results do not carry their claims. Job marked FAILED." >&2
    exit "$rc"
fi
echo "[gate 3/3] verification passed. All three gates green."
