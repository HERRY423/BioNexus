# Changelog

All notable changes to **BioNexus** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🚀 Added
- **Verified Data Ingress (`bionexus.ingress`)**:
  - `bionexus ingest <source> <dest>`: streaming SHA-256-verified ingestion from local paths, `file://`, and `http(s)://`; `s3://`/`gs://` refuse deterministically unless their optional SDK is present (never pretend a fetch happened).
  - Fail-closed checksum/size verification: mismatched artifacts are deleted, never kept.
  - `ingest_into_capsule()` registers ingested artifacts directly into a Run Capsule input manifest.
- **Real nf-core Execution (`skills/nextflow-development`)**:
  - `nfcore_execute.py`: executes a written launch script when Nextflow is available, records exit status, log tails, and a full Run Capsule (`nextflow.pipeline_execute`); refuses honestly when Nextflow/bash are missing.
  - `nfcore_sarek_launch.py`: nf-core/sarek launch artifacts with Sarek-schema samplesheet validation (patient/sample/fastq_1/fastq_2, optional lane + tumor/normal status normalization) and mandatory explicit `--step`.
- **Run Capsule Chain Orchestration (`bionexus.orchestrator`)**:
  - `bionexus chain <spec.yaml>`: topological, fail-closed execution of multi-stage research workflows with one verified Run Capsule per stage; failed stages skip downstream stages (`SKIPPED_FAIL_CLOSED`) and never report partial success.
  - Stage commands are argv lists (`shell=False`); `--dry-run` plans without executing; cycles, unknown dependencies, duplicates, and privilege escalation are rejected at spec validation.
- **Project Ledger (`bionexus.project`)**:
  - `bionexus project init|register-dataset|register-run|status`: cross-session project memory in `.bionexus/project.json`.
  - Datasets deduplicate by SHA-256; Run Capsules are cryptographically verified at registration and tampered capsules are refused (fail-closed).
- **Skill graduation**: `research-workflow-orchestrator` upgraded from outline/deprecated to a canonical wrapper skill over `bionexus.orchestrator` (Run Capsule chain surface), now default-visible.

### 🔄 Changed
- CLI: new `ingest`, `chain`, and `project` subcommands; `research-workflow-orchestrator` moved from `LEGACY_SKILLS` to `DEFAULT_SKILLS`.

### 🛡️ Trust & Evidence Depth (Accuracy & Trustworthiness)
- **Data Governance (`bionexus.governance`)**:
  - `bionexus data-classify`: declaration-driven sensitivity tiers (PUBLIC / INTERNAL / SENSITIVE / RESTRICTED) with a deterministic keyword-signal cap that only ever restricts, writing a SHA-256-bound governance sidecar.
  - `bionexus policy check`: tier x egress-zone policy matrix (LOCAL / ORGANIZATION / EXTERNAL) returning router-vocabulary decisions (`PERMITTED` / `DEGRADED_ADVISORY` / `ABSTAIN`); RESTRICTED (PHI/clinical) data is refused for any external zone unconditionally and locally only behind an explicit RUO acknowledgement.
  - `bionexus.governance.assert_query_permitted()` gates hosted-endpoint queries that would carry data fragments to external processors; unknown endpoint ids resolve conservatively to EXTERNAL.
- **Orthogonal Evidence Audits (`bionexus.validation`)**:
  - `rank_concordance()` (EvidenceCard dimension 6): Spearman rank correlation + top-k Jaccard overlap between two method rankings, with documented A/B/C/CONFLICTED grading; refuses degenerate overlaps.
  - `external_validation()` (EvidenceCard dimension 7): precision/recall/F1/Jaccard of predicted calls against an independent truth set (e.g. ClinVar-style controls), grading A/B/C/CONFLICTED.
  - `bionexus concordance` / `bionexus external-validation` CLI audits; `apply_cross_method_concordance()` / `apply_external_validation()` write audited grades into EvidenceCards.
  - New `scrna_cross_method_audit.py` gold-chain script audits Wilcoxon marker rankings against PyDESeq2 pseudobulk DE rankings (explicit lower-is-better handling for pvalue/padj columns).
- **Eval L3 Expansion (4 → 8 outcome cases; 39 → 43 total)**:
  - `rank_concordance`: two independent statistics (mean-shift vs rank-sum) must agree on planted markers (rho >= 0.85).
  - `external_validation`: planted truth-set recovery must reach precision/recall >= 0.80.
  - `egress_policy`: the governance matrix must return the documented decision for all 7 tier x zone combinations.
  - `survival_separation`: canonical log-rank test must detect planted hazard separation (lifelines optional; skipped as PERMITTED on minimal runners).

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
