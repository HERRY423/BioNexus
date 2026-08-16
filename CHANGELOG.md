# Changelog

All notable changes to **BioNexus** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 📜 Added (BioNexus Scientific Contract Specification — BNS series)
- **`spec/` normative specification tree**: nine RFC 2119-style documents (`BNS-001`..`BNS-009`) plus index, defining the scientific contract that binds BioNexus and any connected host agent — capability contract & Scientific ABI, input semantic invariants, execution fidelity, evidence maturity, abstention & degradation, provenance, cross-method validation, host conformance, and capability lifecycle. Every requirement carries a stable ID (`BNS-XX-nnn`) with a live verification hook (unit test, eval category, or runtime refusal). `tests/unit/test_spec_conformance.py` enforces document presence, RFC 2119 keyword usage, and cross-document reference integrity.

### 🧬 Added (Biological Capability ABI — `bionexus.abi`, ABI v1.0)
- **Capability contracts upgraded from metadata to a Scientific ABI**: every canonical capability now projects to a machine-readable ABI record (`input_contract` with allowed matrix states and coordinate types, `preconditions`, `forbidden_claims`, `execution` reference backend/algorithm, `validation` policy, `evidence_ceiling`, `provenance` requirements), generated from the canonical contract so it cannot drift. `forbidden_claims` and `evidence_ceiling_without_external_validation` are new normative fields on `CapabilityContract`.
- **Normative forbidden-claim taxonomy** (`FORBIDDEN_CLAIM_CATALOG`): 11 claim families (causal interaction, cell-cell communication, cell-type identity without reference, clinical diagnosis, treatment recommendation, model substitution, hazard causation, true-expression recovery, sensor calibration, regulatory compliance, pipeline results without execution) with detection patterns.
- **Routing-time forbidden-claim interception (BNS-AD-009)**: requests asking a capability for a claim on its forbidden list are now deterministically refused with the scientific reason and reformulation remedy (e.g. "use Moran's I to prove cell-cell communication" → ABSTAIN).
- **Evidence-ceiling clamping (`enforce_evidence_ceiling`)**: over-warranted maturity claims are clamped to the capability's ceiling (spatial SVG → FRAGILE without external validation; exploratory clustering → PRELIMINARY; REPLICATED requires external truth sets).
- **CLI**: `bionexus abi list|show <id>|audit-claims <id> --claims ...|conformance`.
- New unit tests: `tests/unit/test_abi.py` (10 tests: projection completeness, single-source-of-truth, claim audits, ceiling clamps, router interception, no-false-positive controls, CLI surface).

### 🎯 Changed (Calibration honesty — frontier track, BNS-LC-004..007)
- **Frontier calibration track**: new `evals/datasets/calibration_edge.yaml` (11 probes, `known_limitation: true`) exploring adjacent-rank maturity discrimination, coordinate-substitution detection, statistical-power auditing, multi-intent routing, and ABI ceiling clamps. Frontier cases are executed and reported with honest pass/fail but excluded from gating metrics until graduation.
- **Honest benchmark reporting**: reports now separate gating (guaranteed behavior) from frontier (known limitations) and state the union accuracy — gating-only 100% is explicitly labeled NOT a calibration claim. Current honest state: gating 42/42 (CRI 100%), frontier 7/11, union 49/53 = 92.5%, union calibration verdict UNDERCONFIDENT (macro-F1 96.3%, OCE 0.041). The four open known limitations are published by name in every report.
- **Calibration metrics extended**: adjacent-rank error rate, within-one accuracy, per-class precision/recall/F1, calibration verdict, skipped-no-backend accounting, and cross-host consistency (single-host runs reported as not evaluated rather than trivially consistent).
- **L2/L3 maturity attribution made honest**: claim audits warrant at most PRELIMINARY (they verify absence of overclaim, not statistical support); L3 outcome cases attest SUPPORTED only when the gold pipeline actually recovered the planted signal, and are excluded from calibration (disclosed count) when optional backends are absent. Fixes the previously un-reproducible "100% calibration" committed report (the prior numbers masked 12 L2/L3 maturity mismatches).
- **Spec-strengthened gating cases (BNS-AD-009)**: `claim-gxppart11-001` and `claim-acmg-clinical-001` now expect ABSTAIN — requesting an FDA Part 11 certified audit trail or an official clinical diagnostic report is refused at routing time instead of being permitted and audited post-hoc. Three new forbidden-claim refusal cases added (`refuse-forbidden-*`).
- **Loader fix**: `expected_maturity` is now actually read from YAML suites (was silently dropped).
- New unit tests: `tests/unit/test_calibration_frontier.py` (8 tests) and updated `test_eval_harness.py`.

### 🔒 Fixed (Single source of truth for the plugin mirror trees)
- **Dual skill-tree drift eliminated**: `skills/single-cell-rna-qc/scripts/scrna_pipeline.py` had diverged by 49 lines between the canonical root tree and the `plugins/bionexus/skills/` copy (the mirror lacked `--run-dir` / Run Capsule support). The mirror is now regenerated from the root; both trees are byte-identical.
- **Drift detection now covers code trees, not just JSON manifests**: `bionexus registry --check` and `scripts/registry_compiler.py --check` verify `skills/` and `scripts/` are byte-identical to their `plugins/bionexus/` mirrors (content edits, missing files, and stale mirror-only files all fail CI); `--generate` resynchronizes the mirrors automatically. Ignored artifacts (`__pycache__`, logs, doctor cache) are excluded.
- **Rule**: edit only the canonical root `skills/` and `scripts/` trees — the `plugins/bionexus/` copies are compiler-generated.
- **Removed the broken `plugins/codex/` scaffold**: its only manifest (`.codex-plugin/plugin.json`) declared `"skills": "./skills/"` pointing at a directory that never existed there; nothing in the repo referenced it.
- **Completed the self-contained `plugins/bionexus/` plugin root**: added the missing `plugins/bionexus/.mcp.json` required by its `.codex-plugin/plugin.json` (`"mcpServers": "./.mcp.json"`), so every relative reference in the nested manifests now resolves.
- New unit tests: repository-level mirror zero-drift, all three divergence classes (edited / missing / stale) plus sync repair, and self-containedness of the plugin-root manifests.

---

## [0.8.0] - 2026-08-15

### 🚀 Added
- **Machine-Readable Capability Contracts (`bionexus.capabilities`)**:
  - Implemented formal `CapabilityContract`, `SemanticInputType`, `Precondition`, `RefusalTrigger`, `EvidenceRequirement`, and `CapabilityEvaluationResult`.
  - Registered 8 canonical capabilities: `scrna.pseudobulk_de`, `scrna.exploratory_clustering`, `spatial.morans_svg`, `survival.kaplan_meier`, `scvi.probabilistic_vae`, `allotrope.format_conversion`, `nextflow.pipeline_launch`, `variant.acmg_classification`.
  - Added CLI subcommands: `bionexus capability [list|show|check]`.
- **6-Stage Scientific Intent & Invariant Router (`bionexus.intent_router`)**:
  - Implemented 6-stage routing pipeline: Intent Extraction $\to$ Data Semantics $\to$ Preconditions $\to$ Capability Matching $\to$ Backend Probe $\to$ Decision.
  - Added authoritative routing statuses: `PERMITTED`, `NEEDS_DATA`, `ABSTAIN`, `DEGRADED_ADVISORY`.
  - Added CLI command: `bionexus route "<query>" [--data <path>] [--min-replicates <N>]`.
- **BioNexus Eval: Agent Behavior & Scientific Reliability Benchmark (`evals/`)**:
  - Implemented 8 Core Reliability Metrics: Routing Accuracy, Unsafe Invocation Rate, Abstention Precision/Recall, Capability Hallucination Rate, Backend Fidelity, Scientific Semantic Error Rate, Evidence Calibration, and Composite Reliability Index (CRI).
  - Created 6 evaluation datasets across 29 structured prompts: `routing.yaml`, `refusal.yaml`, `capability_claim.yaml`, `scientific_semantics.yaml`, `backend_failure.yaml`, `adversarial.yaml`.
  - Added CLI command: `bionexus eval [--suite <name>] [--report <path>] [--json]`.
- **Single Source of Truth (SSOT) Multi-Platform Manifest Compiler (`bionexus.registry`)**:
  - Canonical `bionexus.registry.yaml` compiling into Agent Plugins 1.0 (`plugin.json`, `mcp.json`), Claude Plugin (`.claude-plugin/plugin.json`), and OpenAI Codex (`.codex/config.json`).
  - Added CLI command: `bionexus registry [--generate|--check|--validate-endpoints]`.
- **Skill Scaffolding Tool (`bionexus.scaffold`)**:
  - Added CLI generator `bionexus create-plugin <name>` generating Gold Reference skill directories, pipelines, and offline unit test fixtures.
- **Ecosystem Governance Documentation**:
  - Added `docs/versioning-policy.md`, `docs/compatibility-matrix.md`, `docs/migration-guide.md`, `docs/deprecation-policy.md`.
  - Added automated GitHub release workflow `.github/workflows/release.yml`.

### 🔄 Changed
- **EvidenceCard 2.0 (Three-Layer Epistemic Model)**:
  - Decoupled into `ExecutionState` (`EXECUTED`, `DEGRADED`, `REFUSED`, `FAILED`), `DimensionGrade` (`A`, `B`, `C`, `UNTESTED`, `NOT_APPLICABLE`, `INSUFFICIENT`, `CONFLICTED`), and `ConclusionMaturity` (`ABSTAIN`, `FRAGILE`, `CONFLICTED`, `PRELIMINARY`, `SUPPORTED`, `ROBUST`, `REPLICATED`).
  - Added non-breaking backward compatibility aliases `ConclusionStatus` and `EvidenceGrade`.
- **Parameter Robustness Auditing**:
  - Added `audit_parameter_stability()` in `bionexus.integrity` computing Adjusted Rand Index (ARI) and Jaccard similarity across parameter perturbation sweeps.

### 🛡️ Fixed
- Fixed single-cell condition differential expression to require biological replicates ($n \ge 2$) and refuse single-sample pseudoreplication.
- Fixed negative binomial GLM inputs to refuse continuous normalized floats and enforce discrete integer counts.
- Fixed cell-type naming invariants to prohibit unverified hallucinated biological labels.

---

## [0.7.0] - 2026-07-23

### 🚀 Added
- Initial gold-chain skill wrappers for `single-cell-rna-qc` (scanpy), `spatial-transcriptomics` (squidpy), `scvi-tools`, `nextflow-development`, `instrument-data-to-allotrope`.
- Basic `EvidenceCard` 1.0 and DoctorGate environment verification.
- Local fallback MCP server and W3C PROV-O provenance sidecars.
