# BioNexus BCTK — Development Diagnostic Guide

> **Scientific Trust Reset:** BCTK certification and badge issuance are suspended.
> A diagnostic score is not third-party validation, certification, or endorsement.

BCTK can inspect a target and produce a target-content-bound development report:

```bash
bctk test . --json
bctk test plugins/my-analysis-plugin --markdown
bionexus conformance test plugins/bionexus
```

Every run returns exit code `2` (`NOT_ASSESSED`) so it cannot silently satisfy a CI
certification gate. The JSON includes:

- `assessment_status: DEVELOPMENT_NOT_CERTIFIABLE`
- `conformance_tier: NOT_ASSESSED`
- `badge_eligible: false`
- `trust_decision: NOT_ASSESSED`
- `target_content_sha256`, computed from the target files in scope
- `cryptographic_fingerprint`, a report integrity hash that is explicitly not a signature
- `diagnostic_tier`, the legacy score mapping retained only for calibration research

Biological-semantics and cross-host checks remain `NOT_ASSESSED` unless future
versions receive target-specific fixtures and host-native traces. BCTK no longer
tests BioNexus/NumPy and attributes those results to a third-party target.

Reports also project the eight dimensions into independently adoptable protocol
profiles: `BNS-Core`, `BNS-Warrant`, `BNS-Provenance`, `BNS-Agent`,
`BNS-Validation`, and `BNS-Full`. Profiles are not score bands. If any mandatory
dimension is missing, skipped, or not applicable, that profile is
`NOT_ASSESSED`; a high score elsewhere cannot average the gap away. Every profile
has `certification_effect: NONE` during the trust reset.

The commands below intentionally fail without writing a badge:

```bash
bctk badge --tier GOLD
bctk test . --badge
```

Future certification evidence must conform to
`bionexus.evidence-attestation.v1`: it must bind the exact artifact SHA-256, verify
an Ed25519 signature against a preconfigured trust key, remain within its validity
interval, and have no valid signed revocation. The packaged trust registry contains
no trusted authorities. This is a research integrity mechanism, not a regulatory
electronic-signature claim.

The normative development contract is [BNS-020](../spec/BNS-020-conformance-test-kit.md).
