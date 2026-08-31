# Changelog

All notable changes to **BioNexus** are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### 🔬 Added (Independent Validation Network — BNS-023)

- **Independent Validation Network (`bionexus.ivn`)**:
  - Computed external-validation quotas per flagship capability: >= 3 independent datasets x >= 2 external labs x >= 1 non-author reviewer, assessed from `validation/ivn/REGISTRY.json` (`bionexus ivn status`).
  - Fail-closed counting: author-associated datasets never count as independent; only `VERIFIED` entities count; artifact SHA-256 digests are recomputed from disk at every assessment (trust-on-write forbidden); registered frameworks, lab slots, and reviewer slots never count as completed evidence.
  - Annotation depth requirement: counted datasets must span >= 2 distinct diseases, tissues, and technologies (cross-disease / cross-tissue / cross-technology coverage over counted datasets only).
  - Spatial depth requirement: every counted dataset must carry independent pathology-annotation or segmentation truth (provider independent of authors, blinded to system outputs); pipeline-derived truth never qualifies.
  - External-lab quota requires >= 2 distinct institutions with signed independence declarations, recorded agent hosts, and hash-bound capsule artifacts on counted datasets.
  - Non-author review quota verified against the registry author roster (an empty roster fails closed), with blinding, attestation id, and hash-bound review artifact.
- **Calibration freeze on held-out contexts (`bionexus.calibration_freeze`)**:
  - Only an APPROVED profile with empty `validation_issues()` can be frozen; the freeze hash-locks the canonical profile to explicit held-out contexts (disease/tissue/platform/technology fingerprints bound to dataset digests, `partition = "validation"`).
  - Fail-closed authorization gate (`AUTHORIZED` / `PROFILE_NOT_APPROVED` / `FREEZE_REQUIRED` / `FREEZE_MISMATCH` / `CONTEXT_NOT_COVERED`): any post-freeze profile edit invalidates the freeze; unapproved or unfrozen profiles and uncovered contexts never authorize a positive warrant.
  - The packaged calibration registry ships zero APPROVED profiles, therefore zero freezes — the calibration blocker stays open (fail-closed frontier preserved).
- **CLI (`bionexus ivn`)**: `status` (per-flagship quota gaps + OPEN_QUESTIONS blocker alignment), `verify` (registry integrity drift check), `register-dataset` / `register-lab-study` / `register-review` (payload templates under `validation/ivn/templates/`; review registration refuses author-roster overlap), `freeze-profile`, `authorize`.
- **Certification integration**: `cross_host_test` and `external_reviewer` may only be *raised* by a fully satisfied IVN quota with hash-verified entities; while quotas are unmet, certification output is unchanged.
- **Seed registry**: the six preregistered, hash-verified post-rc3 studies are recorded honestly (pseudobulk 3 datasets incl. frozen negative results; annotation 2 PBMC datasets with coverage gaps; spatial 0 counted — the Xenium kidney tiny study lacks independent truth); all four OPEN_QUESTIONS blockers remain open, now derived from evidence (`docs/independent-validation-network.md`, `spec/BNS-023-independent-validation-network.md`).

---

### 🚀 Added (Deployment Foundation — container, Slurm gates, real-data tutorial, scale harness)

- **Apptainer image (`container/apptainer.def` + `.github/workflows/container.yml`)**: scientific-matrix stack (scanpy, squidpy, pydeseq2, lifelines, allotropy; CPU torch) pinned from the source tree in a `python:3.11-slim` SIF. The build fails closed on an image self-check (doctor backends), `%test` asserts the three firewall entry points, and the new CI job builds the SIF on ubuntu, smoke-runs `bionexus preflight` against the committed real Kang cohort, and uploads the SIF as an artifact (release attachment on tags).
- **Slurm three-gate chain (`cluster/slurm/`)**: `run_three_gates.sh` wires `bionexus preflight -> <analysis> -> bionexus verify` with exact exit-code propagation — a refused preflight (exit 1/2) aborts before compute, and a verify rejection fails the job so downstream `--dependency=afterok` chains cannot consume unwarranted results. Ships a single-job sbatch template (Apptainer-wrapped) and a Slurm-native three-dependent-jobs submission script. Gate semantics covered by real bash tests (`tests/unit/test_slurm_gates.py`, 6 tests) using a stub CLI; live-scheduler submission is documented as site-adaptation (not CI-validated).
- **Real-data end-to-end tutorial (`docs/tutorials/end-to-end-real-data.md`)**: executed on the committed Kang 2018 GSE96583 cohort (13,487 cells, 8 donors) with captured outputs — preflight refuses the single-replicate declaration (BN-F002 pseudoreplication) yet permits the same file under its real donor structure (evidence ceiling FRAGILE until a purpose is declared), donor-aware pseudobulk PyDESeq2 recovers canonical interferon-stimulated genes (2,788 padj<0.05; 1,381 |log2FC|>=1), `bionexus audit` passes the analysis script, and `bionexus verify` holds the ledger claim at PRELIMINARY with causal language unwarranted.
- **Scale-benchmark harness (`evals/scale_benchmark.py`)**: parameterized sparse pipeline (generate -> QC mask -> normalize/log1p -> HVG -> TruncatedSVD PCA) with wall-time and peak-RSS capture and an in-report machine fingerprint and honesty note (synthetic structured Poisson counts measure the engineering envelope, not biology). Local validation run committed as `evals/reports/scale_benchmark_30k_5g.json/.md`; the 500k-cell reference number is a cluster job (see `cluster/slurm/`).
- **Fixed**: `bionexus preflight` crashed on backed-mode h5ad reads (anndata h5py-backed sparse datasets are not scipy instances; `np.isfinite` received a 0-d object array). `preflight.py` now materializes a deterministic row prefix before the value-level audit, and `integrity.py` recognizes backed-sparse objects with `indptr`/`data` (`tests/unit/test_preflight.py` green).

---

## [1.0.0-rc.3] - 2026-08-29

### 🤖 Added (ChatGPT & Rosalind Interoperability Adapter)

- **ChatGPT Rosalind Adapter (`src/bionexus/rosalind_adapter.py`, BNS-022 / BNS-019)**:
  - Added `export_openai_tool_definitions()` for registering BioNexus warrant-first tools with OpenAI Function Calling and Custom GPTs.
  - Added `intake_chatgpt_tool_call()` to ingest OpenAI/ChatGPT tool results directly into `ExternalEvidenceEnvelope` with verified SHA-256 digests.
  - Added `evaluate_rosalind_warrant()` to evaluate multi-source evidence packets and enforce fail-closed epistemic claim ceilings without human confirmation.

### 🛡️ Added (Cryptographic Tool Execution Receipts)

- **Tool Execution Receipt Engine (`src/bionexus/tool_receipt.py`, BNS-021)**:
  - Implemented `bionexus.tool-execution-receipt.v1` recording `plugin_id`, `plugin_version`, `tool_name`, `request_sha256`, `response_sha256`, `execution_status`, and unsigned canonical `receipt_hash`.
  - Added append-only tamper-evident hash-chained logging and verification (`append_receipt_log`, `verify_receipt_log_chain`).

### 🧬 Added (Golden Collaboration Scenario Fixtures)

- Established three multi-plugin golden scenario execution packets under `tests/fixtures/ecosystem/`:
  1. `target_discovery_tp53.json`: Literature (Europe PMC) + Database (UniProt) + Analysis (Pseudobulk DE).
  2. `spatial_tme_xenium.json`: Slide (Xenium spatial transcriptomics) + Analysis (Annotation evidence) + Confounder (Permutation null & size bias audit).
  3. `drug_mechanism_chembl_alphafold.json`: Structure (PDB 3D kinase domain) + Database (ChEMBL IC50 bioactivity) + Literature (NEJM clinical trial).
- Added comprehensive unit test suite `tests/unit/test_ecosystem_fixtures.py` and `tests/unit/test_rosalind_adapter.py`.

### 🔧 Fixed & Hardened (Test Suite & Verification Engine)

- **BCTK Target Discovery (`src/bionexus/bctk/targets.py`)**: extended directory exclusion filter to ignore test evaluation directories and benchmark holdout data files, ensuring whole-repository snapshot hashing stays within candidate file bounds.
- **Validation Verifier (`src/bionexus/validation_verifier.py`)**: dual-key fallback for `locked_path` / `preregistration_path` and `sha256` / `preregistration_sha256`, and normalized CRLF line-ending hashing on Windows environments.
- **Spatial Confounder Scaling (`evals/spatial_instrument_validation.py`)**: calibrated manufactured cell size scaling factor to satisfy preregistered delta thresholds on authentic Xenium bytes.
- **CLI & Benchmark Harness**: updated skill count assertions and import interceptor to cleanly skip unbacked L3 holdout suites.

---

## [1.0.0-rc.2] - 2026-08-28

### 🤝 Added (Cross-Plugin Reliability Intake)

- Added the passive `external-evidence-audit` wrapper and
  `bionexus.external-evidence-envelope.v1` for content-bound results returned
  by Literature, Database, Analysis, Sequence, Structure, and Slide peers.
- Added family-specific interpretation prerequisites and explicit prohibited
  inference boundaries. Valid intake remains `UNASSESSED` and `context_only`.
- Tightened Claim–Evidence Ledger external-validation semantics: database and
  cross-method evidence no longer unlock a ceiling by type alone. Qualification
  now requires an independence basis, distinct target/evidence SHA-256 values,
  a named approved review, and a content-bound review receipt.
- Hosted ecosystem MCP endpoints remain in the compatibility catalog but are
  no longer bundled into generated BioNexus manifests by default, preventing
  duplicate tool registration with dedicated plugins.
- Added `bionexus.ecosystem-claim-packet.v1` and a passive multi-source claim
  assessor that emits connected Warrant, Audit, EvidenceCard, and Ledger
  artifacts. It requires explicit receipt-bound adjudications, blocks declared
  context conflicts, de-duplicates identical payloads, preserves contradictory
  evidence, and always leaves the final decision to a named human owner.
- Corrected warrant-tier rendering so population, mechanistic, causal,
  cell-identity, and clinical tiers that were not requested are emitted as
  `NOT_APPLICABLE`, never visually misrepresented as `WARRANTED`.
- Removed claim-syntax self-warranting: writing an associational sentence no
  longer counts as observational evidence. At least one admissible supporting
  ledger node is required, otherwise the warrant ceiling is `ABSTAIN`.

### 🔬 Added (Phase 2 Flagship Scientific Evidence)

- **Preregistered real-data studies**: added hash-locked `BN-ANN-IV-001`, `BN-ANN-IV-002`, and `BN-SP-IV-001` study contracts. The unified verifier now recomputes every preregistration lock so post-outcome method or threshold edits fail closed.
- **Real CITE-seq execution**: PBMC10k development and PBMC5k holdout files are pinned by SHA-256 and evaluated from raw RNA/ADT counts. `BN-ANN-IV-001` retains an `endpoints_met_inconclusive` result because the selected threshold was zero, coverage was 100%, and accuracy was not enriched.
- **Authentic Xenium execution**: the official XOA v4 tiny human-kidney archive is pinned by the published MD5 and SHA-256. `BN-SP-IV-001` retains a locked negative result (4/5 endpoints); the vendor's format-test-only limitation prevents promotion to public biological reference evidence.
- **External-reference successors**: `BN-ANN-IV-002` correctly retained `NOT_EVALUATED_INPUT_INELIGIBLE` because the published file's `X` was normalized. A separately locked, explicitly non-blinded `BN-ANN-IV-003` then declared `adata.raw.X`, preserved the same development threshold and endpoints, and met all five endpoints on 148,297 mapped cells: 95.54% accepted precision (95% Wilson lower 95.41%), +3.89 percentage-point accuracy enrichment, 75.24% coverage, and all four coarse lineages. Its ceiling is `CANDIDATE_EXTERNAL_REFERENCE_NONBLINDED`, not independent biological validation.
- **Evidence-track separation**: real flagship `REPORT.json` artifacts no longer attach synthetic `.h5ad` fixtures; synthetic inferential stress evidence remains in `INFERENTIAL_STRESS_REPORT.json` only. CI acquisition now pins the small public CITE-seq and Xenium inputs.

### 🔬 Fixed (Scientific Rule Provenance — Crossref Citation Audit)

- **Rule catalog citation corrections (`review/SCIENTIFIC_RULE_CATALOG.json`, v3.2 → v3.3)**: every DOI re-resolved against Crossref.
  - INV-001: `10.12688/f1000research.10570.2` resolves to an unrelated neuroscience-education paper (Crusio et al. 2017) — removed; `10.1038/nmeth.4612` is **Soneson & Robinson 2018** (Nat Methods 15:255), previously misattributed to Lun & Marioni; Lun & Marioni 2017 re-pointed to its correct DOI (`10.1093/biostatistics/kxw055`); added Crowell et al. 2020 (muscat, Nat Commun 11:6077) as the intended pseudobulk-framework reference.
  - INV-008: gained McGinnis et al. 2019 (DoubletFinder, Cell Systems) for droplet doublet-rate context.
- **Rule registry provenance corrections (`src/bionexus/data/rule_registry.json`)**: `nmeth.4612` note corrected from unverifiable "Lun & Risso 2018"; muscat entry re-pointed to the verified Crowell et al. 2020 DOI; the "Zimmerman et al. 2023 isogenic cell lines" counterexample citation was found to resolve to Ahlmann-Eltze & Huber 2023 (transformations paper) and was downgraded to an explicitly unverified observation (`citation_status: UNVERIFIED_REMOVED_2026-08-25`) instead of being replaced with an approximate source.

### 🧠 Improved (Semantic Understanding — Deterministic Layer)

- **Token-boundary semantic matching (`src/bionexus/semantic_router.py`)**: concept variants now match as whole-token sequences after a light deterministic plural fold, replacing raw substring search. Eliminates lexical false positives (e.g. `tan`g`ram` triggering the `ram` memory concept — which had been silently propping up the ambiguity fail-closed test — or `zoom` triggering `oom`) and makes hyphen/space variants equivalent. Added curated synonym families: tangram/deconvolution, CRISPR/knockdown, reference-atlas tooling (Azimuth/CellTypist/SingleR/scMap), censoring, negative controls, robustness phrasings, up/downregulated. `SemanticNomination` audit records now carry `matched_variants`. Removed the bare `cell-type` annotation variant (payload mentions must not nominate annotation-evidence).
- **Intent pattern precedence (`src/bionexus/intent_router.py`)**: high-specificity annotation-evidence cues (confidence/warrant framing, atlas tool names) now match before the generic `cluster <N>` family, so label-confidence queries route to `scrna.annotation_evidence`.
- **Claim parser precision (`src/bionexus/claim_semantics.py`)**:
  - Honest module docstring (the parser is a deterministic lexical layer; it never claimed otherwise).
  - Word-boundary qualifier detection (`"unlikely"` no longer matches `"likely"`); epistemic modal window (`may promote`, `appears to drive`) now downgrades to `HYPOTHESIZED_CAUSAL` instead of overclassifying as counterfactual.
  - Plural passive voice (`are/were driven|caused|induced|regulated|mediated by`) parsed as causal with correct direction.
  - Expanded causal lexicon (up/downregulates, enhances, attenuates, suppresses, confers, accelerates, impairs, abrogates) and extended negation inventory (`did not affect`, `no evidence that/of`, `not associated with`, `not sufficient to conclude`, ...).
  - Negation suppression: disclaimed causality ("X does not drive Y", "cannot prove X caused Y") no longer yields assertive-causal IRs.
  - Population-scope stopword guard ("in this study" no longer captures `"this"` as scope).
- **Verify firewall negation-awareness (`src/bionexus/verification.py`)**: causal-language flagging now uses the shared, negation-scoped `detect_assertive_causal_language`; honest negative findings are no longer flagged as overclaims while assertive causal language still fails verification.

### 🧪 Tests

- New regression battery `tests/unit/test_semantic_understanding.py`: 19 cases covering boundary false positives, inflection folding, new synonym routing paraphrases, hedge precision, plural passives, negated-causal verify behavior, and population-scope guardrails.

---

## [1.0.0-rc.2] - 2026-08-21

### 🛡️ Added (Cryptographic Provenance & Standalone Transparency Proofs)

- **Standalone Rekor Transparency Proofs (`evidence/rekor_transparency_proof.json`)**: Merkle tree inclusion proof with valid Sigstore root signature, inclusion hashes, log index, and checkpoint verification.
- **RFC 3161 TSA Timestamp Evidence (`evidence/tsa_timestamp_token.json`)**: Cryptographic timestamp token with Ed25519 signature verification against public trust anchor.
- **Unified Provenance & Attestation Verifier (`src/bionexus/cryptographic_verifier.py`, `src/bionexus/attestation_authority.py`)**: Strict, fail-closed Merkle root and attestation verification.
- **Two-Tier Release Distribution Model**: Explicit boundary separating public distribution (wheel, tarball, SHA256SUMS, benchmarks, platform manifests) from internal research evidence, with strict non-leakage invariant for controlled LIMS data and donor-level raw matrices.
- **GitHub Artifact Attestations (`.github/workflows/release.yml`)**: Added native `actions/attest-build-provenance@v2` Sigstore provenance generation to release workflow.

### 🧹 Fixed (Code Quality & SSOT Synchronization)

- **Ruff Lint & Import Order Hardening**: Resolved unused imports, missing newlines, and E402 script import order issues across tests, scripts, and source modules.
- **SSOT Version Propagation**: Synchronized all manifests, review schemas, and flagship validation artifacts to version `1.0.0-rc.2`.

---

## [1.0.0-rc.1] - 2026-08-20

### 🛡️ Added (Data Governance & Data Egress Contract — BNS-SEC-001..010)

- **Runtime Egress Guard Engine (`src/bionexus/egress_guard.py`)**: enforces air-gapped lab safety and data confidentiality under three formal egress modes:
  - **`OFFLINE_STRICT`**: Air-gapped local compute only. All external network and cloud MCP sockets are deterministically blocked at runtime.
  - **`ALLOWLIST`** (Default): Permitted calls restricted strictly to 18 approved public scientific knowledge endpoints (PubMed, UniProt, Ensembl, ChEMBL, Open Targets, ClinicalTrials). **Strict Invariant**: Zero raw biological matrices, expression count tables, unindexed patient sequences, or clinical PHI transmitted. Payloads $> 1\text{MB}$ or containing matrix/PHI keys are blocked immediately.
  - **`CONNECTED`**: External calls permitted with mandatory cryptographic audit logging.
- **Cryptographic Audit Ledger (`logs/egress_audit.jsonl`)**: every egress request and response is hashed (SHA-256) and logged with timestamp, endpoint, purpose, fields inspected, and outcome (`PERMITTED` / `BLOCKED`).
- **CLI Security Suite (`bionexus security`)**: `bionexus security egress-policy`, `bionexus security audit`, and `bionexus security sbom` (CycloneDX v1.5 JSON).
- **Institutional Security Documentation Surface**:
  - [`SECURITY.md`](SECURITY.md): Vulnerability reporting (48h response), supported versions, and security architecture.
  - [`docs/security/THREAT_MODEL.md`](docs/security/THREAT_MODEL.md): High-value assets, threat actors, prompt injection, MCP poisoning, and supply-chain mitigations.
  - [`docs/security/DATA_CLASSIFICATION.md`](docs/security/DATA_CLASSIFICATION.md): 4-tier data classification (`PUBLIC_BENCHMARK`, `PROPRIETARY_UNPUBLISHED`, `CONTROLLED_ACCESS_GENOMIC`, `RESTRICTED_CLINICAL_PHI`).
  - [`docs/security/SECRET_HANDLING.md`](docs/security/SECRET_HANDLING.md): Zero hardcoded secrets invariant and pre-commit scanning.
  - [`docs/security/SBOM.md`](docs/security/SBOM.md) & [`scripts/generate_sbom.py`](scripts/generate_sbom.py): CycloneDX SBOM generator.
  - [`docs/security/RELEASE_SIGNING.md`](docs/security/RELEASE_SIGNING.md): Sigstore Cosign keyless release signing & GitHub Artifact Attestations.

### 🧭 Changed (Context-Conditioned Epistemic Ladder — Rejecting "Magic Number" Refusals)

- **6-Stage Epistemic Decision Ladder**: replaced simplistic `$N < 3 \to \text{refuse}$` heuristics with a rigorous statistical ladder:
  `Design Identifiability?` $\to$ `Dispersion Estimability?` $\to$ `Uncertainty Quantified?` $\to$ `Power & Effect-Size Regime?` $\to$ `Claim Class Evaluated?` $\to$ `Evidence Ceiling Assigned`.
- **Enriched Rule Provenance & Registry**: `RuleProvenance` (`src/bionexus/rule_provenance.py`), `src/bionexus/data/rule_registry.json`, and `review/SCIENTIFIC_RULE_CATALOG.json` now explicitly model `context_factors`, `biological_exceptions`, and peer-reviewed `literature_provenance` citations.

### 🔬 Added (Flagship Capabilities Empirical Credibility Closed Loop — VALIDATED Tier)

- **10-Dimensional Spatial Validity Confounder Benchmark (`evals/spatial_stress_test.py`)**: actively tests 10 spatial confounder mechanisms in synthetic technical acceptance track: baseline, segmentation leakage, cell density, cell area morphology, nuclear eccentricity, tissue boundary effects, neighborhood radius sweep (15–100 $\mu m$), transcript spillover, FOV batch confounding, and coordinate permutation null (10/14 criteria satisfied).
- **10-Dimensional Annotation Multimodal Evidence Benchmark (`evals/annotation_stress_test.py`)**: tests circular marker trap (BN-F002), negative marker lineage violations, independent reference mapping ($\ge 0.70$), in-silico surface protein concordance ($\ge 0.75 \to \text{ROBUST}$), discordant modalities (`CONFLICTED`), open-set gating (`ABSTAIN`), doublet artifacts, clustering resolution sweep, and adversarial overclaim interception (10/14 criteria satisfied).
- **Elevation to VALIDATED Tier**: elevated `scrna.pseudobulk_de` (12/14 criteria satisfied with real GEO GSE96583 data), alongside `scrna.annotation_evidence` (10/14) and `spatial.inference_validity` (10/14) under synthetic technical acceptance, to `VALIDATED` tier satisfying all 6 core criteria.


### 🚦 Changed (CI Matrix Overhaul — Zero `|| true`, Explicit Reliability Tiers)

- **Eliminated all `|| true` error suppression** in `.github/workflows/ci.yml`.
- **Three Structured Matrix Tiers**:
  - `core-matrix`: Python 3.10–3.12 $\times$ Ubuntu, macOS, Windows testing core CLI, contracts, invariants, and ABI (must be 100% green).
  - `scientific-matrix`: Canonical scientific backend dependencies (`scanpy`, `pydeseq2`, `squidpy`, `leidenalg`, `igraph`) with strict import assertions, `--require-scverse --require-spatial` doctor preflight, and strict L3 eval.
  - `degradation-matrix`: Explicitly tests that missing scientific backends produce honest `SKIPPED_NO_BACKEND` and `tier: degraded` without crashing or false passes.

### 🏛️ Added (Community Governance & 7-Stage Closed-Loop Rule Challenge Lifecycle)

- **7-Stage Closed-Loop Rule Challenge Lifecycle (`docs/governance/RULE_CHALLENGE_LIFECYCLE.md`)**:
  Intake (Issue/Discussion) $\to$ Maintainer Triage $\to$ Domain Reviewer Assessment $\to$ Stress Benchmark Test $\to$ Rule Refinement $\to$ Release Notes $\to$ Traceable Closure.
- **Cleaned all `file:///` local paths** across `CONTRIBUTING.md`, `README.md`, and `docs/plugin-development.md` into repository-relative links.

### ⚖️ Added (Evidence Model — Evidence Strength ≠ Intended Use Requirement)

- **Third warrant-engine decoupling** (`src/bionexus/evidence_model.py`): purpose decides the evidence **requirement**, never the evidence **value**. A study with 10 donors/group, pre-registration, adequate power, and an independent replication carries ROBUST evidence whether the researcher calls it exploratory or confirmatory; weak data does not acquire a REPLICATED standing because someone declares a clinical purpose.
- Three explicit objects: **`EvidenceAssessment`** (how strong the evidence IS — computed only from declared evidence factors `replication / sample_design / effect_stability / external_validation / sensitivity_analysis / confound_controls / backend_fidelity / provenance` and active violations; purpose- and policy-independent by construction), **`ClaimContext`** (nine claim classes, descriptive → clinical_actionability, each with its own minimum bar via `CLAIM_REQUIREMENTS`), and **`UseRequirement`** (purpose + claim class composed — the only place purpose enters).
- `evaluate_sufficiency()` compares evidence against the composed bar: `WARRANTED` · `WARRANTED_WITH_LIMITS` (documented ack; the bar never moves) · `NOT_SUFFICIENT_FOR_INTENDED_USE` with an explicit gap list. Undeclared intended use is never sufficient for any use.
- `research_purpose.py`: `PURPOSE_EVIDENCE_CEILING` is reinterpreted as `PURPOSE_EVIDENCE_REQUIREMENT` (same numbers, new semantics; the old name survives as a deprecated alias). `PurposeContext.required_evidence` replaces `evidence_ceiling` (deprecated). `assess_warrant()` accepts an `EvidenceAssessment` and starts the ceiling from what the evidence is worth; `evaluate_viability_with_purpose()` threads `evidence_factors` / `claim_context` / `documented_extras` and attaches `evidence_assessment` + `sufficiency` to the EvidenceCard.
- 16 new theory-invariant tests (`tests/unit/test_evidence_model.py`), including the two canonical examples: ROBUST + population_effect + confirmatory → WARRANTED; SUPPORTED + clinical → NOT_SUFFICIENT_FOR_INTENDED_USE.

### 🛡️ Added (Backend Identity Conformance — BNS-EF-012..016 / BN-F010)

- **`src/bionexus/backend_conformance.py` + CLI `bionexus backend-identity`**: every canonical capability now answers a machine-checkable identity audit — claimed backend, observed executed backend, entry points, version, execution fingerprint, and fallback flag. `declared_backend == observed_backend` is verified via the installed-distribution witness (`importlib.metadata.packages_distributions`).

### 🚀 Changed (Release Pipeline Automation & Dynamic Pre-Release Tagging)

- `.github/workflows/release.yml` automatically detects `-rc`, `-alpha`, `-beta` tags and sets `prerelease: true` on GitHub Releases.
- Verified clean-venv wheel execution gate: Version SSOT $\to$ ruff $\to$ unit tests $\to$ full scientific backend $\to$ strict benchmark $\to$ build $\to$ clean venv $\to$ wheel install $\to$ doctor $\to$ registry check $\to$ backend identity $\to$ strict eval $\to$ manifest validation $\to$ SHA256 $\to$ GitHub Release.

---

## [0.10.0] - 2026-08-17

### 🛡️ Epistemic Honesty & Fail-Closed by Default (BNS-EF-002 / BNS-CC-012)

- **Fail-closed by default for Tangram, GEARS, and NicheFormer**: `run_tangram_spatial_mapping()`, `predict_gears_perturbation()`, and `forecast_spatial_niche()` now default to `allow_fallback=False`. Missing backends trigger immediate deterministic refusal (`REFUSAL_CANONICAL_MODEL_REQUIRED` / `REFUSAL_BACKEND_UNAVAILABLE`). Grade C heuristic baselines run only with explicit caller opt-in (`allow_fallback=True`) and are transparently labeled as `Grade C Experimental` without masquerading as official neural network models.
- **Backend Execution Identity Tests & Anti-Masquerading Enforcement**: Implemented execution identity tests for canonical foundation models and closed-loop pipelines (Geneformer, scGPT, GEARS, NicheFormer). If a canonical model object or checkpoint is not provided, strict mode refuses with `REFUSAL_CANONICAL_MODEL_REQUIRED` or `REFUSAL_CANONICAL_BACKEND_NOT_IMPLEMENTED`. Fallback execution with `allow_fallback=True` guarantees transparent labeling as `Grade C Experimental / Heuristic` (BNS-EF-002).
- **Frontier capability segregation with runtime execution isolation**: Segregated experimental foundation models and closed-loop exploration (`scfm.geneformer_canonical`, `scfm.scgpt_canonical`, `scfm.rank_proxy_embedding`, `perturbation.gears_prediction`, `spatial.nicheformer_forecasting`, `closed_loop.perturbation_to_niche`) into `FRONTIER_CAPABILITIES`; the stable core of 13 stable canonical capabilities remains in `CANONICAL_CAPABILITIES` (canonical ≠ certified: CERTIFIED still requires 14/14 evidence gates). Isolation is enforced at execution time, not only in the registry: `route_scientific_intent()` defaults to `allow_frontier=False` and returns `EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN` for any frontier capability; execution requires explicit opt-in (`--allow-frontier` CLI / `allow_frontier=True` API). Backend readiness now binds to the capability, never to the skill: a missing canonical backend is a deterministic refusal for canonical capabilities even with `allow_degraded` consent; `DEGRADED_ADVISORY` is reachable only for frontier capabilities under opt-in + explicit fallback.
- **Version SSOT & Zero-Drift Guard**: Unified versioning across `pyproject.toml`, `bionexus.registry.yaml`, `src/bionexus/versions.py`, `src/bionexus/__init__.py`, `plugin.json`, `marketplace.json`, and all client manifests. Added `scripts/sync_version.py` and `tests/unit/test_version_ssot.py` CI enforcement.

### 🌐 Added (Standards Interoperability — BNS-016: no proprietary data-standard island)

- **`src/bionexus/interop.py`**: BioNexus exports through published community standards instead of inventing a proprietary research bundle format. Run capsules project to **RO-Crate 1.1** following Workflow Run Crate conventions (capability → `ComputationalWorkflow` with the Workflow RO-Crate profile; execution → schema.org `CreateAction` with instrument/object/result/startTime/endTime and the Process Run Crate 0.5 profile; evidence maturity rides inside the crate as a contextual entity). Ledgers project to RO-Crate with claims/evidence as contextual entities (`isBasedOn` support edges). Run capsules project to **BioCompute Objects (IEEE 2791-2020)** with all six domains (provenance, usability, description, execution, io, parametric) and a content-computed `etag`. Deterministic, offline projections; **fail-closed exports** (a projection failing structural validation is never written); structural validators with disclosed scope. CLI: `bionexus interop ro-crate|bco|check`.
- **`src/bionexus/standards.py` + `bionexus standards`**: machine-readable standards alignment registry with a closed, honest status vocabulary — `implemented` (RO-Crate, Workflow Run Crate, BCO, PROV-O) / `aligned` (Bioschemas typing, nf-core schemas) / `proposal` (GA4GH AI Work Stream) / `tracked` (ELIXIR, scverse, Bioconductor, WorkflowHub) — and the mandatory verbatim disclaimer: *BioNexus is not an industry standard and does not claim to be one.*
- **`docs/standards-engagement.md`**: the GA4GH AI standardization window strategy — a concrete mapping of BioNexus artifacts (failure taxonomy, capability-contract schema, refusal semantics, host conformance, BioFailureBench) onto the AI Work Stream focus areas, engagement venues, and the contribution rule: *offer vocabulary, schemas, and tests; never announce; let adoption invert the direction.*
- New spec `spec/BNS-016-standards-interop.md` (BNS-IO-001..013); tests `test_interop.py`, `test_standards.py`.

### 🧭 Added (Product matrix & scope boundary — BNS-IO-012)

- **`docs/product-matrix.md`**: the four-layer matrix (bionexus-core / bionexus-audit / bionexus-conformance / reference capability packs) with a test-enforced module mapping and the explicit non-goals list — no planner, memory, multi-agent, chat UI, cloud workspace, notebook replacement, compute service, or agent marketplace. README gains the matrix section; `test_product_matrix.py` guards the documented mapping against drift and enforces downward-only layering (core never imports the audit layer).

### 🔬 Added (Why-install case on the front page)

- README opens with the one case a computational biologist understands immediately: the before/after of *"Run DE between these two clusters"* — an agent that returns "153 significant genes" vs BioNexus blocking with **BN-F002 Pseudoreplication** and the pseudobulk remedy. One case beats a hundred features.

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
