# BioNexus 🧬

[![Agent Plugins 1.0.0](https://img.shields.io/badge/Agent%20Plugins-1.0.0-blue.svg)](https://agent-plugins.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-Standard-orange.svg)](https://modelcontextprotocol.io/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

**BioNexus** is a portable, high-performance Agentic AI Toolkit and Plugin for early-stage life sciences R&D, computational biology, single-cell genomics, nextflow pipelines, and laboratory instrument automation.

Built to conform with the [Agent Plugins Specification (v1.0.0)](https://agent-plugins.org/) and the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/), BioNexus is ready for out-of-the-box operation across **Antigravity**, **Cursor**, **Codex (ChatGPT)**, **VS Code**, **GitHub Copilot**, and **Claude Code**.

---

## 🌟 Key Highlights

- ⚡ **High-Throughput Parallel Batch Processing**: Multi-process batch parser for plate readers, spectrophotometers, and qPCR instruments with automated summary metrics.
- 🔬 **Scalable Single-Cell Omics (100k - 1M+ Cells)**: Vectorized sparse matrix calculations, disk-backed streaming (`--backed r`), and chunked QC metrics.
- 🤖 **Deep Learning Acceleration**: Mixed-precision training (FP16 / BF16 AMP) and multi-worker DataLoader support for `scVI` and `scANVI`.
- 🔌 **Local Fallback Stdio MCP Server**: Zero-proxy Python stdio MCP server for PubMed, bioRxiv, ChEMBL, Open Targets, and ClinicalTrials.gov.
- 🛠️ **Hardware-Aware One-Click Installer**: Auto-detects NVIDIA CUDA, Apple Silicon MPS, or CPU to configure dependencies.

---

## ⚡ Quick Start: One-Click Environment Setup

We provide cross-platform automated setup scripts that detect your operating system, CPU architecture, and GPU hardware:

### Windows
```powershell
# PowerShell
.\setup.ps1

# Or Command Prompt (CMD)
setup.bat
```

### Linux / macOS
```bash
chmod +x setup.sh
./setup.sh
```

### Python CLI (Advanced / Diagnostic Mode)
```bash
# Check hardware acceleration and bioinformatics toolchain without installing
python scripts/setup_env.py --check-only

# Force CPU-only or CUDA build
python scripts/setup_env.py --cpu
python scripts/setup_env.py --cuda
```

---

## 🚀 Client Setup & Integration

### 1. Google Antigravity
- **Global**: Place or clone in `~/.gemini/config/plugins/bio-research/`.
- **Project**: Place in `.agents/plugins/bio-research/`.

### 2. Cursor
- **Skills**: Add plugin path under `Settings > Features > Skills`.
- **MCP**: Import `mcp.json` under `Settings > Features > MCP`.

### 3. OpenAI Codex / ChatGPT
- Discovers `skills/*/SKILL.md` and reads `plugin.json` automatically.

### 4. VS Code / GitHub Copilot
- VS Code detects `plugin.json` and loads `mcp.json` via MCP extensions.

### 5. Claude Code
- Backward-compatible with `.claude-plugin/plugin.json` and `.mcp.json`.

---

## 🧩 Included Skills & Capabilities

| Skill Name | Description | Key Features |
|---|---|---|
| **`single-cell-rna-qc`** | High-performance single-cell RNA-seq quality control | MAD filtering, sparse CSR vectorization, disk-backed chunked QC |
| **`scvi-tools`** | Deep learning for single-cell data integration | scVI, scANVI, TotalVI, mixed precision (FP16/BF16), DataLoader workers |
| **`instrument-data-to-allotrope`** | Lab instrument file standardization to Allotrope ASM | Multi-core parallel batch processing, 20+ instrument formats, 2D CSV flattening |
| **`nextflow-development`** | nf-core pipeline management & multi-threaded SRA fetch | RNA-seq, Sarek, ATAC-seq sample sheets, parallel FASTQ downloads |
| **`scientific-problem-selection`** | Research project ideation & strategic guidance | Frameworks for evaluating scientific feasibility, tractability, and novelty |
| **`start`** | Plugin orientation & environment verification | Diagnostic checks for MCP servers, Python toolchains, and active skills |

---

## 📡 MCP Server Configuration & Authentication

BioNexus supports both a **local stdio fallback server** and **10 remote cloud MCP servers**:

- **Local Fallback**: `scripts/local_mcp_server.py` provides offline/direct access to NCBI PubMed, bioRxiv, ChEMBL, Open Targets, and ClinicalTrials.gov.
- **API Credentials & LIMS**: Copy `.env.example` to `.env` to configure private API keys (Benchling, Synapse, Wiley, etc.).
- Run diagnostic checks anytime:
  ```bash
  python scripts/auth_helper.py --status
  ```

---

## 📁 Repository Structure

```text
BioNexus/
├── plugin.json                 # Agent Plugins 1.0.0 Root Manifest
├── mcp.json                    # Standard MCP Server Declarations (Stdio + Streamable-HTTP)
├── pyproject.toml              # Modern Python packaging & optional dependency groups
├── environment.yml             # Conda / Mamba Environment Specification
├── requirements.txt            # Pinned requirements for pip/uv
├── setup.bat / setup.ps1       # One-click Windows installer
├── setup.sh                    # One-click Linux/macOS installer
├── .env.example                # API authentication template
├── scripts/
│   ├── local_mcp_server.py     # Pure-Python Stdio MCP Server
│   ├── auth_helper.py          # API authentication checker
│   └── setup_env.py            # Hardware-aware environment initializer
├── skills/                     # Standard Agent Skill packages
│   ├── single-cell-rna-qc/
│   ├── scvi-tools/
│   ├── instrument-data-to-allotrope/
│   ├── nextflow-development/
│   ├── scientific-problem-selection/
│   └── start/
├── CONNECTORS.md               # Connector guide & private API integration
├── README.md                   # Project overview & quick start
└── LICENSE                     # Apache-2.0
```

---

## 📄 License

This project is licensed under the [Apache License 2.0](LICENSE).
