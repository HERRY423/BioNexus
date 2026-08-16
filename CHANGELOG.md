# Changelog

All notable changes to **BioNexus** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🔒 Fixed (Evaluation Integrity — fail-closed scoring)
- **L3 auto-pass defect**: `evals/runner.py` no longer records `PERMITTED` when a scientific backend (`scanpy`/`squidpy`/`pydeseq2`/...) is unavailable. Missing backends now produce `SKIPPED_NO_BACKEND` results that are **never counted as passed**, are excluded from the accuracy denominator in non-strict runs, and are listed in a dedicated report section with the unavailable-backend reason. A machine without backends can no longer produce a passing L3 score.
- **Strict mode**: new `bionexus eval --strict` flag (or `BIONEXUS_EVAL_STRICT=1`) promotes backend-unavailable skips to failures with a non-zero exit code — required when citing an L3 score. New CI job `eval-strict` installs the full gold-chain + spatial stack (no `|| true` degradation), asserts the backends import, and runs the benchmark in strict mode, uploading the generated report as an artifact.
- **Unknown L3 planted signals** now fail loudly (`OUTCOME_MISMATCH`) instead of silently auto-passing, so dataset typos cannot inflate scores.
- **Circular test removed**: `test_eval_harness.py` no longer asserts "benchmark passes with CRI ≥ 0.95" by construction; it now verifies accounting integrity (passed/failed/skip exclusivity, skip reasons, denominator math), plus new regression tests for missing-backend skips, strict-mode promotion, and the `--strict` CLI flag.
- **L2 replay disclaimer**: offline replay reports now state explicitly that L2 scores audit scripted fixture responses, not live host-agent behavior.

### 📝 Fixed (Documentation vs SSOT honesty)
- **README skill table aligned to `bionexus.registry.yaml`**: variant-interpretation B→C, protein-structure-analysis A→C, biologics-design A/C→C, clinical-cohort A/C→C, provenance A→B; backend strings updated to SSOT wording. New guard test `tests/unit/test_readme_consistency.py` rejects grade overclaims, unverifiable static score badges, and "Primary Active" Python versions absent from the CI matrix.
- **Python 3.13 claim downgraded** to "Experimental — not in CI" (matrix covers 3.10–3.12); host-agent platforms downgraded from "Verified (Tier 1)" to "Declared (not CI-verified)" with an honesty note.
- **Doctor example output** replaced with the real `bionexus doctor` format; MCP tool names corrected (`search_gtex`→`get_gene_expression`, `search_pmc`→`get_pubmed_article`); static `Tests-217`/`CRI 96.2%` badges replaced with non-numeric equivalents.
- Corrected the 0.8.0 entry below: the eval suite is 8 datasets / 39 cases (not 6 datasets / 29 prompts).

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
  - Created 8 evaluation datasets across 39 structured cases: `routing.yaml`, `refusal.yaml`, `capability_claim.yaml`, `scientific_semantics.yaml`, `backend_failure.yaml`, `adversarial.yaml`, `l2_agent_claims.yaml`, `l3_scientific_outcomes.yaml`.
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
