# Independent pseudobulk validation track

This directory contains the preregistered donor/platform holdout study
`BN-PB-IV-002`. It evaluates whether donor-aware PyDESeq2 results reproduce a
shared interferon-response direction across an independent 10x cohort and a
Parse split-pool cohort.

It does **not** establish clinical validity, causality, cell-type identity, or
method superiority. The Parse input is a documented 10K-cell subsample and no
independent analyst attestation is present, so even a statistically passing run
would be capped at `PRELIMINARY` and the full independent-blinded claim would
remain `ABSTAIN`.

## Reproduce

1. Run the BioNexus Reliability environment gate:

   `python scripts/doctor.py --require-scverse`

2. Materialize the two preregistered raw-count h5ad files at the paths recorded
   in `PREREGISTRATION.json`.

3. Execute:

   `python evals/pseudobulk_independent_validation.py`

The run verifies the preregistration hash before reading outcomes, aggregates
raw counts by donor and condition, runs PyDESeq2, performs leave-one-donor-out
direction checks, evaluates the independent platform, and executes the locked
paired-donor sign-flip negative control.

## Current result

The donor holdout, platform holdout, and multi-cohort direction endpoints pass.
The preregistered negative control does not: empirical `p = 0.05859375` with
255 locked permutations, above the `0.05` threshold. The retained result is
therefore `negative_result / FRAGILE / independent biological validation not
supported`.

Do not increase the permutation count or change the threshold under this study
identifier. A new analysis requires a new preregistration and study ID.
