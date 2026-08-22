# BioNexus Spatial Empirical Gold Program

This program is intentionally restricted to cell-resolved imaging spatial
transcriptomics on **Xenium, CosMx, and MERSCOPE**. It calibrates the BioNexus
Spatial Alternative Explanation Battery; it does not add another omics
capability or provide a generic vendor analysis pipeline.

`program.json` is a zero-threshold program registry. It defines the eligible
platforms, battery metrics, evidence requirements, split policy, and current
coverage gaps. No platform study or approved profile is packaged yet, so the
program status is `incomplete_not_claim_ready`.

Real calibration work enters through:

1. a preregistered study manifest conforming to
   `schemas/study-manifest.schema.json`;
2. an immutable observation table conforming to
   `schemas/observations.schema.json` whose rows bind a battery-run digest and
   independent adjudication record; every one of those digests must be
   re-computed from supplied bytes before fitting, and each versioned JSON
   envelope must match the row's study, platform, metric, donor, FOV,
   partition, score/outcome, adjudicator, and protocol;
3. donor- and FOV-disjoint calibration/validation partitions;
4. one platform, tissue, task, metric, and versioned evidence source per
   candidate profile; and
5. external review plus a target-bound Ed25519 attestation whose configured
   trust key, expiry, artifact binding, and signed revocation state all verify
   before runtime use.

Synthetic fixtures may test software behavior but are forbidden as production
study provenance. Platforms are never pooled to manufacture sample size or a
universal threshold.

Use `bionexus-spatial-gold inventory`, `validate-study`, `verify-artifacts`, and
`validate-observations` for machine-readable audits. Verification reads the
artifact bytes; a manifest declaration alone is not candidate-fit evidence.
`verify-artifacts` only produces a fit-eligible receipt when both
`--observation-set` and `--record-artifact-map` are supplied. Record-map keys
are exactly `<record_id>:battery_run` and
`<record_id>:adjudication_record`.

At runtime a generic `APPROVED` calibration profile is ignored. Positive
warrant requires an `externally_validated` program and platform, re-verification
of the `program.json` bytes, exact membership, the approved profile artifact
bytes (keyed by `<profile_id>@<version>`), every bound real-study manifest, and
a verified unexpired, unrevoked `spatial-gold-profile-approval` attestation.
Missing or mismatched material remains
`GOLD_PROGRAM_AUTHORIZATION_REQUIRED`.
