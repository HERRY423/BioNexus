# BioNexus Artifact Contract: Standardized Run Capsule Specification

## 🎯 Purpose & Multi-Agent Vision

In modern LLM-driven scientific workflows (across Claude Code, OpenAI Codex, Cursor, Antigravity), biological analysis tasks frequently span multiple turns, multiple specialized subagents, or multiple consecutive sessions. 

Without a rigorous **Artifact Contract**, downstream agents are forced to:
- Guess where intermediate AnnData `.h5ad` matrices or marker tables were written.
- Hallucinate which preprocessing parameters (resolution, min_counts, FDR cutoff) were applied.
- Re-run costly computations because they cannot ascertain if the previous run passed quality gates.
- Misinterpret unverified exploratory markers as causal differential expression findings.

The **BioNexus Run Capsule** provides a deterministic, machine-readable execution bundle contract that serves as the universal handoff interface between agents.

---

## 🏛️ Standard Directory Topology

Every executed BioNexus skill or pipeline outputs a standardized directory layout:

```text
run/
├── run.json            # Master Run Capsule Descriptor & Agent Handoff Manifest
├── inputs.json         # Input files, semantic data types, SHA-256 hashes, matrix stats
├── parameters.json     # Resolved hyperparameters and algorithmic configuration
├── results/            # Computed datasets (.h5ad, .csv, .parquet, .tsv)
│   ├── clustered.h5ad
│   └── markers.csv
├── figures/            # Generated visualizations (.png, .svg, .pdf, .html)
│   ├── qc_violin.png
│   └── umap_clusters.png
├── evidence.json       # EvidenceCard 2.0 (execution_state, dimension grades, conclusion_maturity)
├── provenance.json     # W3C PROV-O activity record with input/output cryptographic hashes
├── environment.json    # OS runtime, Python packages, CPU/RAM specs, pinned dependency versions
└── logs/               # Detailed execution stdout/stderr and preflight doctor reports
    └── pipeline.log
```

---

## 📄 Master Capsule Descriptor: `run.json`

The entry point for any agent reading previous work is `run.json`.

```json
{
  "run_id": "run_20260815_160800_scrna_exploratory_clustering",
  "bionexus_version": "0.8.0",
  "capability_id": "scrna.exploratory_clustering",
  "skill_name": "single-cell-rna-qc",
  "status": "COMPLETED",
  "execution_state": "EXECUTED",
  "conclusion_maturity": "SUPPORTED",
  "timestamp_start": "2026-08-15T16:08:00.123456+00:00",
  "timestamp_end": "2026-08-15T16:08:15.654321+00:00",
  "duration_seconds": 15.53,
  "artifacts": {
    "inputs_manifest": "inputs.json",
    "parameters_manifest": "parameters.json",
    "evidence_card": "evidence.json",
    "provenance_sidecar": "provenance.json",
    "environment_snapshot": "environment.json",
    "execution_log": "logs/pipeline.log",
    "primary_result": "results/clustered.h5ad",
    "results": [
      {
        "name": "clustered_anndata",
        "path": "results/clustered.h5ad",
        "semantic_type": "clustered_counts",
        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "size_bytes": 45219200
      },
      {
        "name": "cluster_markers",
        "path": "results/markers.csv",
        "semantic_type": "tabular_markers",
        "sha256": "5d41402abc4b2a76b9719d911017c592",
        "size_bytes": 104820
      }
    ],
    "figures": [
      {
        "title": "UMAP Leiden Clusters",
        "path": "figures/umap_leiden.png",
        "format": "png",
        "sha256": "7d793037a0760186574b0282f2f435e7",
        "size_bytes": 245000,
        "description": "UMAP projection colored by numeric cluster IDs."
      }
    ]
  },
  "downstream_suggestions": [
    {
      "intent": "differential_expression",
      "capability_id": "scrna.pseudobulk_de",
      "input_artifact": "results/clustered.h5ad",
      "recommended_command": "python skills/single-cell-rna-qc/scripts/scrna_pseudobulk.py --input results/clustered.h5ad",
      "rationale": "Identify robust condition DE genes using PyDESeq2 with biological replicates."
    }
  ]
}
```

---

## 🤖 How the Next Agent Interacts with a Run Capsule

When a new agent turn begins or a subagent receives a request like *"Continue the single-cell analysis and find differentially expressed genes"*, the agent can:

### 1. Inspect the Run Bundle via CLI or Python SDK
```bash
# Agent CLI inspection
bionexus run inspect run/
```
Output:
```text
============================================================
📦 BioNexus Run Capsule: run_20260815_160800_scrna_exploratory_clustering
============================================================
• Capability ID:       scrna.exploratory_clustering
• Skill Name:          single-cell-rna-qc
• Status:              COMPLETED (EXECUTED)
• Conclusion Maturity: SUPPORTED
• Duration:            15.53s

📊 Result Artifacts (2):
  - clustered_anndata: results/clustered.h5ad (clustered_counts) [PRIMARY]
  - cluster_markers: results/markers.csv (tabular_markers)

🤖 Next Agent Actionable Suggestions (1):
  1. Intent: differential_expression -> scrna.pseudobulk_de
     Input:   results/clustered.h5ad
     Command: python skills/single-cell-rna-qc/scripts/scrna_pseudobulk.py --input results/clustered.h5ad
     Why:     Identify robust condition DE genes using PyDESeq2 with biological replicates.
============================================================
```

### 2. Cryptographically Verify Capsule Integrity
```bash
bionexus run verify run/
```
Ensures zero data tampering, missing intermediate matrices, or broken pipelines.

### 3. Programmatic Usage in Python
```python
from bionexus.artifacts import RunBundle, load_run_bundle, verify_run_bundle

# Load capsule
capsule = load_run_bundle("run/")
primary_data = capsule["artifacts"]["primary_result"]
evidence = capsule["artifacts"]["evidence_card"]

# Verify before chaining downstream step
check = verify_run_bundle("run/")
if not check.valid:
    raise RuntimeError(f"Cannot chain pipeline: {check.notes}")
```

---

## 🔒 Immutability & Audit Invariants

1. **Deterministic Hashes**: All input and output datasets have SHA-256 digests generated at creation time.
2. **Epistemic Separation**: `evidence.json` contains full `EvidenceCard 2.0` dimensions, separating execution fidelity from statistical power.
3. **Reproducibility Guarantee**: `provenance.json` and `environment.json` record the exact platform, Python interpreter, CPU architecture, and pinned package versions.
