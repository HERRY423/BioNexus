# Two-phase independent-review blinding protocol

This protocol makes the IVN `blinded=true` field auditable without pretending
that a public source repository can conceal its identity forever. It is a
self-attested, hash-bound pre-output design; it is not double blinding.

## Phase 1 — lock before system output

1. The maintainer sends only `BLINDED_REVIEW_PACKET.json` and an assigned
   review ID. The reviewer must not open the repository, README, CI results,
   validation reports, or prior BioNexus output before locking this phase.
2. The reviewer verifies and records the packet SHA-256, copies
   `PREOUTPUT_ASSESSMENT_TEMPLATE.json` to `PREOUTPUT_ASSESSMENT.json`, and
   fills every field.
3. The reviewer records an ISO-8601 `locked_at`, signs by name, computes the
   completed file's SHA-256, and retains that unchanged file.

If the reviewer has already seen BioNexus outputs, this protocol is not met.
They may still provide a valuable unblinded review, but `blinded` and
`system_outputs_unseen_until_lock` must remain `false`, so it will not count
toward the current blinded-review quota.

## Phase 2 — unblind, reproduce, and challenge

1. Only after the Phase 1 lock, the reviewer receives the immutable Git commit
   and runs the reproduction command.
2. The reviewer inspects every capsule log, including non-zero results, and
   actively attacks the precommitted rules.
3. The reviewer returns both unchanged artifacts:
   `PREOUTPUT_ASSESSMENT.json` and a completed `REVIEW.json` copied from
   `SIGNOFF_TEMPLATE.json`.

The final `REVIEW.json` binds the blinded packet, pre-output assessment,
immutable commit, capsule, identity, disclosures, scientific judgment, and
signature. The maintainer registers a separate ledger record and may promote
it only through `bionexus ivn verify-review`, which creates a distinct
hash-bound verification receipt.
