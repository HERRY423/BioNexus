# BioNexus v2.7.0

[![Agent Plugins 1.0.0](https://img.shields.io/badge/Agent%20Plugins-1.0.0-blue.svg)](https://agent-plugins.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-2024--11--05-orange.svg)](https://modelcontextprotocol.io/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-brightgreen.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

Agent skill pack for biomedical analysis **routing**. It wraps community tools when they are installed and otherwise emits **named heuristics** or **refuses**. It is not a diagnostic laboratory, not a computational-biology platform, and not a replacement for scanpy, squidpy, nf-core, VEP, ESM, or ANARCI.

## Ten-minute path

```bash
pip install -e ".[goldchain]"
python scripts/doctor.py
# Honor ready.scverse_ready. If refuse: stop and install extras.

python skills/single-cell-rna-qc/scripts/scrna_inspect.py raw.h5ad
python skills/single-cell-rna-qc/scripts/scrna_pipeline.py raw.h5ad -o clustered.h5ad
# optional: --config skills/single-cell-rna-qc/configs/gold_chain.example.json
python skills/single-cell-rna-qc/scripts/scrna_plot.py clustered.h5ad -o figures/
python skills/single-cell-rna-qc/scripts/scrna_scrublet.py clustered.h5ad -o clustered.h5ad
```

**Stop here.** You have numeric Leiden/KMeans labels, a markers CSV, `umap_*.png` / `violin_qc.png`, and a provenance sidecar. This plugin does **not** assign cell types. Condition DE: `scrna_pseudobulk.py` then `scrna_deseq.py` (pydeseq2).

Spatial (squidpy):

```bash
pip install -e ".[spatial]"
python skills/spatial-transcriptomics/scripts/spatial_inspect.py visium.h5ad
python skills/spatial-transcriptomics/scripts/spatial_pipeline.py visium.h5ad -o spatial_out.h5ad
```

## Install

```bash
# Windows
.\setup.ps1

# Linux / macOS
chmod +x setup.sh && ./setup.sh

pip install -e ".[dev,goldchain]"
pytest tests/ -v
```

Optional extras:

```bash
pip install -e ".[goldchain]"   # scanpy, leidenalg, harmonypy (no torch)
pip install -e ".[scverse]"     # goldchain + scvi-tools + torch
pip install -e ".[spatial]"     # squidpy + spatialdata
pip install -e ".[survival]"    # lifelines
pip install -e ".[plm]"         # transformers (ESM-2; set BIONEXUS_ALLOW_ESM=1)
pip install -e ".[structure]"   # abnumber, biotite
pip install -e ".[biologics]"   # ViennaRNA Python bindings if available
pip install -e ".[allotrope]"
```

## When not to use a core skill

| Situation | Do not | Do |
|---|---|---|
| Only FASTQs | `scrna_pipeline.py` | `nextflow-development` + `check_environment.py --samplesheet ...` |
| Seurat `.rds` | `scrna_convert.py` | R `zellkonverter` (`skills/single-cell-rna-qc/references/r_interop.md`) |
| Condition DE | `rank_genes_groups` p-values | `scrna_pseudobulk.py` → pydeseq2/DESeq2 |
| Spatial, no coordinates | invent `obsm['spatial']` | refuse |
| “Label these cell types” | this plugin | stop; clusters stay numeric |

Heuristic skills are **not auto-discovered** (`SKILL.legacy.md`). Open them only if the user names that job and accepts grade C.

## Shared kernel

```python
from bio_research.contracts import attach_meta, refuse
from bio_research.backends import probe_all, require
from bio_research.inventory import as_markdown_table
from bio_research.pipeline_config import load_pipeline_config, merge_config
from bio_research.provenance import sidecar
```

Every analysis result should carry `method`, `backend`, `evidence_grade` (`A` gold / `B` simplified real / `C` heuristic / `abstain`), and `limitations`.

## Skills

See `skills/start/SKILL.md` for the grade table. The same table lives in `src/bio_research/inventory.py`.

Honest gold-wrappers: `single-cell-rna-qc`, `spatial-transcriptomics` (squidpy), `scvi-tools`, `nextflow-development`, `instrument-data-to-allotrope`.

## MCP

Hosted servers in `mcp.json` (PubMed, bioRxiv, ChEMBL, Open Targets, ClinicalTrials.gov) are preferred when connected. `local-bio-mcp` is a stdio fallback and the only local path for UniProt, Ensembl, gnomAD, PDB, AlphaFold DB, Reactome, STRING, GEO, and GTEx. `search_cosmic` is **not** the COSMIC API.

## Tests

Unit tests live under `tests/unit/`. Golden / honesty tests check that dangerous defaults are gone (no auto-PM2, no forged CLIA, no random LM22). A green suite means the contracts hold, not that every named gold-standard method ran.

## License

Apache License 2.0.
