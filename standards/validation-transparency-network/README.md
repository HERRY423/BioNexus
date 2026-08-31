# Validation Transparency Network development contract

This directory is the language-neutral interchange surface for BNS-023. A
producer creates a validation-event packet, signs the exact packet with an
authorized `bns-validation-event` key, and obtains a second signature from a
distinct assessor authorized for `bns-independence-assessment`.

The BioNexus reference implementation can admit those packets into a portable
JSONL hash chain and deterministically derive candidate evidence-slot counts.
Consumers should derive state through `compute_state_from_log`, supplying both a
trust registry and an independently retained expected log head; the pure reducer
is not a substitute for chain and signature verification.
It does not operate a public transparency service, establish real-world
institutional identity, certify implementations, or replace Human Scientific
Adjudication. A SCITT or in-toto envelope remains an interoperability direction
until exercised against an external conforming implementation.
