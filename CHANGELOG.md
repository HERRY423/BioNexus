# Changelog

All notable changes to **BioNexus** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🧱 Added (Scientific Assertion Firewall — BNS-013)

Product repositioning: **BioNexus catches biological analyses that should not have been run.** Three researcher-facing entry points, usable without any host agent:

- **`bionexus preflight`** (`src/bionexus/preflight.py`): runs BEFORE compute. Resolves the declared intent onto a capability contract, inspects the actual data state (matrix semantics, donor/condition structure, confounding, spatial provenance — reading `.h5ad` directly when anndata is present), and renders the seven-section verdict block: INTENT / DATA STATE / RISKS / DECISION / ALLOWED / FORBIDDEN CLAIM / REMEDY. Decision vocabulary is the fail-closed table (BNS-AD-014) verbatim; ALLOWED under a prevented decision comes only from taxonomy `acceptable_degradation`; FORBIDDEN CLAIM is mechanically derived from the capability's forbidden-claim catalog + evidence ceiling. Exit codes: 0 proceed (incl. capped/degraded), 1 refused/blocked, 2 missing evidence.
- **`bionexus audit <notebook|script>`** (`src/bionexus/analysis_audit.py`): deterministic static rule engine (BFA-001..BFA-013) over `.ipynb` / `.py` / `.R` / `.Rmd` / `.qmd` screening the canonical trap classes: cell-level pseudoreplication, raw/log matrix confusion, missing FDR, batch/condition confounding, inappropriate statistical unit, annotation without evidence, circular marker validation, missing negative controls, spatial coordinate substitution (incl. `obsm['spatial'] = obsm['X_umap']`), parameter instability, overclaimed causality (via the prohibited-claims auditor), backend substitution, and unexecuted code claims. Findings cite rule id + BN-Fxxx + evidence line + remedy; the mandatory disclaimer states that absence of findings is NOT proof of validity. Data-file audit behavior (`.h5ad`/csv matrix semantics) is preserved unchanged.
- **`bionexus verify <results>`** (`src/bionexus/verification.py`): verifies final results against their Claim–Evidence Ledger (BNS-012): fail-closed re-resolution per claim, evidence lines with honest symbols, ceiling cross-check, and *not-warranted* flagging of causal/mechanistic language beyond the evidence class. Exit non-zero on ABSTAIN/CONFLICTED/unwarranted claims; honest intermediate maturities do not fail.
- New spec `spec/BNS-013-scientific-assertion-firewall.md` (BNS-FW-001..014); tests `test_preflight.py`, `test_analysis_audit.py`, `test_result_verify.py`.

### 🏆 Added (Flagship Certification Track + two flagship capabilities — BNS-015)

- **Flagship principle**: *three CERTIFIED capabilities with independent external validation outweigh ten self-tested certifications.* Flagship set: `scrna.pseudobulk_de` (A: pseudoreplication), `scrna.annotation_evidence` (B: annotation evidence), `spatial.inference_validity` (C: spatial inference validity). The M4 10-CERTIFIED target is unchanged (BNS-CF-006); the flagship track is prioritization, never weakening. External criteria (public dataset, independent ground truth, cross-host, external reviewer) cannot be implementer-satisfied. `bionexus certification` now publishes the flagship section with per-capability external-criteria-remaining.
- **`src/bionexus/annotation_evidence.py` + contract `scrna.annotation_evidence`**: not another CellTypist — assesses how much evidence backs a candidate cell-type label (reference mapping, marker consistency, negative markers, doublet risk, ontology compatibility, open-set detection, cross-method agreement) and returns per-label verdicts SUPPORTED / TENTATIVE / ABSTAIN with published deterministic thresholds.
- **`src/bionexus/spatial_inference.py` + contract `spatial.inference_validity`**: not a Squidpy reimplementation — tests whether a spatial conclusion survives its alternative explanations (12-control canonical registry: cell size, transcript density, segmentation uncertainty, nuclear eccentricity, local density, spot composition, spatial autocorrelation, batch/FOV, ligand/receptor abundance, contact geometry, neighborhood radius, permutation null). Verdict ladder ROBUST / SUPPORTED / FRAGILE / ABSTAIN; ceiling FRAGILE without orthogonal validation.
- New spec `spec/BNS-015-flagship-certification.md` (BNS-FC-001..008); tests `test_flagship_capabilities.py`.

### 🪤 Added (BioFailureBench: the Scientific Trap Corpus — BNS-014)

- **`evals/datasets/biofailurebench.yaml`**: 26 traps (23 gating — all passing deterministically; 3 frontier known limitations) covering **all twelve taxonomy modes**. Each trap is a complete record with eight fields: data, intended analysis, hidden flaw (BN-Fxxx), expected detection, allowed computation, forbidden claim, remediation, reference. Includes a positive control (BF-024) so the bench cannot degrade into an all-refusal benchmark. Host-agnostic: Claude, Codex, Cursor, Biomni, and future agents run the identical suite via `bionexus eval --suite biofailurebench`.
- **`evals/biofailurebench.py` + `bionexus bench validate`**: machine-checked corpus integrity (field completeness, taxonomy linkage, gating/frontier prefixes, ID resolution, mode coverage); invalid corpora fail CI.
- **Three taxonomy open gaps CLOSED with wired detection** (BNS-FT-008): BN-F004 identifier mismatch (router stage-3.5 namespace screen, BF-008/BF-025), BN-F005 missing FDR (`abi.enforce_statistical_warrant` caps warrant at PRELIMINARY, BF-005), BN-F008 cross-database contradiction (router trap screen, BF-016). BN-F009 embedding-coordinate substitution is now refused at routing (BF-007/BF-020). Perfect condition-donor confounding and open-set/annotation-evidence traps are screened deterministically (BF-003/BF-013, BF-004/BF-022).
- New spec `spec/BNS-014-biofailurebench.md` (BNS-BF-001..009); tests `test_biofailurebench.py`. Honest benchmark state after extension: **gating 61/61 attempted (65 total, 4 L3 skipped no-backend) · frontier 7/14 · union 90.7% · union macro-F1 90.1%**; union calibration verdict is now MISALIGNED (both an overconfidence trap and underconfidence probes exist — reported, not hidden).

## [0.9.0] - 2026-08-16

### 🌐 Fixed (FastMCP Dynamic Tool Registration & Fallback Routing Disambiguation)
- **Fixed FastMCP default tool leakage in `scripts/local_mcp_server.py`**: wrapped the 6 hosted-overlap fallback tools (`search_pubmed`, `get_pubmed_article`, `search_biorxiv`, `search_chembl`, `search_opentargets`, `search_clinical_trials`) and `search_cosmic` behind `BIONEXUS_LOCAL_HOSTED_FALLBACKS=1`. By default, FastMCP now registers exactly **9 local unique tools** (GTEx, GEO, STRING, UniProt, Ensembl, gnomAD, PDB, AlphaFold, Reactome) plus 6 Resources and 6 Prompts.
- **Eliminated Agent routing ambiguity**: AI coding agents querying literature, targets, or clinical trials will cleanly route to dedicated cloud-hosted MCP endpoints without duplicate tool confusion.
- **Synced test coverage**: updated `tests/unit/test_mcp_server.py` to assert 9 default unique tools and 16 tools upon opt-in.

### 🎖️ Added (Capability Certification Program — BNS-010)
- **`src/bionexus/certification.py`**: 14 evidence criteria and four tiers (CERTIFIED / VALIDATED / EXPERIMENTAL / CONNECTOR-ONLY). Tiers are **computed from recorded evidence, never asserted** (BNS-CF-002); structural cross-checks re-verify contract-derived criteria against the live ABI, preconditions, and taxonomy. Honest current state: **0 CERTIFIED, 7 VALIDATED, 1 EXPERIMENTAL** — the per-capability blocking-criteria list is the published roadmap to the M4 target of 10 CERTIFIED (evidence must be produced, criteria never weakened, BNS-CF-006). CLI: `bionexus certification`.
- New spec `spec/BNS-010-capability-certification.md`; tests `tests/unit/test_certification.py` (CERTIFIED requires all 14 — structurally un-gameable).

### 🧯 Added (Scientific Failure Taxonomy — BNS-011)
- **`src/bionexus/failures.py`**: twelve normative failure modes (BN-F001 assay-state confusion, BN-F002 pseudoreplication, BN-F003 unsupported annotation, BN-F004 identifier mismatch, BN-F005 missing multiple-testing correction, BN-F006 invalid model assumption, BN-F007 parameter instability, BN-F008 cross-database contradiction, BN-F009 missing spatial provenance, BN-F010 backend degradation masquerading, BN-F011 claim inflation, BN-F012 unexecuted maturity claim). Each record: definition, canonical example, affected capabilities, detection rule, **fail-closed required behavior**, acceptable degradation, benchmark cases. Three modes are honestly flagged as open gaps (no benchmark coverage yet). `classify_violation()` tags runtime violations with taxonomy IDs. CLI: `bionexus failures list|show`.
- New spec `spec/BNS-011-failure-taxonomy.md`; tests verify record shape, vocabulary, and that every benchmark-case reference resolves to a real eval case.

### 🚫 Added (Fail-Closed Gate — BNS-005 §6)
- **`src/bionexus/failclosed.py`**: `prevent_invalid_run()` — the canonical gate implementing *knowing when not to compute is a scientific capability*: missing evidence → ABSTAIN (request data), invalid input → REFUSE, backend unavailable → DEGRADE WITH DISCLOSURE, assumption violated → BLOCK CLAIM, claim beyond warrant → BLOCK CLAIM, external validation absent → CAP EVIDENCE LEVEL. No row resolves to silent execution. Returns `PreventionDecision` with failure-mode IDs, remedies, and the underlying routing decision. CLI: `bionexus prevent "<query>"`.
- New spec requirements BNS-AD-013..015; tests cover all six rows plus the clean RUN PERMITTED exit.

### 📒 Added (Claim–Evidence Ledger — BNS-012)
- **`src/bionexus/ledger.py`**: claims as auditable dependency graphs — `ClaimRecord` (supported_by / contradicted_by / depends_on) over closed-vocabulary `EvidenceRef` nodes (dataset, transformation, method_run, statistical_result, database, cross_method). **Fail-closed resolution**: any contradiction forces CONFLICTED; no support forces ABSTAIN; otherwise the weakest supporting warrant, clamped by the capability's ABI evidence ceiling (database/cross-method support counts as external validation). JSON round-trip + PROV-O JSON-LD projection; append-only (duplicate IDs rejected). Deliberately a data structure, not a graph platform. CLI: `bionexus ledger show|jsonld`.
- New spec `spec/BNS-012-claim-evidence-ledger.md`; tests include the CLAIM-017 reference scenario.
- **ABI clamp refinement**: warning states (FRAGILE / CONFLICTED / ABSTAIN / UNASSESSED) are never rewritten by evidence ceilings — only ascending-ladder warrant levels (PRELIMINARY→REPLICATED) are clamped.

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
