# BioNexus Deprecation Policy & Sunset Schedule

This document formalizes the **Deprecation Lifecycle**, **Sunset Timelines**, and **Removal Rules** for skills, capabilities, APIs, and client configurations in BioNexus.

---

## 🏛️ 1. The 3-Phase Deprecation Lifecycle

To prevent unexpected breakage in downstream AI agent workflows and production computational biology pipelines, BioNexus strictly enforces a 3-phase deprecation process:

```text
Phase 1: Announcement & Manifest Flag (Release N)
   │  - Mark `status: deprecated` in `bionexus.registry.yaml` and `SKILL.md`
   │  - Document alternative canonical capability in Migration Guide
   ▼
Phase 2: Runtime Warning & EvidenceCard Advisory (Release N+1 to N+2)
   │  - Function emits Python `FutureWarning` or `DeprecationWarning`
   │  - CLI / Intent Router emits `DEGRADED_ADVISORY` routing status
   │  - EvidenceCard attaches mandatory deprecation limitation note
   ▼
Phase 3: Formal Removal (Release MAJOR.0.0)
      - Feature/Skill code removed from codebase
      - Zero removal occurs within minor or patch releases
```

---

## ⏳ 2. Minimum Deprecation Windows

1. **Python APIs & Core Kernel**: Must remain deprecated for **at least 2 Minor releases** (or 6 months, whichever is longer) before removal in a MAJOR bump.
2. **Canonical Capability Contracts (`scrna.*`, `spatial.*`)**: Must provide backwards-compatible capability aliases for at least 1 Major version cycle if renamed.
3. **CLI Subcommands**: Deprecated CLI flags and subcommands will print deprecation warnings to `stderr` and continue functioning until the next Major release.
4. **Client Manifests**: Compiled manifests maintain backwards schema compatibility for all supported agent formats.

---

## 📋 3. Current Skill Status & Sunset Schedule

| Skill Name | Current Tier | Lifecycle Status | Recommended Canonical Alternative | Scheduled Sunset |
|---|---|---|---|---|
| `single-cell-rna-qc` | `core` | 🟢 Canonical | — | Active |
| `spatial-transcriptomics` | `core` | 🟢 Canonical | — | Active |
| `scvi-tools` | `wrapper` | 🟢 Canonical | — | Active |
| `nextflow-development` | `wrapper` | 🟢 Canonical | — | Active |
| `instrument-data-to-allotrope`| `wrapper` | 🟢 Canonical | — | Active |
| `clinical-cohort-analysis` | `heuristic` | 🟡 Legacy Heuristic | `survival.kaplan_meier` (with `lifelines`) | Retained as Grade C |
| `variant-interpretation` | `heuristic` | 🟡 Legacy Heuristic | `variant.acmg_classification` (with ACMG rules) | Retained as Grade C |
| `biologics-design` | `heuristic` | 🟡 Legacy Heuristic | Dedicated structure & antibody tools | v1.0.0 Evaluation |
| `experiment-design-agent` | `outline` | 🟡 Outline Template | Scientific Intent Router | v1.0.0 Evaluation |
| `research-workflow-orchestrator`| `outline` | 🟡 Outline Template | Native Nextflow workflows | v1.0.0 Evaluation |
