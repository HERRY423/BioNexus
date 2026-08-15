# BioNexus Plugin & Skill Development Guide

This guide defines the authoritative architecture, interfaces, and scientific standards for creating plugins and skills in **BioNexus**. 

Whether you are wrapping an official bioinformatics package (e.g. `scanpy`, `squidpy`, `scvi-tools`), contributing a format converter, or implementing a new computational pipeline, follow this specification to ensure your skill adheres to the **BioNexus Scientific Honesty Contract**.

---

## 🏛️ 1. BioNexus Skill Anatomy

Every BioNexus skill is encapsulated in a dedicated directory under `skills/<skill-name>/` and must follow this standard layout:

```text
skills/<skill-name>/
├── SKILL.md                 # Agent specification, capabilities, and refusal rules
├── scripts/                 # Executable Python pipeline modules
│   ├── <snake_name>_pipeline.py # Canonical entry point (Single Source of Truth)
│   └── _common.py           # Shared path resolution and bootstrapping
├── references/              # Scientific documentation, citations, and benchmarks
│   └── README.md
└── configs/                 # Default YAML / JSON parameter schemas
    └── default.yaml
```

Additionally, every skill must have corresponding unit tests in `tests/unit/`:
```text
tests/unit/
└── test_<snake_name>.py     # Pytest unit & regression tests with offline fixtures
```

---

## 📋 2. `SKILL.md` Specification & Frontmatter Schema

`SKILL.md` is the primary interface parsed by AI coding agents (Codex, Claude, Cursor) for tool routing and capability discovery.

### Standard Frontmatter Schema
```yaml
---
name: <kebab-case-name>                 # Required: Unique identifier matching directory name
display_name: "<Human-Readable Title>"  # Required: Formatted display title
description: <Short description>       # Required: Clear summary of capabilities and refusal conditions
tier: <core | wrapper | heuristic | outline> # Required: Capability tier
grade: <A | B | C | abstain | gold-wrapper | heuristic | outline> # Required: Default evidence grade
status: <canonical | active | heuristic | outline | deprecated> # Required: Lifecycle status
backend: "<Primary execution engine>"  # Required: e.g. "scanpy", "squidpy", "scvi-tools"
---
```

### Required Sections in `SKILL.md`
1. **Title & Summary**: Clear explanation of what the skill computes.
2. **Quick Start**: Command-line examples executing the canonical pipeline.
3. **Analytical Specifications & Matrix**: Table mapping each analytical step to its Python script, backend engine, and evidence grade.
4. **Scientific Honesty Invariants & Forbidden Actions**:
   - Explicitly state what the skill **cannot** do.
   - List forbidden actions (e.g., cell-type guessing, treating exploratory marker p-values as condition DE).
   - Define exact conditions under which the skill must **refuse**.

---

## 📐 3. Machine-Readable Scientific Capability Contracts

AI coding agents need more than human-readable markdown: they need **machine-actionable scientific contracts** that specify *when an analysis is scientifically valid* and *when it is statistically/biologically invalid and must be refused*.

In BioNexus, every biological capability defines a formal `CapabilityContract` ([`src/bionexus/capabilities.py`](file:///c:/Plugin/BioNexus/src/bionexus/capabilities.py)):

```yaml
capability:
  id: scrna.pseudobulk_de
  version: 1
  display_name: "Single-Cell Pseudobulk Differential Expression"
  skill_name: "single-cell-rna-qc"

intent:
  - compare_conditions
  - differential_expression
  - treatment_effect

inputs:
  expression:
    semantic_type: raw_counts
    required: true
    validation_rule: "audit_expression_matrix:counts"
  sample_design:
    semantic_type: sample_metadata
    required: true

preconditions:
  - id: min_replicates
    rule: "n_replicates_per_condition >= 2"
    description: "At least 2 biological replicates per group to estimate dispersion."
  - id: raw_integer_counts
    rule: "is_integer_like(counts) == True"
    description: "Negative binomial GLM requires discrete integer counts."

backend:
  canonical:
    name: pydeseq2
    minimum_version: 0.4.0
    extra: deseq

refusal_conditions:
  - id: normalized_matrix_only
    description: "Continuous floats provided where raw counts required."
    remedy: "Sum unnormalized raw counts (adata.raw.X) over (sample, condition) before testing."
  - id: missing_replicates
    description: "Fewer than 2 biological replicates per group."
    remedy: "Condition DE is invalid without replicates (pseudoreplication). Collect replicates or report exploratory rankings only."
  - id: missing_backend
    description: "PyDESeq2 backend missing."
    remedy: "Install via `pip install bionexus[deseq]`."

evidence_requirements:
  multiple_testing: required
  effect_size: required
  min_fdr_alpha: 0.05
```

### Querying and Evaluating Capabilities via Python / CLI
```python
from bionexus.capabilities import evaluate_capability_preconditions

result = evaluate_capability_preconditions(
    "scrna.pseudobulk_de",
    input_metadata={"min_replicates_per_condition": 1, "is_normalized": True}
)

if not result.permitted:
    # Deterministic scientific refusal with actionable remedies
    print(f"Refusal Status: {result.status}")
    print(f"Violations: {result.violations}")
    print(f"Actionable Remedies: {result.remedies}")
```

```bash
# Query capabilities via CLI
bionexus capability list --intent differential_expression
bionexus capability show scrna.pseudobulk_de
bionexus capability check scrna.pseudobulk_de --min-replicates 1
```

---

## 🚦 4. The 6-Stage Scientific Intent & Invariant Router

BioNexus replaces static skill lookup with a validated 6-stage **Scientific Intent Routing Pipeline** ([`src/bionexus/intent_router.py`](file:///c:/Plugin/BioNexus/src/bionexus/intent_router.py)):

```text
User Scientific Prompt ("compare tumor vs normal in my scRNA data")
                     │
                     ▼
       1. Identify Analytical Intent (e.g. compare_conditions)
                     │
                     ▼
       2. Inspect Data Semantics (counts vs log-floats, matrix shape)
                     │
                     ▼
       3. Check Scientific Preconditions (replicates >= 2, valid geometry)
                     │
                     ▼
       4. Match Canonical Capability (scrna.pseudobulk_de)
                     │
                     ▼
       5. Probe Backend Lifecycle (pydeseq2 installed vs missing)
                     │
                     ▼
       6. Authoritative Routing Decision:
          ├── [PERMITTED]         -> Execute Gold-Chain (PyDESeq2)
          ├── [NEEDS_DATA]        -> Request missing biological replicates in adata.obs
          ├── [ABSTAIN]           -> Prohibit pseudoreplication with remedies
          └── [DEGRADED_ADVISORY] -> Grade C fallback notice
```

### Programmatic & CLI Usage
```python
from bionexus.agent_routing import route_scientific_intent, RoutingStatus

# Agent evaluates user query with available data metadata
decision = route_scientific_intent(
    query="compare tumor vs normal in my scRNA data",
    data_metadata={"min_replicates_per_condition": 1}  # Single sample
)

if decision.status == RoutingStatus.ABSTAIN:
    # Host agent directly receives reasons to refuse invalid analysis
    print(decision.rationale)
    print("Scientific Remedies:", decision.remedies)
```

```bash
# Agent or user CLI routing
bionexus route "compare treated vs control in scRNA"
# -> [NEEDS DATA] Please provide biological replicate identifiers in adata.obs (e.g. sample_id, donor_id, batch).

bionexus route "compare treated vs control in scRNA" --min-replicates 1
# -> [ABSTAIN] Fewer than 2 biological replicates per experimental condition (pseudoreplication).

bionexus route "compare treated vs control in scRNA" --min-replicates 3
# -> [PERMITTED] Analysis is scientifically valid.
#    Recommended Script: skills/single-cell-rna-qc/scripts/scrna_deseq.py
```

---

## 🧬 5. The Scientific Evidence Operating Layer (EvidenceCard 2.0)

BioNexus strictly decouples **Execution Fidelity** (whether an algorithm successfully computed) from **Scientific Evidence Quality** (statistical power, input validity, parameter sensitivity, and external replication).

Every canonical pipeline must construct and attach an `EvidenceCard` (v2.0) with three distinct layers:

```python
from bionexus.contracts import (
    GRADE_A,
    GRADE_B,
    GRADE_C,
    UNTESTED,
    EvidenceCard,
    ExecutionState,
    attach_meta,
    refuse,
)

# Construct EvidenceCard 2.0
card = EvidenceCard(
    # Layer 1: Execution State
    execution_state=ExecutionState.EXECUTED.value,  # EXECUTED / DEGRADED / REFUSED / FAILED
    
    # Layer 2: Evidence Dimensions
    input_integrity=GRADE_A,             # A: verified raw/normalized scale / B: plausible / C: invalid scale or NaNs
    assumption_validity=GRADE_A,         # A: verified distribution / B: standard assumed / C: violated
    statistical_support=GRADE_A,         # A: FDR q < 0.05 / B: unadjusted p < 0.05 / C: marginal / INSUFFICIENT
    parameter_robustness=GRADE_A,        # A: stable across sweeps / B: moderate / C: fragile / UNTESTED
    cross_method_concordance=UNTESTED,   # A: unanimous / B: majority / C: conflicted / UNTESTED
    external_validation=UNTESTED,        # A: recovers ground truth / B: partial / C: inconsistent / UNTESTED
    details={
        "backend": "scanpy",
        "n_samples": 1200,
        "fdr_threshold": 0.05,
        "robustness_notes": "ARI > 0.85 across Leiden resolution sweeps 0.4 - 1.2"
    }
)

# Synthesize overall ConclusionMaturity and attach standard metadata
result = attach_meta(
    payload={
        "n_clusters": 5,
        "cluster_labels": ["0", "1", "2", "3", "4"],
    },
    method="my_skill_gold_chain",
    backend="scanpy",
    evidence_grade=GRADE_A,
    limitations=[
        "Research-use only.",
        "Clusters are numeric; cell types must be verified with orthogonal markers."
    ],
    evidence_card=card,
)
```

### ConclusionMaturity Epistemic Hierarchy
- `REPLICATED`: Validated against external independent benchmarks + robust under parameter sweeps + strong statistics.
- `ROBUST`: Supported on current data AND verified stable under parameter sweeps/perturbations (`parameter_robustness: "A"`).
- `SUPPORTED`: Current dataset directly supports hypothesis (Inputs `A`, Assumptions `A`/`B`, Statistics `A`).
- `PRELIMINARY`: Baseline single-run execution with standard assumptions (Exploratory baseline).
- `FRAGILE`: Parameter sensitivity (`parameter_robustness: "C"`), violated assumptions, or suspect input scaling.
- `CONFLICTED`: Contradictory findings across alternative algorithms (`cross_method_concordance: "CONFLICTED"`).
- `ABSTAIN`: Missing required backend, violated hard constraints, or clinical claim refusal.

---

## 🔍 4. Data Semantics & Integrity Auditing

Pipelines must audit input data semantics using `bionexus.integrity` before computing downstream metrics.

### Auditing Expression Matrices (`audit_expression_matrix`)
Prevents silent mathematical distortions, such as passing log-normalized continuous floats into negative binomial models expecting integer counts:

```python
from bionexus.integrity import audit_expression_matrix

grade, notes, stats = audit_expression_matrix(
    matrix, 
    expected_type="counts"  # "counts" or "normalized"
)

if grade == "C":
    # Fatal input defect (e.g. NaNs, infinities, or negative values)
    return refuse(
        method="my_pipeline",
        reason=f"Data integrity audit failed: {'; '.join(notes)}"
    )
```

### Auditing Spatial Coordinates (`audit_spatial_coordinates`)
```python
from bionexus.integrity import audit_spatial_coordinates

grade, notes, stats = audit_spatial_coordinates(adata.obsm["spatial"])
if grade == "C":
    return refuse(
        method="spatial_knn_graph",
        reason=f"Spatial coordinates invalid: {'; '.join(notes)}"
    )
```

---

## 🚫 5. Deterministic Backend Verification & Refusal

BioNexus forbids silently substituting a local heuristic under the name of a gold-standard package.

```python
from bionexus.backends import BackendUnavailable, require
from bionexus.contracts import refuse

try:
    require("scanpy", for_method="run_scrna_gold_chain", min_version="1.10.0")
except BackendUnavailable as e:
    return refuse(
        method="run_scrna_gold_chain",
        reason=str(e),
        extra={"error_type": "missing_dependency"}
    )
```

---

## 📦 6. Provenance Tracking & W3C PROV-O Sidecars

Every file-producing pipeline must emit a companion `.provenance.json` sidecar capturing cryptographic SHA-256 checksums, execution parameters, and runtime environment:

```python
import json
from bionexus.provenance import sidecar

sidecar_data = sidecar(
    activity_name="scrna_clustering",
    input_files=["data/raw_counts.h5ad"],
    output_files=["results/clustered.h5ad", "results/markers.csv"],
    method="scanpy_gold_chain",
    backend="scanpy",
    parameters={"resolution": 0.8, "n_top_genes": 2000},
)

with open("results/clustered.h5ad.provenance.json", "w", encoding="utf-8") as f:
    json.dump(sidecar_data, f, indent=2)
```

---

## 🌟 7. Gold Reference Walkthrough (`single-cell-rna-qc`)

Study `skills/single-cell-rna-qc/` as the canonical model:
- **`SKILL.md`**: Defines clean steps (inspect → convert → QC → doublets → preprocess → cluster → markers → plots → pseudobulk → DE).
- **`scripts/scrna_pipeline.py`**:
  - Enforces `require("scanpy")`.
  - Runs `audit_expression_matrix()` on `adata.X`.
  - Enforces numeric Leiden cluster labels only (no cell-type hallucination).
  - Emits 7-dimensional `EvidenceCard`.
  - Generates `.provenance.json` sidecar.
- **`tests/unit/test_scrna_gold_chain.py`**:
  - Uses fast synthetic planted datasets (`_planted_scrna()`).
  - Verifies recovery of planted marker genes (`CD3D`, `MS4A1`, `CD14`).
  - Asserts absence of cell-type hallucination in outputs.

---

## 🚀 8. Scaffolding a New Skill with the CLI

Use the BioNexus CLI to generate a complete skill scaffold adhering to all requirements:

```bash
# 1. Generate skill skeleton
bionexus create-plugin my-new-skill \
  --tier core \
  --grade A \
  --backend scanpy \
  --description "High-throughput single-cell pathway scoring pipeline"

# 2. Implement your algorithm in:
#    skills/my-new-skill/scripts/my_new_skill_pipeline.py

# 3. Run unit tests
pytest tests/unit/test_my_new_skill.py -v

# 4. Sync multi-platform manifests
bionexus registry --generate

# 5. Verify zero configuration drift
bionexus registry --check
```

---

## 🏆 9. BioNexus Eval (Agent Behavior & Scientific Reliability Benchmark)

BioNexus includes a comprehensive **Agent Behavior & Epistemic Reliability Benchmark** (`evals/`) evaluating AI agents on real scientific prompts across 8 core reliability pillars:

| Metric | Target | Scientific Significance |
|---|---|---|
| **Routing Accuracy** | `> 95.0%` | Correct capability and toolchain selected |
| **Unsafe Invocation Rate** | `0.0%` | Frequency of running invalid analyses (Target: zero) |
| **Abstention Precision** | `> 95.0%` | Refusals are scientifically justified |
| **Abstention Recall** | `> 95.0%` | Catches pseudoreplication, wrong distributions, etc. |
| **Capability Hallucination Rate** | `0.0%` | Zero fabricated cell-types, methods, or regulatory claims |
| **Backend Fidelity** | `> 95.0%` | Accurate toolchain declaration and degradation honesty |
| **Scientific Semantic Error Rate** | `0.0%` | Zero confusion of raw/log, cell/sample, or marker/DE |
| **Evidence Calibration Score** | `> 90.0%` | EvidenceCard maturity accurately reflects data quality |
| **Composite Reliability Index (CRI)** | **`> 95.0%`** | Unified weighted scientific quality index |

### Running the Benchmark
```bash
# Run full benchmark across all 6 test suites
bionexus eval

# Run a specific evaluation suite
bionexus eval --suite refusal
bionexus eval --suite routing
bionexus eval --suite adversarial

# Export structured JSON or Markdown report
bionexus eval --report evals/reports/benchmark_report.md
bionexus eval --json
```

Following this guide ensures your contributions seamlessly integrate into BioNexus, pass all CI checks, and provide dependable scientific results across AI coding platforms.

