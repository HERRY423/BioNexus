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

## 🧬 3. The Scientific Evidence Operating Layer

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

Following this guide ensures your contributions seamlessly integrate into BioNexus, pass all CI checks, and provide dependable scientific results across AI coding platforms.
