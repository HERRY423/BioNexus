# BNS-023: Validation Transparency Network

**Status**: Development / No Certification Effect | **Version**: 0.1 | **Supersedes**: none  
**Applies to**: `src/bionexus/validation_network.py`, validation event packets, mirrors, and derived candidate-slot state.  
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose and boundary

BNS-023 defines a portable event format for recording who evaluated which
artifact, against which BNS profile and dataset, on which host, with what
result and limitations. It is an evidence-transparency protocol, not a central
BioNexus database, scientific truth oracle, certification authority, or
blockchain.

- **BNS-VN-001** Every accepted event MUST bind an immutable validation packet,
  evidence artifact, BNS release, BCTK release, profiles, issuer, institution,
  subject digest, result, timestamp, and limitations.
- **BNS-VN-002** The event issuer MUST sign the exact packet using a configured
  trust anchor authorized for `bns-validation-event`.
- **BNS-VN-003** A distinct assessor MUST sign the same packet using a trust
  anchor authorized for `bns-independence-assessment`; self-assessed
  independence MUST be rejected.
- **BNS-VN-004** Signature validity, identity authorization, artifact binding,
  expiry, and revocation MUST fail closed through the trust registry.

## 2. Portable append-only history

- **BNS-VN-005** The log MUST use canonical JSON, monotonic sequence numbers,
  previous-event links, and SHA-256 event hashes.
- **BNS-VN-006** Anyone MAY export, copy, or mirror the complete log. A verifier
  MUST accept an out-of-band expected head so rollback to a valid prefix is
  detectable.
- **BNS-VN-007** An implementation MUST refuse to append to a corrupted chain
  or reuse an event identifier.
- **BNS-VN-008** Corrections, supersession, negative results, and revocation
  MUST remain events; historical bytes MUST NOT be rewritten.

## 3. Derived state, not mutable certification flags

- **BNS-VN-009** Candidate slot counts MUST be deterministically recomputed from
  active, dual-attested events after expiry, revocation, and supersession.
- **BNS-VN-010** Positive and negative non-author review outcomes MAY both count
  as completed review evidence; an inconclusive or not-assessed event MUST NOT.
- **BNS-VN-011** Dataset, external-laboratory, cross-host, and calibration slots
  MUST require the event-specific positive result defined by the reducer.
- **BNS-VN-012** Derived state MUST remain `certification_status=NOT_ASSESSED`.
  Cryptographic admission MUST NOT be presented as scientific truth,
  institutional authority, accreditation, or certification.

## 4. Interoperability direction

- **BNS-VN-013** The scientific predicate SHOULD be transportable in an
  established attestation envelope such as in-toto, and a transparency-service
  receipt MAY be retained without changing scientific meaning.
- **BNS-VN-014** Recording a SCITT- or transparency-shaped receipt MUST NOT be
  called SCITT conformity unless an external conforming service and receipt
  verification have actually been exercised.

## 5. Human authority

- **BNS-VN-015** Event admission and slot derivation MUST NOT replace named
  Human Scientific Adjudication. A human decision MAY cite the event head and
  packet digests but MUST remain a separate, accountable decision artifact.
