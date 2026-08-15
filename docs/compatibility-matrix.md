# BioNexus Ecosystem & Toolchain Compatibility Matrix

This document provides the official compatibility matrix for **BioNexus**, detailing verified integrations with **Host AI Coding Agents**, **Python Runtimes**, **Gold-Standard Bioinformatics Backends**, and **Multi-Platform Manifest Standards**.

---

## 🤖 1. Host AI Coding Agent Compatibility

BioNexus operates as a scientific reliability and capability enforcement layer on top of all major AI coding assistants:

| Host Agent Platform | Integration Method | Verified Status | Key Features Tested |
|---|---|---|---|
| **Codex / OpenAI Agents SDK** | `.codex/config.json` + CLI tools | 🟢 **Verified (Tier 1)** | Capability Contract pre-checks, doctor diagnostics, pseudobulk DE |
| **Claude Code / Desktop** | `.claude-plugin/plugin.json` + HTTP/Stdio MCP | 🟢 **Verified (Tier 1)** | Literature search (PubMed/bioRxiv), Local MCP server, EvidenceCard 2.0 |
| **Cursor / Windsurf** | Native Agent Plugins (`plugin.json` + `mcp.json`) | 🟢 **Verified (Tier 1)** | Skill routing, zero-drift manifest compilation, scverse gold chain |
| **Google Antigravity** | Native Python SDK + Stdio/Lazy MCP Servers | 🟢 **Verified (Tier 1)** | 6-stage Scientific Intent Router, BioNexus Eval harness, W3C PROV-O |

---

## 🐍 2. Python Runtime Compatibility Matrix

BioNexus core kernel and capability contracts are tested continuously across CPython versions:

| Python Version | Core Kernel | Gold-Chain Wrappers | Heuristic Fallbacks | Status | Notes |
|---|---|---|---|---|---|
| **Python 3.10** | 🟢 Compatible | 🟢 Compatible | 🟢 Compatible | Supported | Minimum supported Python runtime |
| **Python 3.11** | 🟢 Compatible | 🟢 Compatible | 🟢 Compatible | Supported | Recommended for production pipelines |
| **Python 3.12** | 🟢 Compatible | 🟢 Compatible | 🟢 Compatible | Supported | Required for latest scanpy 1.12+ features |
| **Python 3.13** | 🟢 Compatible | 🟢 Compatible | 🟢 Compatible | **Primary Active** | Current primary development & CI runtime |

---

## 🧬 3. Canonical Bioinformatics Toolchains & Backend Matrix

BioNexus routes analytical intents exclusively to official community gold standards, with strict version bounds:

| Package | Canonical Role | Supported Versions | Minimum Required | Extras Flag |
|---|---|---|---|---|
| **`scanpy`** | Single-cell preprocessing, PCA, UMAP, Leiden | `1.10.x`, `1.11.x`, `1.12.x` | `>= 1.10.0` | `bionexus[goldchain]` |
| **`anndata`** | Annotated data matrix container (`.h5ad`) | `0.10.x`, `0.11.x` | `>= 0.10.0` | `bionexus[core]` |
| **`squidpy`** | Spatial KNN graph, Moran's I SVGs, spatial plots | `1.3.x`, `1.4.x` | `>= 1.3.0` | `bionexus[spatial]` |
| **`pydeseq2`** | Pseudobulk negative binomial GLM condition DE | `0.4.x`, `0.5.x` | `>= 0.4.0` | `bionexus[deseq]` |
| **`scvi-tools`** | Probabilistic deep generative models (scVI, scANVI) | `1.0.x`, `1.1.x`, `1.2.x` | `>= 1.0.0` | `bionexus[scverse]` |
| **`allotropy`** | Analytical instrument table to ASM JSON | `0.1.30+` | `>= 0.1.30` | `bionexus[allotrope]` |
| **`lifelines`** | Kaplan-Meier survival curves & log-rank tests | `0.27.x`, `0.28.x` | `>= 0.27.0` | `bionexus[survival]` |
| **`scikit-learn`** | ARI, Jaccard similarity, dimensionality metrics | `1.3.x`, `1.4.x`, `1.5.x` | `>= 1.3.0` | `bionexus[core]` |

---

## 📜 4. Client Manifest Schema Compatibility

BioNexus single-source compiler compiles from `bionexus.registry.yaml` to standard client targets:

| Manifest Target | File Location | Schema Specification | Zero-Drift Guaranteed |
|---|---|---|---|
| **Agent Plugins 1.0** | `plugin.json` | `https://agent-plugins.org/schemas/1.0.0/plugin.schema.json` | 🟢 Yes (`bionexus registry --check`) |
| **Agent Plugins MCP** | `mcp.json` | `https://agent-plugins.org/schemas/1.0.0/mcp.schema.json` | 🟢 Yes (`bionexus registry --check`) |
| **Claude Plugin** | `.claude-plugin/plugin.json` | Claude Desktop / Code Specification | 🟢 Yes (`bionexus registry --check`) |
| **OpenAI Codex** | `.codex/config.json` | OpenAI Developer Specification | 🟢 Yes (`bionexus registry --check`) |
