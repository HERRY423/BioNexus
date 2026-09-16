# BN-DE-RETENTION-GUARD-20260914

## Purpose

Engineering regression study for the current BioNexus working candidate. It
tests whether the candidate can retain the 12 developer-labelled valid cases in
the frozen 09-08 challenge while continuing to reject and correctly flag all 42
developer-labelled invalid cases.

This is a post-outcome remediation check on developer-authored labels. It is not
an independent expert study, external validation, laboratory net-benefit trial,
or scientific authorization.

## Frozen inputs

- Cases: `review/methods-experiments-2026-09-08/run-01/challenge/cases/`
- Exactly 54 case folders: 12 valid and 42 invalid.
- The runner records SHA-256 for every `case.json`, `receipt.json`, `metadata.csv`,
  `design.csv`, and `de.csv` file before execution.
- No frozen input is edited or copied back over its source.

## Candidate call

For every case, call the snapshotted candidate engine with:

- `de_table=<case>/de.csv` as a file path;
- `sample_metadata=<case>/metadata.csv` as a file path;
- the unmodified parsed `receipt.json` object;
- the unmodified claim text;
- `donor_col="donor"`, `condition_col="condition"`.

Using the original sample-sheet path is part of the intended interface under
test. It lets a legacy receipt without `donor_ids` use its existing
`sample_metadata_sha256` only when the supplied file bytes match exactly. An
in-memory DataFrame remains insufficient for that compatibility path.

## Predefined endpoints

Acceptance means `overall_status == ROBUST_PASS`.

The engineering gate passes only if all three conditions hold:

1. valid retention = 12/12;
2. unsupported acceptance = 0/42;
3. every invalid case has at least one `HIGH_IMPACT` or `BLOCKER` finding = 42/42.

No threshold may be lowered after seeing the run. A failed run is retained as a
failed run and any follow-up uses a new output directory.

## Evidence ceiling

Passing this gate supports a local regression claim for these 54 frozen,
developer-labelled cases and this exact candidate source snapshot. It does not
estimate performance on new claims, prove label correctness, authenticate the
original analysis producer, prove the recorded model really ran, establish
scientific validity, or demonstrate benefit in a real laboratory workflow.
