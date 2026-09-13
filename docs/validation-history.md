# Historical reports and new execution evidence

`scripts/sync_flagship_reports.py` is now a read-only inventory. Its former
metadata rewriting API raises an error. `--output NEW_FILE` writes a separate
assessment with exclusive creation; it never updates reports, execution times,
source hashes, dirty flags or generator identities.

The original eleven rollups were copied byte for byte to
`validation/history/pre-ga-provenance-01/`. Their manifest binds archived bytes.
Because the previous synchronizer could rewrite their identity without running
an analysis, their original execution authenticity is NOT_ESTABLISHED. They
remain inspectable; their numerical results are not relabeled as wrong or as
newly validated. The strict validation verifier rejects these quarantined
reports as evidence of a fresh execution.

The strict verifier additionally requires a completed local run receipt with
matching source snapshots and exact changed output bytes. Rewriting only a
timestamp, version or digest cannot satisfy that check. A completed run with an
unchanged report, failed exit or source change cannot supply the missing receipt.

Validation runner entry points create a fresh `validation/runs/<run-id>/`
capsule before executing. Each capsule retains the complete available
validation files before and after the attempt, SHA-256 inventories, changed
and deleted paths, actual return/error state and before/after source snapshots.
Top-level report paths remain compatibility views; the capsule retains their
prior bytes and the new output separately. An unchanged report in the after
inventory is explicitly not a new result. Failed attempts are retained too.

The capsule is a local process record, not producer authentication, independent
replication or an externally immutable log. A process kill can leave an
incomplete directory without a receipt; that is incomplete evidence, never a
successful run. Source changes during execution invalidate the candidate.
An exclusive writer lock prevents concurrent runners from attributing each
other's output. A killed process leaves its lock in place: retain and inspect
the incomplete capsule, confirm the writer has stopped, then explicitly remove
the lock before retrying. The runner never clears a stale lock automatically.
External consumers should retain the receipt/file digests independently.

Use the actual runners for fresh evidence. Never copy new source identifiers
into historical JSON to silence drift checks. A source-applicability assessment
may reference old results, but it cannot change which source executed them.
CI preserves run capsules as separate artifacts even when a run fails.
