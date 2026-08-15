# Contributing to BioNexus

Welcome to **BioNexus**! We are building the **Scientific Reliability Layer for Agentic Biology**—transforming AI coding agents (OpenAI Codex, Claude Code, Cursor) into rigorous, peer-reviewed computational biology assistants.

To enable the broader scientific and developer community to safely contribute to BioNexus, all contributions must adhere to our **Scientific Honesty Contract**, **Canonical Architecture Rules**, and **Pull Request Acceptance Criteria**.

---

## 📜 The Scientific Honesty Contract (Non-Negotiables)

BioNexus is built on an uncompromising commitment to scientific veracity. Every line of code, prompt, and analytical pipeline must obey these non-negotiable invariants:

### 1. Zero Fabrication & Zero Hallucination
- **Never fabricate or hallucinate** biological findings, benchmark metrics, sequence alignments, p-values, or clinical evidence.
- **Never auto-assign biological cell-type labels** from exploratory single-cell clustering. Clusters must remain numeric unless validated against external reference ground truth.
- **Never publish marker gene p-values** as experimental condition treatment effect p-values. Condition DE strictly requires pseudobulk replicate aggregation and formal Wald/LRT tests (e.g. PyDESeq2).

### 2. "One Feature → One Canonical Implementation"
- Each biological functionality in BioNexus must have exactly **one designated Canonical implementation** (e.g. `single-cell-rna-qc` is the single canonical entry point for scRNA-seq QC and clustering).
- Do not create parallel, duplicate, or divergent implementations of the same analytical pipeline.
- All multi-platform manifests (`plugin.json`, `mcp.json`, `.claude-plugin/`, `.codex/`, `marketplace.json`) are compiled from the Single Source of Truth (`bionexus.registry.yaml`).

### 3. Explicit Backend Probing & Deterministic Refusal
- Never claim an algorithm ran if it did not.
- Never substitute a simplified local heuristic under the name of a gold-standard community tool (e.g. do not call a BLOSUM lookup an "ESM-2 language model", and do not call a local NNLS deconvolution "SoupX" or "CellBender").
- When a required backend library or binary is absent from the user's environment, the pipeline must **cleanly refuse** using `bionexus.contracts.refuse()` with `EvidenceGrade.ABSTAIN`.

### 4. Mandatory EvidenceCard 2.0 Three-Layer Epistemic Architecture
- Every numeric, classification, or predictive endpoint must return a structured `EvidenceCard` structured into three distinct epistemic layers:
  1. **Layer 1: Execution State** (`EXECUTED`, `DEGRADED`, `REFUSED`, `FAILED`): Answers "Did the computational method actually execute and with what technical fidelity?" Decoupled entirely from the scientific conclusion itself.
  2. **Layer 2: Evidence Dimensions & Qualitative Status** (`A`, `B`, `C`, `UNTESTED`, `NOT_APPLICABLE`, `INSUFFICIENT`, `CONFLICTED`):
     - **Input Integrity**: Were input matrices verified (raw counts vs log-scaled, NaN/Inf checks, non-negative)?
     - **Assumption Validity**: Are statistical distribution assumptions met?
     - **Statistical Support**: Are FDR-adjusted q-values and effect sizes significant?
     - **Parameter Robustness**: Is the finding stable across hyperparameter sweeps (`audit_parameter_stability`)? (*UNTESTED $\neq$ Fragile*)
     - **Cross-method Concordance**: Do orthogonal methods agree? (*UNTESTED $\neq$ Conflicted*)
     - **External Validation**: Has the result been benchmarked against ground truth?
  3. **Layer 3: Conclusion Epistemic Maturity** (`ABSTAIN` $\to$ `FRAGILE` $\to$ `CONFLICTED` $\to$ `PRELIMINARY` $\to$ `SUPPORTED` $\to$ `ROBUST` $\to$ `REPLICATED`):
     - `PRELIMINARY`: Baseline single-run execution with standard assumptions.
     - `SUPPORTED`: Current data directly supports hypothesis (Inputs A, Assumptions A/B, Stats A).
     - `ROBUST`: Supported AND proven stable across parameter sweeps.
     - `REPLICATED`: Robust AND validated against independent external datasets/benchmarks.

### 5. Decoupling Execution Fidelity from Scientific Evidence Quality
- Successfully running an algorithm (`execution_state: "EXECUTED"`) does not prove a scientific hypothesis is true if input data was unverified (`input_integrity: "C"`), sample size was inadequate (`statistical_support: "INSUFFICIENT"`), or parameters are fragile.
- The synthesized `ConclusionMaturity` must reflect this nuance.


### 6. Research Use Only (RUO) & Regulatory Disclaimers
- BioNexus is strictly for research use. All clinical or genomic interpretation outputs must include non-negotiable disclaimers stating that the system is not a clinical diagnostic and not CLIA/CAP validated.

---

## 🚦 Definition of Done & PR Acceptance Criteria

Before submitting a Pull Request, verify that your contribution satisfies all criteria:

- [ ] **100% Green CI**: All matrix test jobs (Ubuntu, macOS, Windows across Python 3.10, 3.11, 3.12) pass with zero failures.
- [ ] **Zero Configuration Drift**: Running `bionexus registry --check` (or `python scripts/registry_compiler.py --check`) reports `[OK] All platform manifests are strictly in sync with bionexus.registry.yaml`.
- [ ] **Zero Ruff Lint Violations**: Running `ruff check .` completes with zero errors.
- [ ] **Deterministic Offline Tests**: Every skill includes fast unit tests in `tests/unit/test_<snake_case_name>.py` using synthetic fixtures from `tests/fixtures/` that run without mandatory network access.
- [ ] **Evidence Contract Compliance**: All pipeline functions wrap results with `attach_meta()`, evaluate `audit_expression_matrix()` / `audit_spatial_coordinates()`, attach an `EvidenceCard`, and write a `.provenance.json` sidecar.
- [ ] **Gold Reference Anatomy**: Skill folders must follow the Gold Reference structure defined in `skills/single-cell-rna-qc/`.

---

## 🧬 Skill Lifecycle & Capability Tiers

BioNexus categorizes skills into clear lifecycle tiers:

| Tier | Status | Grade | Description | Examples |
| :--- | :--- | :---: | :--- | :--- |
| **`core`** | `canonical` | `A` | Official gold-standard community toolchain wrappers. Default route for real data analyses. | `single-cell-rna-qc`, `spatial-transcriptomics`, `scvi-tools`, `nextflow-development` |
| **`wrapper`** | `canonical` | `A` / `B` | Standard format converters and provenance sidecars. | `instrument-data-to-allotrope`, `provenance-and-audit` |
| **`heuristic`** | `heuristic` | `B` / `C` | Local domain approximations. Permitted only with explicit doctor notice and mandatory limitation disclosures. | `variant-interpretation`, `biologics-design`, `clinical-cohort-analysis` |
| **`outline`** | `canonical` | `outline` | Study design templates and session orientation. Never claims analysis. | `start`, `scientific-problem-selection` |
| **`deprecated`** | `deprecated` | `C` | Legacy heuristics scheduled for removal. Maintained only for legacy backward compatibility. | `qc_analysis.py`, `ambient_rna.py` |

---

## 🛠️ Contributor Development Workflow

### 1. Fork and Clone the Repository
```bash
git clone https://github.com/<your-username>/BioNexus.git
cd BioNexus
```

### 2. Set Up the Development Environment
```bash
# Create virtual environment
python -m venv .venv
# Activate virtual environment (Windows: .venv\Scripts\activate | Unix: source .venv/bin/activate)

# Install development dependencies and editable package
pip install -r requirements-dev.txt
pip install -e ".[all]"
```

### 3. Scaffold a New Skill
Use the official BioNexus CLI to generate a complete skill scaffold matching the Gold Reference pattern:

```bash
bionexus create-plugin <skill-name> \
  --tier core \
  --grade A \
  --backend scanpy \
  --description "Short description of the analytical capability"
```

This generates:
- `skills/<skill-name>/SKILL.md` (Specification, instructions, and refusal rules)
- `skills/<skill-name>/scripts/<skill_name>_pipeline.py` (Canonical pipeline entry point)
- `skills/<skill-name>/scripts/_common.py` (Shared imports and path configuration)
- `skills/<skill-name>/references/README.md` (Scientific literature and citations)
- `skills/<skill-name>/configs/default.yaml` (Default configuration parameters)
- `tests/unit/test_<skill_name>.py` (Unit tests with EvidenceCard verification)

### 4. Implement Analytical Pipeline
- Implement domain algorithms inside `skills/<skill-name>/scripts/`.
- Validate input matrices with `bionexus.integrity.audit_expression_matrix()`.
- Enforce backend dependencies with `bionexus.backends.require("<backend_name>", for_method="...")`.
- Return metadata and `EvidenceCard` via `bionexus.contracts.attach_meta()`.

### 5. Synchronize Platform Manifests
If you added or modified MCP endpoints or registry metadata, synchronize all platform adapters:
```bash
bionexus registry --generate
```

### 6. Run Quality Checks, Test Suite & Reliability Benchmark
```bash
# Run Ruff linter
ruff check .

# Check manifest synchronization
bionexus registry --check

# Run full test suite
pytest tests/ -v

# Run BioNexus Eval Benchmark (Composite Reliability Index >= 95%)
bionexus eval

# Run gold-chain smoke test
python scripts/goldchain_smoke.py
```

### 7. Governance, Versioning & Releases
- **Semantic Versioning**: Adhere to [`docs/versioning-policy.md`](file:///c:/Plugin/BioNexus/docs/versioning-policy.md).
- **Compatibility Matrix**: Verify platform & library support in [`docs/compatibility-matrix.md`](file:///c:/Plugin/BioNexus/docs/compatibility-matrix.md).
- **Deprecation Rules**: Consult [`docs/deprecation-policy.md`](file:///c:/Plugin/BioNexus/docs/deprecation-policy.md).
- **Changelog**: Add an entry under `## [Unreleased]` in [`CHANGELOG.md`](file:///c:/Plugin/BioNexus/CHANGELOG.md).

### 8. Submit Your Pull Request
Push your branch to GitHub and open a Pull Request against `main`. Ensure your PR description includes:
- Summary of the new skill or architectural improvement.
- Evidence that all CI tests and `bionexus eval` benchmark cases are green.
- Example inputs and outputs demonstrating `EvidenceCard` synthesis.
