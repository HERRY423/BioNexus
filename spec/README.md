# BioNexus Scientific Contract Specification (BNS)

**Status**: Active | **Specification Series Version**: 1.0 | **Applies to**: BioNexus >= 0.8.0

The BioNexus Scientific Contract Specification (BNS) series defines the normative,
machine-enforceable scientific behavior contract for BioNexus and any host agent
(Claude, Codex, or future AI coding agents) that connects to it.

## Why a scientific contract?

Prompts can be copied. Skills can be copied. MCP endpoints can be copied.
A **Scientific Contract** — invariants, refusal triggers, evidence maturity rules,
failure taxonomy, and a calibration benchmark validated across hundreds of cases —
cannot be copied, only earned. The BNS series is the written form of that contract.

## Normative language

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD",
"SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in each BNS document are to be
interpreted as described in **RFC 2119** / **RFC 8174** when, and only when, they
appear in capitals.

Every requirement carries a stable identifier (`BNS-XX-nnn`). Identifiers are
never reused. Requirements may be superseded by later revisions but never silently
deleted.

`registry.yaml` is the authoritative numbering ledger. CI validates that IDs and
filenames are unique, contiguous, present on disk, and bound to the document's
first heading. A document is not part of the BNS series until it is registered.

## Document index

| ID | Title | Governs | Primary enforcement point |
|---|---|---|---|
| [BNS-001](BNS-001-capability-contract.md) | Capability Contract & Scientific ABI | What a capability MUST declare | `src/bionexus/capabilities.py`, `src/bionexus/abi.py` |
| [BNS-002](BNS-002-input-invariants.md) | Input Semantic Invariants | Raw vs normalized data, coordinates, cell types | `src/bionexus/integrity.py`, router stage 2–3 |
| [BNS-003](BNS-003-execution-fidelity.md) | Execution Fidelity | Gold backends, execution states, degradation honesty | `src/bionexus/backends.py`, `contracts.ExecutionState` |
| [BNS-004](BNS-004-evidence-maturity.md) | Evidence Maturity (EvidenceCard 2.0) | Three-layer epistemic evidence reporting | `src/bionexus/contracts.py` |
| [BNS-005](BNS-005-abstention-and-degradation.md) | Abstention & Degradation | Deterministic refusal and degraded advisory behavior | `src/bionexus/intent_router.py`, `contracts.refuse()` |
| [BNS-006](BNS-006-provenance.md) | Provenance | Reproducibility sidecars and audit trails | `src/bionexus/provenance.py`, `artifacts.py` |
| [BNS-007](BNS-007-cross-method-validation.md) | Cross-Method Validation | Parameter sensitivity and method concordance | `src/bionexus/integrity.py` (stability audits) |
| [BNS-008](BNS-008-host-conformance.md) | Host Agent Conformance | What any connected host agent MUST/MUST NOT do | `src/bionexus/claim_checker.py`, `evals/host_eval.py` |
| [BNS-009](BNS-009-capability-lifecycle.md) | Capability Lifecycle | Versioning, frontier graduation, deprecation | `docs/versioning-policy.md`, eval frontier track |
| [BNS-010](BNS-010-capability-certification.md) | Capability Certification | 14 evidence criteria; CERTIFIED / VALIDATED / EXPERIMENTAL / CONNECTOR-ONLY tiers | `src/bionexus/certification.py` |
| [BNS-011](BNS-011-failure-taxonomy.md) | Scientific Failure Taxonomy | The BN-Fxxx failure ontology with detection rules | `src/bionexus/failures.py` |
| [BNS-012](BNS-012-claim-evidence-ledger.md) | Claim–Evidence Ledger | Claim graph as a data structure (JSON / PROV-O JSON-LD) | `src/bionexus/ledger.py` |
| [BNS-013](BNS-013-scientific-assertion-firewall.md) | Scientific Assertion Firewall | The three researcher entry points: preflight / audit / verify | `src/bionexus/preflight.py`, `analysis_audit.py`, `verification.py` |
| [BNS-014](BNS-014-biofailurebench.md) | BioFailureBench | The scientific trap corpus with ground truth (BF-nnn) | `evals/datasets/biofailurebench.yaml`, `evals/biofailurebench.py` |
| [BNS-015](BNS-015-flagship-certification.md) | Flagship Certification | 3 externally-validated CERTIFIED capabilities as the priority track | `src/bionexus/certification.py` (flagship program) |
| [BNS-016](BNS-016-standards-interop.md) | Standards Interoperability & External Scope | RO-Crate / Workflow Run Crate / IEEE 2791 BCO exports; standards engagement; product boundary | `src/bionexus/interop.py`, `src/bionexus/standards.py` |
| [BNS-017](BNS-017-claim-semantics-ir.md) | Scientific Claim Semantics & Deterministic Warrant IR | Typed Claim IR, epistemic warrant rules, causal overclaim interception | `src/bionexus/claim_semantics.py`, `src/bionexus/claim_checker.py` |
| [BNS-018](BNS-018-rule-calibration-and-challenge-network.md) | Scientific Rule Calibration & Challenge Network | Machine-readable rule registry, empirical sensitivity, peer challenge protocol | `src/bionexus/rule_calibration.py`, `src/bionexus/empirical_warrant.py` |
| [BNS-019](BNS-019-scientific-semantic-conventions.md) | Scientific Semantic Conventions | Language-neutral vocabulary for biological units, claims, evidence, confounds, and warrants | `standards/scientific-semantic-conventions/` |
| [BNS-020](BNS-020-conformance-test-kit.md) | BioNexus Conformance Test Kit (BCTK) | Target-bound development diagnostics; certification and badges suspended | `src/bionexus/bctk/`, `bctk` CLI |
| [BNS-021](BNS-021-evidence-debt.md) | Scientific Evidence Debt & Epistemic DAG Amortization | Structured scientific debt taxonomy, keystone bottleneck analysis, optimal repayment schedule | `src/bionexus/debt.py`, `bionexus debt` |
| [BNS-022](BNS-022-scientific-semantics-neutral-governance.md) | Scientific Semantics Neutral Governance & Institutional Adoption | Independent Council formation, technical/commercial/certification separation, evidence-bound institutional adoption | `governance/scientific-semantics/`, `scripts/validate_semantic_governance.py` |
| [BNS-023](BNS-023-validation-transparency-network.md) | Validation Transparency Network | Portable, dual-attested validation events and deterministic candidate-slot state | `src/bionexus/validation_network.py` |

## Conformance classes

1. **Core conformance** (MUST): enforced deterministically by the BioNexus runtime;
   violations are refusals, not warnings.
2. **Host conformance** (BNS-008): obligations on the connecting AI agent; audited by
   the L2 prohibited-claims benchmark.
3. **Calibration conformance** (BNS-004): obligations on reported evidence quality;
   measured by the epistemic calibration benchmark (OCE, overconfidence, macro-F1)
   and the frontier calibration track (BNS-009).
4. **Certification conformance** (BNS-010): tier claims MUST be computed from
   recorded evidence; honest gap reporting is mandatory (BNS-CF-005).

## Governing philosophy

**Fail-closed** (BNS-005 §6): *knowing when not to compute is a scientific
capability.* Missing evidence abstains, invalid input refuses, missing backends
degrade with disclosure, violated assumptions block claims, absent external
validation caps evidence. The canonical gate is `prevent_invalid_run()`.

## Verification

Every requirement lists its verification hook: the unit test file, eval category, or
runtime refusal that checks it. The benchmark report (`evals/reports/benchmark_report.md`)
is the living conformance record.
