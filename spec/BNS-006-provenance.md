# BNS-006: Provenance

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/provenance.py`, `src/bionexus/artifacts.py`, ABI `provenance` block
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

A result without provenance is an anecdote. Provenance is what makes a BioNexus
result reproducible, auditable, and admissible as evidence in later meta-analyses.
The ABI provenance block (BNS-CC-014) is the normative minimum.

## 2. Required provenance fields

- **BNS-PV-001** Every executed result MUST record a **dataset hash** (content hash
  of primary input artifacts) sufficient to detect input drift between runs.
- **BNS-PV-002** Every executed result MUST record **package versions** of the
  canonical backend and its critical dependencies (Python version, library versions
  resolved at execution time, not assumed).
- **BNS-PV-003** Every executed result MUST record the full **parameter set** used,
  including defaulted parameters. Omitting defaults MUST NOT occur: defaults are
  scientific choices.
- **BNS-PV-004** Every executed result SHOULD record: wall-clock timestamp with
  timezone, host platform, random seeds (BNS-EF-011), and the BioNexus capability id
  + ABI version that produced it.

## 3. Sidecar contract

- **BNS-PV-005** Provenance MUST be emitted as a machine-readable sidecar adjacent
  to the primary output artifact (JSON), referencing outputs by relative path and
  content hash.
- **BNS-PV-006** Sidecars MUST be self-contained: a reader MUST be able to
  reconstruct the invocation (data + packages + parameters) without access to
  BioNexus runtime state.
- **BNS-PV-007** Degraded executions MUST mark the substitution in the sidecar
  (actual executor vs canonical backend, BNS-AD-008) so downstream provenance
  audits can detect heuristic-stage artifacts.

## 4. Integrity

- **BNS-PV-008** Consumers of an artifact MUST be able to verify the artifact
  against its recorded hash; mismatch MUST be surfaced as an integrity violation,
  not a warning.
- **BNS-PV-009** Provenance records MUST NOT be mutable after emission; corrections
  are new records superseding old ones (append-only audit semantics).

## 5. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-PV-001..004 | `tests/unit/test_provenance_tracker.py`; `bionexus abi show <id>` provenance block |
| BNS-PV-005..007 | `tests/unit/test_artifacts.py` (sidecar emission) |
| BNS-PV-008..009 | `src/bionexus/provenance.py` verification APIs |
