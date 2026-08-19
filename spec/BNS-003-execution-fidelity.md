# BNS-003: Execution Fidelity

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/backends.py`, `src/bionexus/contracts.py` (`ExecutionState`), router stage 5
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

Execution fidelity answers one question: **did the gold-standard method actually run?**
It is deliberately decoupled from scientific conclusions (BNS-004 Layer 1 separation):
an analysis that ran perfectly can still support only a fragile conclusion, and a
refused analysis has no conclusion at all.

## 2. Execution states

- **BNS-EF-001** Every BioNexus result MUST carry exactly one `ExecutionState`:
  - `PERMITTED` — preflight passed; execution allowed but not yet run.
  - `EXECUTED` — the canonical gold-standard backend executed successfully.
  - `DEGRADED` — heuristic fallback, partial stack, or approximate parameters ran.
  - `REFUSED` — deterministically refused by a capability contract trigger.
  - `FAILED` — runtime crash, divergence, or convergence failure.
- **BNS-EF-002** States MUST NOT be conflated: a heuristic fallback MUST NOT be
  reported as `EXECUTED`; a refusal MUST NOT be reported as `FAILED` (refusal is a
  correct behavior, failure is an incorrect one).
- **BNS-EF-003** The legacy `execution_fidelity` field is a compatibility alias
  only. New code MUST read `execution_state`.

## 3. Backend requirements

- **BNS-EF-004** Each capability MUST probe its declared backend before execution
  (`backends.probe`): installed version vs minimum version, importability.
- **BNS-EF-005** For **default-visible skills**, a missing canonical backend MUST
  produce an abstention (`REFUSED`) with an install remedy — the runtime MUST NOT
  silently substitute a heuristic for a gold-standard method.
- **BNS-EF-006** For **legacy skills** with explicit user consent
  (`allow_degraded=true`), execution MAY proceed via a Grade C heuristic, and the
  result MUST be marked `DEGRADED` with the missing backend named in the evidence
  card. Degraded consent MUST be per-invocation; it MUST NOT be a global default.
- **BNS-EF-007** Backend unavailability in a benchmark environment MUST NOT be scored
  as a routing failure when the expected behavior is a clean abstention
  (eval category `backend_failure`).

## 4. Reference implementations

- **BNS-EF-008** Capabilities SHOULD name a reference algorithm
  (ABI `execution.reference_algorithm`, e.g. `spatial_autocorr` for Moran's I) so
  that alternative implementations can be validated against the reference on planted
  ground-truth fixtures (L3 outcome suites).
- **BNS-EF-009** Where community packages implement the same statistics with
  different defaults (e.g. Scanpy vs Seurat normalization), BioNexus MUST record the
  chosen reference in provenance (BNS-006) rather than silently mixing defaults.

## 5. Crash honesty

- **BNS-EF-010** A runtime crash MUST surface as `FAILED` with the exception class
  recorded. Crashes MUST NOT be retried into heuristics without an explicit degraded
  consent path (BNS-EF-006).
- **BNS-EF-011** Non-determinism (seeds, GPU kernels) SHOULD be pinned in
  provenance; a capability whose reference algorithm is seed-sensitive MUST record
  the seed (BNS-006).

## 5a. Backend Identity Conformance

BNS-EF-005 forbids silent substitution as a *policy*; BNS-EF-012..016 make the
absence of substitution *machine-provable*. Every canonical capability answers
an identity audit: claimed backend, observed executed backend, entry points,
version, execution fingerprint, and fallback flag.

- **BNS-EF-012** Each capability MUST emit a machine-checkable backend identity
  statement (`backend_conformance.verify_backend_identity`): claimed backend,
  observed backend, declared/resolved/missing entry points, installed version,
  execution fingerprint, and a fallback flag.
- **BNS-EF-013** `declared_backend == observed_backend` MUST be verified via the
  installed-distribution witness (`importlib.metadata.packages_distributions`),
  not via anything the caller claims. A missing or mismatched witness MUST
  resolve to state `MASQUERADE` with action `BLOCK` and failure mode `BN-F010`.
- **BNS-EF-014** The declared entry points MUST resolve to real symbols of the
  observed backend. The right distribution without the declared API surface is
  still a masquerade and MUST `BLOCK` (BN-F010).
- **BNS-EF-015** An identity report MUST NOT conceal a fallback: the `fallback`
  field is structurally `False`. An identity report that required a fallback is
  itself a masquerade.
- **BNS-EF-016** A backend that executed nothing MUST be reported as
  `NOT_INSTALLED` with action `ABSTAIN` and no failure mode: absence is honest
  refusal territory (BNS-005), never a masquerade.

## 6. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-EF-001..003 | `tests/unit/test_evidence_card.py`; `contracts.synthesize_conclusion_maturity` |
| BNS-EF-004 | `tests/unit/test_backend_matrix.py` |
| BNS-EF-005..007 | eval `backend_failure`; `tests/unit/test_kernel_and_honesty.py` |
| BNS-EF-008 | L3 planted-truth suites (`scrna_markers`, `spatial_moran_svg`, `pseudobulk_de`) |
| BNS-EF-009 | `src/bionexus/provenance.py` sidecar schema |
| BNS-EF-010 | eval L3 `EXECUTION_FAILURE` handling in `evals/runner.py` |
| BNS-EF-012..016 | `tests/unit/test_backend_conformance.py`; CLI `backend-identity`; flagship pseudobulk gate (`evals/flagship_validation.py`) |
