# BNS-009: Capability Lifecycle

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: capability versioning, benchmark suite evolution, `docs/versioning-policy.md`, `docs/deprecation-policy.md`
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

Capabilities and their benchmarks must evolve without eroding trust. This document
norms how requirements change, how hard cases enter the suite, and how capabilities
deprecate — including the rule that a 100% pass rate on an easy suite is worth less
than an honest 96% on a hard one.

## 2. Change discipline

- **BNS-LC-001** Any change to a capability's inputs, preconditions, forbidden
  claims, or evidence ceiling MUST increment the capability `version` (BNS-CC-002)
  and be recorded in the changelog with the affected requirement IDs.
- **BNS-LC-002** Spec requirements are versioned with the series; a requirement MAY
  be strengthened (MAY→SHOULD→MUST) across versions but MUST NOT be silently
  weakened. Weakenings require a new requirement ID and an explicit supersession
  note.
- **BNS-LC-003** ABI version bumps (BNS-CC-015) follow semver: additive fields are
  minor; semantic changes to existing fields are major and require a migration note
  (`docs/migration-guide.md`).

## 3. The frontier track (calibration honesty)

- **BNS-LC-004** Benchmark cases that probe beyond currently-guaranteed behavior
  MUST be marked `known_limitation: true` and tracked in a **frontier track** —
  executed and reported with honest pass/fail, but excluded from gating metrics
  (CRI) until they graduate.
- **BNS-LC-005** A frontier case MUST graduate into the gating suite once the
  runtime passes it deterministically; graduation MUST be recorded in the changelog.
  Lingering frontier cases are the public, honest statement of "what BioNexus does
  not yet guarantee".
- **BNS-LC-006** Benchmark reports MUST distinguish gating metrics from frontier
  metrics. A report MAY show 100% on the gating suite, but MUST NOT present it as a
  calibration claim; calibration claims are only valid over the union of gating and
  frontier tracks (BNS-EM-009).
- **BNS-LC-007** Suites SHOULD grow toward adjacent-class confusion, near-miss
  refusals, and multi-capability ambiguity — the cases that make macro-F1 meaningful
  — rather than toward more copies of easy wins.

## 4. Deprecation

- **BNS-LC-008** Capability deprecation follows `docs/deprecation-policy.md`:
  announce → warn (one minor series) → remove. Deprecated capabilities MUST keep
  refusing safely (their refusal triggers stay active) until removal.
- **BNS-LC-009** Legacy skills that fall back to heuristics MUST remain
  non-default-visible (`agent_routing.LEGACY_SKILLS`) so degraded execution can never
  be the implicit path (BNS-AD-006).

## 5. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-LC-001..003 | `CHANGELOG.md` review; `tests/unit/test_abi.py` (ABI version stability) |
| BNS-LC-004..007 | frontier track in `evals/datasets/calibration_edge.yaml`; report frontier section |
| BNS-LC-008..009 | `tests/unit/test_handoff_and_gate.py`; `agent_routing.LEGACY_SKILLS` |
