# Scientific Trust Reset — Phase 1

**Status:** implemented development baseline (2026-08-21)

Phase 1 removes claims that the repository cannot independently verify and makes
missing trust evidence fail closed.

## Production trust boundary

- `rule_registry.json` is a `DEVELOPMENT_UNVERIFIED` proposition registry. Packaged
  dataset/platform calibration claims, sensitivity results, named reviewers,
  endorsements, and accepted challenges are empty.
- The empirical warrant registry remains explicit: every current profile is
  `LEGACY_UNCALIBRATED` and cannot support a positive warrant.
- BCTK is a development diagnostic. It emits `NOT_ASSESSED`, is bound to a digest
  of target file bytes, returns a non-success certification exit code, and refuses
  all badge requests.
- `spec/registry.yaml` is the single numbering ledger. BNS-019 is Scientific
  Semantic Conventions, BNS-020 is BCTK, and BNS-021 is Evidence Debt.

## Evidence acceptance contract

An external review, calibration approval, challenge vote, or future conformance
result is accepted only when all of these conditions hold:

1. The signed payload uses `bionexus.evidence-attestation.v1`.
2. Its subject contains the exact evidence artifact SHA-256.
3. The Ed25519 key already exists in an explicitly supplied trust registry and is
   authorized for the predicate; a self-generated key is not trusted.
4. The signature, signer/key identity, issuance interval, and expiry verify.
5. Neither the key nor the attestation has a valid signed revocation.
6. The supplied artifact bytes match the signed digest.

Missing artifact bytes return `NOT_ASSESSED`; tampering, expiry, untrusted keys,
and revocation return explicit negative decisions. A report SHA-256 alone is never
described as an attestation.

These controls provide research-grade provenance and review integrity. They are
not 21 CFR Part 11, GxP, CLIA, or another regulatory electronic-signature claim.
