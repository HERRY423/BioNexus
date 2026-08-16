# BNS-001: Capability Contract & Scientific ABI

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/capabilities.py`, `src/bionexus/abi.py`, all capability definitions
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

A BioNexus **capability** is the unit of scientific work that can be requested from the
platform (e.g. `scrna.pseudobulk_de`, `spatial.morans_svg`). This document defines what
a capability MUST declare before it may be exposed to any host agent, and defines the
**Biological Capability ABI**: the stable, machine-readable interface boundary that any
host — Claude, Codex, or any future agent — MUST conform to when invoking BioNexus.

The key words "MUST", "MUST NOT", "SHOULD", "SHOULD NOT", and "MAY" are to be
interpreted as described in RFC 2119.

## 2. Capability identity

- **BNS-CC-001** A capability MUST have a unique, stable identifier in
  `domain.method[.variant]` form (e.g. `spatial.morans_svg`). Identifiers MUST NOT be
  renamed after publication; supersession follows BNS-009.
- **BNS-CC-002** A capability MUST declare a `version` integer that increments on any
  semantic change to its contract (inputs, preconditions, forbidden claims, ceilings).
- **BNS-CC-003** A capability MUST declare the canonical skill that implements it
  (`skill_name`) and at least one user-facing `intent` keyword for routing.
- **BNS-CC-004** A capability MUST declare its input specifications, including for each
  input: semantic type, required/optional status, and (where applicable) a validation
  rule hook (e.g. `audit_expression_matrix:counts`).

## 3. Preconditions and refusal triggers

- **BNS-CC-005** A capability MUST declare machine-checkable preconditions
  (`Precondition`), each with a rule expression and a `fatal_if_violated` flag.
- **BNS-CC-006** Every condition that deterministically mandates refusal MUST be
  declared as a `RefusalTrigger` with: `condition_id`, `description`, actionable
  `remedy`, and the scientific `violated_rule` it protects. Refusal triggers MUST NOT
  be advisory-only; when triggered in strict mode the runtime MUST refuse (BNS-005).
- **BNS-CC-007** A remedy MUST be actionable — it names the concrete artifact to
  provide or the command to run (e.g. "Provide raw un-normalized count matrix
  (`adata.raw.X`)"), not a generic apology.

## 4. Execution reference

- **BNS-CC-008** A capability MUST declare a canonical backend
  (`BackendRequirement`): community-standard package name, import name, minimum
  version, and optional install extra. Capabilities without a community backend MUST
  declare a named local deterministic implementation (e.g. `local combiner` for ACMG
  tiering) and MUST NOT present heuristics as gold-standard.
- **BNS-CC-009** A capability MUST declare its expected outputs and its
  `EvidenceRequirement` (multiple-testing policy, effect-size policy, mandatory
  limitations). Every capability's mandatory limitations MUST include the
  Research-Use-Only statement unless BNS-008 grants an explicit certified exception
  (none exist today).

## 5. The Biological Capability ABI

A capability contract is more than metadata: it is a **Scientific ABI** — an interface
boundary that binds any host agent that connects to BioNexus. The ABI projection of a
capability (`bionexus.abi.CapabilityABI`, ABI version `1.0`) MUST contain, at minimum:

```yaml
capability:
  id: spatial.morans_svg
  abi_version: "1.0"
input_contract:
  matrix_state:
    allowed: [normalized_expression]
  coordinates:
    required: true
  coordinate_type:
    allowed: [physical, justified_spatial_embedding]
preconditions:
  - sufficient_nonzero_expression
  - valid_spatial_graph
forbidden_claims:
  - causal_interaction
  - cell_cell_communication
execution:
  reference_backend: squidpy
  reference_algorithm: spatial_autocorr
validation:
  multiple_testing: required
  parameter_sensitivity: required
  cross_method: recommended
evidence_ceiling:
  without_external_validation: FRAGILE   # or PRELIMINARY / SUPPORTED, per BNS-004
provenance:
  dataset_hash: required
  package_versions: required
  parameters: required
```

- **BNS-CC-010** Every capability MUST project to a complete `CapabilityABI` record.
  The projection is generated from the canonical contract (`abi.get_capability_abi`);
  hand-written ABI records MUST NOT diverge from the canonical contract.
- **BNS-CC-011** The ABI MUST declare, per input, the allowed **matrix states**
  (`raw_counts`, `normalized_expression`, ...) and, for spatial capabilities, the
  allowed **coordinate types** (`physical`, `justified_spatial_embedding`). See BNS-002.
- **BNS-CC-012** The ABI MUST declare a `forbidden_claims` list drawn from the
  normative claim taxonomy (`abi.FORBIDDEN_CLAIM_CATALOG`). A host agent MUST NOT
  emit a forbidden claim for this capability; the runtime MUST flag violations
  (BNS-008) and SHOULD block at routing time when the claim is detectable in the
  request.
- **BNS-CC-013** The ABI MUST declare an **evidence ceiling**: the maximum
  `ConclusionMaturity` (BNS-004) that outputs of this capability may assert in the
  absence of external validation. The runtime MUST clamp any synthesized maturity to
  the ceiling (`abi.enforce_evidence_ceiling`).
- **BNS-CC-014** The ABI MUST declare provenance requirements (dataset hash, package
  versions, parameters) per BNS-006.
- **BNS-CC-015** The ABI version string MUST be bumped to a new major version whenever
  any REQUIRED field semantics change in a way that breaks existing hosts. Hosts
  SHOULD verify `abi_version` before invocation.

## 6. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-CC-001..004 | `tests/unit/test_capabilities.py::test_canonical_capabilities_inventory` |
| BNS-CC-005..007 | `tests/unit/test_capabilities.py` (refusal suite), eval category `refusal` |
| BNS-CC-008 | `tests/unit/test_backend_matrix.py`, eval category `backend_failure` |
| BNS-CC-009 | `tests/unit/test_evidence_card.py` |
| BNS-CC-010..015 | `tests/unit/test_abi.py`, `bionexus abi show <id>` CLI |
| BNS-CC-012 (routing) | eval category `capability_claim` + frontier calibration track |
