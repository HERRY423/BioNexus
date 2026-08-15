# BioNexus: The Scientific Reliability Layer for Agentic Biology

[![Agent Plugins 1.0.0](https://img.shields.io/badge/Agent%20Plugins-1.0.0-blue.svg)](https://agent-plugins.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Official%20SDK-orange.svg)](https://modelcontextprotocol.io/)
[![Codex Ready](https://img.shields.io/badge/Codex-Plugin%20Ready-green.svg)](https://openai.com/)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Compatible-purple.svg)](https://claude.ai/)
[![Cursor MCP](https://img.shields.io/badge/Cursor-MCP%20Ready-black.svg)](https://cursor.com/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

> **BioNexus** is the computational biology infrastructure designed for AI coding agents (**Codex**, **Claude Code**, **Cursor**). It equips LLMs with peer-reviewed bioinformatics workflows, deterministic evidence grading, multi-database MCP connectivity, and honest scientific abstention when gold-standard conditions fail.

```text
✓ Single-Cell RNA-seq QC & Clustering      ✓ Spatial Transcriptomics (Squidpy)
✓ scVI Deep Generative Modeling             ✓ nf-core Pipeline Execution (RNA-seq / Sarek)
✓ 16+ Local MCP Biological Database Tools   ✓ 9 Cloud Hosted Biological MCP Endpoints
✓ 7-Dimensional EvidenceCard Grading        ✓ W3C PROV-O Provenance Tracking
✓ Safe Refusal & Non-negotiable Honesty
```

---

## ⚡ Quick Start: Choose Your AI Environment

Install BioNexus in your AI coding environment in under 5 minutes:

### 1. Codex — Recommended (OpenAI / ChatGPT)
Codex natively loads BioNexus skills, analysis rules, and MCP endpoints as a structured capability pack.

- **Option A: Plugin Directory (Production)**
  1. Open the **Plugin Directory** in Codex / ChatGPT.
  2. Search for **`BioNexus`** and click **Install**.
  BioNexus provides biomedical workflow skills, scientific reliability rules, MCP-backed biological databases, and provenance-aware analysis.

- **Option B: Add Marketplace (GitHub Source — GUI)**
  1. In the Codex interface, click **"Add Plugin Marketplace" (添加插件市场)**.
  2. Fill in the repository details:
     - **Source (来源)**: `HERRY423/BioNexus` *(or `https://github.com/HERRY423/BioNexus.git`)*
     - **Git Reference (Git 引用)**: `main`
     - **Sparse Path (稀疏路径)**: **⚠️ Leave EMPTY — do NOT enter `.`**
  3. Click **Add Marketplace (添加市场)**.

  > ⚠️ **Important**: Do NOT enter `.` in the Sparse Path field. A `.` sparse-checkout pattern excludes dot-prefixed directories (`.agents/`, `.codex-plugin/`), which contain the required marketplace and plugin manifests. Leaving it empty clones the full repository correctly.

- **Option C: Add Marketplace (CLI)**
  ```bash
  # Add the BioNexus marketplace source from GitHub
  codex plugin marketplace add HERRY423/BioNexus --ref main

  # Install and enable the bio-research plugin
  codex plugin add bio-research@bionexus-marketplace
  ```

---

### 2. Claude Code (Anthropic Claude CLI & Desktop)
Claude Code auto-discovers skill manifests from [`.claude-plugin/plugin.json`](file:///.claude-plugin/plugin.json) and routes biological queries to BioNexus tools.

- **Install via Claude CLI**:
  ```bash
  claude plugin add HERRY423/BioNexus
  ```
- **Configure Claude Desktop (`claude_desktop_config.json`)**:
  ```json
  {
    "mcpServers": {
      "bio-research": {
        "command": "python",
        "args": ["<path-to-BioNexus>/scripts/local_mcp_server.py"]
      }
    }
  }
  ```

---

### 3. Cursor (AI Code Editor)
Cursor integrates BioNexus via the **Model Context Protocol (MCP)** layer, providing direct LLM tool access to 16 biological databases (UniProt, Ensembl, gnomAD, PDB, AlphaFold DB, Reactome, STRING, GEO, GTEx).

- **Step 1: Clone and Set Up BioNexus**:
  ```bash
  git clone https://github.com/HERRY423/BioNexus.git
  cd BioNexus
  pip install -e ".[dev,goldchain]"
  ```
- **Step 2: Add BioNexus MCP in Cursor**:
  In Cursor **Settings → Features → MCP Servers → Add New MCP Server**:
  - **Name**: `bio-research`
  - **Type**: `command` (stdio)
  - **Command**: `python scripts/local_mcp_server.py`
  
  *Or add to your project `.cursor/mcp.json`:*
  ```json
  {
    "mcpServers": {
      "bio-research": {
        "command": "python",
        "args": ["${workspaceFolder}/scripts/local_mcp_server.py"]
      }
    }
  }
  ```
- **Step 3**: Reload MCP servers in Cursor. Cursor can now call all BioNexus tools directly during chat and editing.

---

### 4. Standalone Python CLI (Developers & HPC Clusters)
For headless pipelines, automated workflows, and HPC slurm scripts:

```bash
# Clone and install dependencies
git clone https://github.com/HERRY423/BioNexus.git
cd BioNexus

# Windows
.\setup.ps1

# Linux / macOS
chmod +x setup.sh && ./setup.sh

pip install -e ".[dev,goldchain]"
```

**Optional Analysis Stacks:**
```bash
pip install -e ".[goldchain]"   # scanpy, leidenalg, harmonypy, pydeseq2
pip install -e ".[scverse]"     # goldchain + scvi-tools + torch
pip install -e ".[spatial]"     # squidpy
pip install -e ".[survival]"    # lifelines
pip install -e ".[plm]"         # transformers (ESM-2; set BIONEXUS_ALLOW_ESM=1)
pip install -e ".[structure]"   # abnumber, biotite
pip install -e ".[biologics]"   # ViennaRNA
pip install -e ".[allotrope]"   # Allotrope ASM data conversion
```

---

## 📊 Environment Compatibility Matrix

| AI Environment | Agent Workflow Skills | Local MCP (16 Tools) | Hosted Cloud MCP (9 Nodes) | Python Workflows | Support Tier |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Codex** | ✅ Native | ✅ Auto-loaded | ✅ Streamable-HTTP | ✅ Fully supported | **Recommended** |
| **Claude Code** | ✅ `.claude-plugin` | ✅ Stdio | ✅ Streamable-HTTP | ✅ Fully supported | **Supported** |
| **Cursor** | *(via MCP)* | ✅ Stdio | ✅ HTTP Bridge | ✅ Python scripts | **Supported** |
| **Python CLI / HPC** | — | *(Optional)* | *(Optional)* | ✅ Direct CLI / scripts | **Supported** |

> **Architecture Principle**: Multi-client installation interfaces across Codex, Claude Code, and Cursor are all compiled from a single canonical source of truth ([`bionexus.registry.yaml`](file:///bionexus.registry.yaml)). No duplicated logic, zero manifest drift.

---

## 🔍 Step 2: Verify Your Installation

Run the BioNexus environment diagnostic to verify backend health:

```bash
python scripts/doctor.py
```

**Example Diagnostic Report:**
```text
============================================================
                   BioNexus Environment Doctor
============================================================
Platform:        Linux / macOS / Windows
Tier:            FULL (scverse ready, spatial ready)
Python:          3.11.x

Installed Backends:
  [PASS] scanpy (1.10.x)       - scverse single-cell analysis
  [PASS] squidpy (1.3.x)       - spatial transcriptomics & graphs
  [PASS] pydeseq2 (0.4.x)      - pseudobulk differential expression
  [PASS] lifelines (0.28.x)    - survival analysis (Kaplan-Meier & Cox PH)
  [PASS] FastMCP (1.0.x)       - official Model Context Protocol SDK

Agent Integration Status:
  [PASS] Codex Config:         .codex/config.json valid
  [PASS] Claude Manifest:      .claude-plugin/plugin.json valid
  [PASS] MCP Registry:         mcp.json in sync (0 drift)
  [PASS] Local MCP Tools:      16 scientific tools registered
  [PASS] Hosted MCP Nodes:     7/9 reachable endpoints

Allowed Scientific Actions:
  ✓ scRNA-seq QC, MAD outlier filtering, and Leiden clustering
  ✓ Spatial Moran's I Spatially Variable Genes (SVGs)
  ✓ Pseudobulk condition differential expression (DESeq2)
  ✓ Multi-database biological entity retrieval
============================================================
```

---

## 🚀 Step 3: Run Your First Biological Workflow (30-Second Prompts)

Copy and paste these prompts directly into your AI environment to verify functionality:

### Prompt 1: Inspect Environment & Available Skills (Codex / Claude Code)
```text
Use BioNexus to inspect this repository environment and tell me which biological workflows and MCP databases are currently available. Do not install anything yet.
```

### Prompt 2: Biological Database Retrieval (Cursor / MCP)
```text
Using the BioNexus MCP tools, search for UniProt protein 'P04637' (TP53) and retrieve its active functional domains, known pathogenic variants in ClinVar, and experimental 3D structures in PDB.
```

### Prompt 3: Single-Cell Quality Control & Clustering (Codex / Claude Code / CLI)
```text
Use BioNexus to inspect my dataset 'sample.h5ad'. Perform MAD-based QC outlier detection, compute Leiden clusters with numeric labels, identify top cluster markers, and generate an EvidenceCard with provenance tracking.
```

---

## 🧬 How BioNexus Works: The Scientific Evidence Operating Layer

BioNexus separates **Execution Authenticity** (did the official method run?) from **Scientific Evidence Quality** (input integrity, assumption validity, statistical power, parameter robustness, cross-method concordance, and external validation).

Every analysis payload automatically attaches a multi-dimensional **`EvidenceCard`** and synthesized **`ConclusionStatus`**:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BioNexus Evidence Card                             │
├──────────────────────────┬────────┬─────────────────────────────────────────┤
│ Dimension                │ Grade  │ Evaluation Notes                        │
├──────────────────────────┼────────┼─────────────────────────────────────────┤
│ 1. Execution Fidelity    │ A      │ Official squidpy / scanpy backend ran   │
│ 2. Input Integrity       │ A      │ Verified non-negative raw integer counts│
│ 3. Assumption Validity   │ A      │ Spatial coordinates & scale verified    │
│ 4. Statistical Support   │ A      │ 12 SVGs pass FDR q < 0.05               │
│ 5. Parameter Robustness  │ B      │ Stable across k=6,8 neighbors           │
│ 6. Cross-method Agree    │ UNTESTED│ Single autocorrelation method tested   │
│ 7. External Validation   │ UNTESTED│ No orthogonal ground truth supplied    │
├──────────────────────────┴────────┴─────────────────────────────────────────┤
│ Synthesized Conclusion Status:                                              │
│ [ SUPPORTED | TENTATIVE | FRAGILE | CONFLICTED | ABSTAIN ]                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Core Scientific Skills

| Skill | Gold-Standard Backend | Evidence Grade | Non-negotiable Honesty Rule |
| :--- | :--- | :---: | :--- |
| `single-cell-rna-qc` | `scanpy` | **A** | Cell clusters remain **numeric only**. Never invent cell-type labels without reference models. |
| `spatial-transcriptomics` | `squidpy` | **A** | Requires real 2D/3D spatial coordinates. Refuses if coordinates are missing. |
| `scvi-tools` | `scvi-tools`, `torch` | **A** | Deep generative VAE modeling. Refuses if GPU/package missing. |
| `nextflow-development` | `nextflow`, `nf-core` | **A** | Validates FASTQ/BAM samplesheet. Emits verifiable launch commands. |
| `variant-interpretation` | `ACMG/AMP 2015`, Bayesian LR | **B** | Combines user-supplied criteria. Disclaims CLIA/CAP diagnostic authorization. |
| `clinical-cohort-analysis`| `lifelines` | **A / C** | Uses Cox PH when lifelines is present; labels event-rate ratios as Grade C when missing. |
| `instrument-data-to-allotrope`| `allotropy` | **A** | Converts raw analytical instrument files to Allotrope Simple Model (ASM) JSON. |

---

## 🌐 MCP Biological Knowledge Layer

BioNexus provides access to 16 biological tools and 9 cloud hosted servers:

- **Local Stdio MCP Server** (`local-bio-mcp`):
  - **Proteins & Functions**: `search_uniprot`, `search_alphafold`, `search_pdb`
  - **Genomics & Constraints**: `search_ensembl`, `search_gnomad`, `search_gtex`, `search_geo`
  - **Pathways & Networks**: `search_reactome`, `search_string`
  - **Literature & Preprints**: `search_pubmed`, `search_pmc`, `search_biorxiv`
  - **Molecules & Targets**: `search_chembl`, `search_opentargets`, `search_clinical_trials`
- **Hosted Cloud MCP Servers**:
  - PubMed Central, bioRxiv/medRxiv, ChEMBL, Open Targets, ClinicalTrials.gov, BioRender, Consensus, Synapse, Wiley.

---

## 🧪 Testing & CI/CD Verification

BioNexus runs a continuous cross-platform matrix across **Linux, Windows, macOS** on **Python 3.10, 3.11, and 3.12**:

```bash
# Run all unit tests
pytest tests/ -v

# Run backend health matrix tests (installed, missing, partial, incompatible, missing weights/binaries)
pytest tests/unit/test_backend_matrix.py -v

# Check manifest synchronization
python scripts/registry_compiler.py --check
```

---

## 📄 License & Compliance

- **License**: Apache 2.0.
- **Regulatory Notice**: BioNexus is for research use only (RUO). Not for use in diagnostic procedures. Not CLIA/CAP certified.
