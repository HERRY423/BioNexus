# BNS-019 Public Interoperability Trial 01

> Historical scope note (2026-09-01): this 0.1.0 trial preserves the original
> standalone Nextflow adapter fixture for reproducibility. It is not the current
> nf-core integration proposal. The current zero-touch proof of concept consumes
> an existing RO-Crate and annotates explicit artifact entities outside the
> pipeline; see `../ro-crate/`.

Trial ID: `BNS019-INTEROP-2026-01`  
Normative manifest: `trial-manifest.json`  
Initial state: `open_on_publication`

## Question

Can independently maintained implementations and common single-cell workflow
hosts consume the exact same BNS-019 registry release, agree on canonical
producer validation, and preserve one meaning-bearing envelope through host
round trips?

This is a software-contract question. It does not test biological correctness,
empirical calibration, scientific conclusions, or tool superiority.

## Frozen inputs

Every run must bind:

- standard `BNS-019` version `0.1.0`;
- release digest
  `b3164afe6ccd69dc9d7738c2ee58195ac65862701e29f9db1f98c12e1a97e934`;
- the unmodified producer conformance manifest and all five cases; and
- the trial manifest in this directory.

An implementation must verify the complete release manifest before reading the
registry. A copied enum table, a registry with a different digest, or a partial
file set is non-conformant.

## Tracks

1. **Independent validator**: implements producer validation without importing
   or invoking another submitted implementation. Python and R are reference
   trial entries, but neither is an external result.
2. **Host adapter**: preserves a canonical envelope through a real host object
   round trip. Scanpy/AnnData uses only `.uns`; Seurat uses only `@misc`.
3. **Workflow adapter**: verifies the release and transports the envelope in a
   real Nextflow execution using an nf-core-compatible module layout.

Adapter tracks may reuse a validator if disclosed. They do not increase the
count of independent validators.

## Required states

- `PASS`: every applicable check executed and matched.
- `FAIL`: a check executed and disagreed, mutated content, or failed closed.
- `NOT_RUN`: runtime, host, or dependency unavailable; never counted as pass.
- `ERROR`: the trial harness could not establish a valid conclusion.
- `INCOMPLETE`: no executed failure, but at least one required public gate is
  missing.

## Public success gate

The trial can be described as publicly demonstrated only after all of the
following are present in the public repository:

1. green public CI for every five track entries;
2. Python/R agreement for validity, normalized attributes, and failure class;
3. exact H5AD and RDS envelope round-trip checks;
4. a real Nextflow process result, not only its Python adapter core;
5. at least one reproducible implementation submitted by a party independent
   of BioNexus maintainers; and
6. immutable source commit, commands, environment, result JSON, and hashes.

Until then, the scoreboard remains `NOT_MET`. Maintainer self-tests are shown
separately and cannot satisfy the external gate.

## Submission and review

Open a pull request containing
`submissions/<submission_id>/submission.json` and
`results/<submission_id>.json`. The metadata must validate against
`schemas/submission.schema.json`. CI reruns applicable public fixtures. A
maintainer review records reproducibility and conflicts; it does not issue a
badge.

Submissions may be rejected for unsafe paths, mutable source references,
missing release verification, digest mismatch, hidden registry copies,
unreproducible execution, or claim inflation.

## Publication transition

Publishing the kit is an external action. On the first public commit that
enables the trial, change `publication_status` to `open`, set `opened_on`, and
update the scoreboard timestamp in the same reviewed change. Do not backdate
the trial or count local runs as public participation.
