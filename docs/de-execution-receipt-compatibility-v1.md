# DE execution receipt compatibility v1

The machine-readable contract is packaged at
`bionexus/data/de_execution_receipt_compatibility_v1.json`.

## Supported representations

A complete execution binding always requires a recognized biological replicate
unit, method, successful fit status, bounded design formula, design-matrix
column names, positive donor count, and a SHA-256 bound result file.

Donors can be bound in either of two ways:

1. **Explicit IDs:** the receipt contains a unique nonempty string list whose
   set exactly matches the supplied metadata.
2. **Legacy hash-bound metadata:** the receipt omits the `donor_ids` key but
   contains `sample_metadata_sha256`, and the caller supplies the original CSV
   or TSV file whose exact bytes match that digest. The parsed table must equal
   the table audited and its donor count must equal `n_donors`.

The legacy path does not accept an in-memory DataFrame because it has no
recoverable original bytes. It also does not repair a present but malformed or
conflicting `donor_ids` value. Historical receipts remain unchanged.

`COMPLETE` and `COMPLETED` are accepted success-status synonyms. Unknown,
missing and explicit failure states do not pass.

## Failure behavior

Missing evidence stays visible as `MISSING_EVIDENCE`. Contradictions stay
`ISSUE_FOUND`. A malformed, all-zero or mismatched sample metadata digest emits
the `BFA-013e` blocker. Failed model status, result-table hash mismatch, design
conflict and donor-count mismatch retain their existing blocker behavior.

## Evidence boundary

Successful binding proves only that the supplied result, receipt fields and
sample metadata are mutually consistent under this bounded parser. It does not
authenticate the producer, prove that the declared model ran, validate the
biological conclusion, establish independent replication, or authorize
clinical or regulatory use.
