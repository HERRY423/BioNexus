# DE review bundle compatibility

This is the bounded consumer contract for the first DE shadow-review product.
It covers file transport and interpretation, not scientific validity. The
project remains a release candidate; this contract does not declare GA status.
The integrity reader and additive writer fields are currently Unreleased in the
development checkout, not features already shipped in the public rc.5 artifact.

## Supported entry points

| Surface | Behavior |
|---|---|
| `audit-de --bundle NEW_DIRECTORY` | Read caller-supplied analysis artifacts and emit a new directory; never overwrite old evidence |
| `audit-de-verify DIRECTORY` | Read local reports and emit versioned JSON; no execution, networking or file changes |
| `audit-de-summary REVIEW...` | Describe human observations with negative, missing and legacy limits retained |
| Python reader | `bionexus.de_bundle.verify_de_bundle(path, expected_manifest_sha256=None)` |
| Standalone reader | `python -S src/bionexus/de_bundle.py DIRECTORY`; standard library only, bypassing package initialization |

Existing `audit-de` flags/aliases and exit codes remain: 0 means the audit engine
returned ROBUST_PASS; 1 means a non-pass or execution error. Those are not
scientific authorization. Internal Python APIs, rule wording and thresholds
remain subject to scientific correction, with changes disclosed in release notes.

## Reader status and exit codes

| Status | Exit | Meaning |
|---|---:|---|
| CONSISTENT | 0 | Three immutable reports match their manifest; audit status is structurally consistent |
| INVALID | 1 | Missing/changed/malformed file, incomplete profile, inconsistent status or anchor mismatch |
| UNSUPPORTED_SCHEMA | 2 | Unknown bundle, profile or status; do not infer success |
| LEGACY_LIMITED | 3 | Historical v1 binds audit.json only; human-readable reports are not verified |

All results declare scientific_authorization=NONE,
analysis_execution_verification=NOT_PERFORMED,
input_content_verification=NOT_PERFORMED, producer_authentication=NOT_ESTABLISHED
and mutable_reviews=NOT_VERIFIED. CONSISTENT never endorses an audit's biological
conclusion or verifies an actual statistical fit.

## Additive v1 fields

New manifests retain `schema: bionexus.de-shadow-bundle.v1` and `audit_sha256`.
They add `integrity_profile: bionexus.de-shadow-integrity.v1` plus
`immutable_artifacts`, binding exactly `audit.json`, `audit-full.md` and
`REVIEW.md` as raw UTF-8 bytes. Both fields must occur together. Old readers may
ignore these additive fields. New readers give old packages LEGACY_LIMITED,
without filling gaps or rewriting history. Summaries expose that status per case.
Additional top-level fields grant no authority. Unknown enum meanings need a
new supported contract revision; consumers must never treat them as success.

The packaged JSON schemas are `bionexus/data/de-shadow-bundle.schema.json` and
`bionexus/data/de-bundle-verification.schema.json`. Mutable `review.json` and
`reference-review.json` remain editable. Their contents are validated separately
by pilot summaries, not authenticated by the bundle reader.

## External digest and resource limits

Retain a manifest digest independently at handoff and compare it on receipt:

```text
bionexus audit-de-verify path/to/review --expected-manifest-sha256 <64-lowercase-hex-digits>
```

Without this caller-supplied anchor, rewriting both files and hashes can produce
an internally consistent bundle. A digest match does not establish the identity
or trustworthiness of its source. Removing the new fields without an anchor
returns LEGACY_LIMITED, never CONSISTENT.

The reader uses fixed filenames, rejects symlinks/path escapes, duplicate JSON
keys and non-finite numbers, and limits each immutable report/manifest to 8 MiB.
It never dereferences raw-data paths or fetches links. Verify a quiescent local
copy with normal filesystem controls; this is not protection against concurrent
hostile filesystem changes. Matrices remain outside the small report envelope.

## Compatibility evidence and migration

`tests/fixtures/de_bundle_legacy_v1` is a byte-frozen, previously executed local
synthetic pilot bundle. Preserve it as historical transport evidence, not
scientific ground truth. CI checks legacy reading, new writes, tampering,
unknown schemas, authority limits and read-only behavior. Release checks repeat
the reader checks against the actual installed wheel outside the source tree.

Never silently migrate an old assessment. Create a new audit directory with a
pinned version when reassessment is needed; retain old reports, input digests
and the rule-change explanation. A breaking consumer change requires migration
guidance, a new contract identifier and old/new fixtures. See
[maintenance policy](../MAINTENANCE.md).
