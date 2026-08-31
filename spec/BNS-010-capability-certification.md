# BNS-010: Capability Certification

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/certification.py`, all capability evidence records, M4 milestones
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

A skill is documentation. A **Certified Scientific Capability** is an executable
contract that has survived a defined evidence program. This document defines
the certification tiers and the fourteen criteria a capability MUST satisfy
before it MAY be called Certified. Certification exists to prevent capability
inflation: the platform MUST NOT grow to 30, 50, 100 shallow skills; it MUST
deepen a small set of capabilities through the tiers.

## 2. Tiers

- **BNS-CF-001** Every capability MUST hold exactly one tier:
  - `CERTIFIED` — all fourteen criteria satisfied with recorded evidence.
  - `VALIDATED` — all core criteria satisfied (reference backend, formal input
    contract, invariants, known failure modes, positive test, negative test).
  - `EXPERIMENTAL` — formal contract exists plus at least one passing test class.
  - `CONNECTOR-ONLY` — data-plane connector (MCP tool, registry endpoint)
    without scientific execution claims.
- **BNS-CF-002** Tier assignment MUST be computed from evidence records
  (`certification.compute_tier`); a tier MUST NOT be hand-asserted. A capability
  without recorded evidence for a criterion cannot reach a tier requiring it.
- **BNS-CF-003** Evidence records MUST cite verifiable pointers: test files,
  benchmark case IDs, vendored datasets, or review records. Notes MUST state
  known weaknesses honestly (e.g. "trigger contract-defined, not exercised").
- **BNS-CF-004** Structural cross-checks MUST run at certification time:
  contract-derived criteria (input contract, invariants, failure-mode links)
  MUST be re-verified against the live ABI, taxonomy, and precondition tables —
  certification records MUST NOT drift from the code they certify.

## 3. The fourteen Certified criteria

A capability MUST satisfy all of the following to be CERTIFIED:

1. **reference_backend** — canonical community backend declared, versioned, probed.
2. **formal_input_contract** — complete ABI input contract (BNS-CC-011).
3. **invariants** — machine-checkable preconditions and refusal triggers.
4. **known_failure_modes** — failure taxonomy modes linked with detection rules (BNS-011).
5. **positive_test** — verified execution producing the expected result.
6. **negative_test** — invalid inputs/requests refused deterministically.
7. **adversarial_test** — coercion/jailbreak attempts blocked.
8. **public_reference_dataset** — validated against a public dataset or truth set.
9. **independent_ground_truth** — ground truth independent of the implementation.
10. **parameter_perturbation** — stability audit across a declared sweep (BNS-XM-002).
11. **degradation_test** — missing-backend behavior tested (BNS-AD-006/007).
12. **provenance_test** — sidecar completeness and integrity tested (BNS-006).
13. **cross_host_test** — L2 claim audit across >= 2 host providers with agreement reported (BNS-HC-007).
14. **external_reviewer** — independent scientific review recorded (reviewer, date, findings).

## 4. Honesty obligations

- **BNS-CF-005** The certification report MUST publish the current tier
  distribution verbatim — including `CERTIFIED: 0` when that is the truth. The
  gap analysis (blocking criteria per capability) IS the certification roadmap.
- **BNS-CF-006** M4's "at least 10 CERTIFIED capabilities" is a target, not a
  deadline for rubber-stamping: capabilities graduate by producing the missing
  evidence (datasets, sweeps, multi-host runs, reviews), never by weakening
  criteria.
- **BNS-CF-007** Criteria MUST NOT be redefined to fit current evidence; adding
  criteria is a spec version bump (BNS-LC-002).

## 5. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-CF-001..004 | `tests/unit/test_certification.py`; `bionexus certification` CLI |
| BNS-CF-005..007 | Certification report gap section; spec review on change |
| BNS-CF-008 | `tests/unit/test_validation_verifier.py`; `CERTIFICATION.json` schema |

## 6. Semantic Authority & CAB Distinction (BNS-010 / BNS-022)

- **BNS-CF-008** Semantic Scope and Authority Limitation:
  - Internal capability tiers (`CERTIFIED`, `VALIDATED`) measure internal evidence completeness (`assessment_authority: "INTERNAL_EVIDENCE_ASSESSMENT"`).
  - All emitted capability certification artifacts carry `certification_effect: "NONE"` and `independent_assurance_status: "NOT_ASSESSED"`.
  - Internal evidence completeness MUST NEVER be represented as or conflated with third-party accredited Conformity Assessment Body (CAB) conformity certification or formal regulatory clearance (CLIA/CAP/FDA).
