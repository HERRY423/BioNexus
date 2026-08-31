# BNS-016: Standards Interoperability & External Scope

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/interop.py`, `src/bionexus/standards.py`, `src/bionexus/cli.py` (interop/standards), `docs/standards-engagement.md`, `docs/product-matrix.md`
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

BioNexus MUST NOT become a research-data standard island. The internal Run
Capsule and Claim–Evidence Ledger stay internal; everything that crosses the
boundary goes through published community standards:

    Claim–Evidence Ledger → W3C PROV-O → ┌─ RO-Crate 1.1 (+ Workflow Run Crate)
    Run Capsule          →              └─ BioCompute Object (IEEE 2791-2020)

Interoperability is the adoption strategy: institutional pipelines (Galaxy,
DNAnexus, Seven Bridges, WorkflowHub) can ingest BioNexus outputs today
without adopting anything else from BioNexus.

## 2. Interoperability requirements

- **BNS-IO-001** Run capsules MUST be exportable as RO-Crate 1.1 documents in
  which the capability is a `ComputationalWorkflow`, the execution is a
  schema.org `CreateAction` (instrument / object / result / startTime /
  endTime), and profile conformance is declared via `conformsTo` against the
  Workflow RO-Crate and Process Run Crate profile identifiers.
- **BNS-IO-002** Claim–Evidence Ledgers MUST be exportable as RO-Crate 1.1
  documents with claims and evidence refs as contextual entities; support
  edges use schema.org `isBasedOn` and contradiction is carried in entity
  descriptions. The PROV-O projection (BNS-CL-009) remains available.
- **BNS-IO-003** Run capsules MUST be exportable as BioCompute Objects
  conforming to the IEEE 2791-2020 six-domain structure (provenance,
  usability, description, execution, io, parametric domains). Ledgers MUST
  NOT be exported as BCOs: a BioCompute Object describes a computation, not a
  claim graph.
- **BNS-IO-004** Exports are fail-closed: a projection that fails structural
  validation MUST NOT be written to disk or returned as valid.
- **BNS-IO-005** BioNexus MUST NOT introduce a proprietary interchange format.
  The run capsule is an internal structure; interchange happens exclusively
  through PROV-O, RO-Crate, and BCO.
- **BNS-IO-006** Projections MUST be deterministic and offline: no network
  calls, no telemetry, no timestamps other than those already recorded in the
  source artifacts.
- **BNS-IO-009** The BCO `etag` MUST be computed from the object's content
  (SHA-256 over the canonical JSON), never asserted; validation MUST recompute
  and reject mismatches.
- **BNS-IO-010** Validator scope MUST be machine-readable. Workflow Run
  RO-Crate CI MUST build a sealed deterministic fixture and run the pinned
  official `roc-validator` CLI at REQUIRED severity against Provenance Run
  Crate 0.5 with profile inheritance enabled. A successful run MUST emit a
  hash-bound receipt with status `THIRD_PARTY_TOOL_VALIDATED`. That status
  proves technical conformance of the fixture only; it MUST NOT be described
  as certification, endorsement, ecosystem adoption, or scientific validation.
  BCO remains repository-structurally-tested until an independent IEEE schema
  validation gate is added.
- **BNS-IO-011** Crate root datasets SHOULD carry Bioschemas-compatible
  schema.org typing; full Bioschemas profile validation MAY follow and MUST
  be reflected honestly in the registry before `implemented` status is claimed.
- **BNS-IO-014** Run capsules MUST be exportable as Workflow Run RO-Crate
  Research Object directories (`bionexus interop wfrun-crate`) that package
  the actual input bytes, software (engine + pinned packages), the execution
  as a `CreateAction`, recorded per-step executions (`ControlAction` /
  tool-run `CreateAction` / engine `OrganizeAction` per Provenance Run Crate
  0.5), output artifacts, the EvidenceCard, and any adjacent Claim–Evidence
  Ledger, under the published profile chain (Process Run Crate 0.5, Workflow
  Run Crate 0.5, Workflow RO-Crate 1.0; Provenance Run Crate 0.5 declared only
  when steps are projected). The export MUST fail closed: capsules whose v2
  integrity seal does not verify are never exported, the metadata document is
  validated before anything is written, and the materialized crate MUST be
  re-verified on disk (structure plus SHA-256 of every data entity, computed
  over raw bytes so standard consumers agree). Exports remain deterministic
  and offline (BNS-IO-006).

## 3. Standards engagement requirements

- **BNS-IO-007** Standards alignment MUST be machine-readable
  (`bionexus standards`): registry entries carry a closed status vocabulary —
  `implemented` (shipped and tested here), `aligned` (follows the external
  spec in use), `proposal` (offered into an external forum, not adopted),
  `tracked` (venue monitored). A status MUST reflect verifiable reality.
  Registry entries MUST also carry the independent verification axis
  (`repository_tested`, `third_party_tool_validated`, or `not_assessed`), so
  implementation, tool validation, and external adoption cannot be conflated.
- **BNS-IO-008** The alignment report MUST publish this disclaimer verbatim:
  *BioNexus is not an industry standard and does not claim to be one. The BNS
  series is an implementation proposal; standards status is earned by external
  adoption of its vocabulary, schemas, and tests — never declared.* BioNexus
  MUST NOT state or imply GA4GH (or any body) endorsement.
- **BNS-IO-013** Engagement with external bodies (GA4GH AI Work Stream,
  ELIXIR, nf-core, scverse, Bioconductor, WorkflowHub) SHOULD contribute
  portable artifacts — the BN-Fxxx taxonomy, the capability-contract schema,
  refusal semantics, and BioFailureBench tests — rather than infrastructure
  that requires running BioNexus.

## 4. Product scope boundary

- **BNS-IO-012** The product matrix (`docs/product-matrix.md`: bionexus-core,
  bionexus-audit, bionexus-conformance, reference capability packs) and its
  non-goals list (no planner, memory, multi-agent, chat UI, cloud workspace,
  notebook replacement, compute service, or agent marketplace) MUST be
  published, and the documented module mapping MUST match the repository.

## 5. Verification hooks

- `tests/unit/test_interop.py` — projections, profiles, fail-closed exports.
- `tests/unit/test_wfrun_crate.py` — Workflow Run RO-Crate bundle structure,
  profile chain, step wiring, checksum agreement, determinism, fail-closed
  refusal of unsealed capsules.
- `tests/unit/test_standards.py` — registry statuses and verbatim disclaimer.
- `tests/unit/test_product_matrix.py` — documented module mapping is real.
- `bionexus interop check <run|ledger>` — CLI-level validation.
- `bionexus interop wfrun-crate <run> --out <dir>` — CLI-level bundle export.
- `.github/workflows/ro-crate-conformance.yml` — pinned official
  `roc-validator==0.11.2`, full inherited REQUIRED profile gate, validator log,
  and hash-bound validation receipt.
