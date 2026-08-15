---
name: start
description: Orient a session on this plugin. Use first. Run scripts/doctor.py, then route only to core gold-chain skills unless the user names a heuristic job. Do not assign cell-type labels. Do not use this skill to run analyses.
---

# BioNexus start

This plugin is an **agent skill pack**. It stops at **numeric clusters + marker tables**. It does not annotate cell types.

## Mandatory first step

```bash
python scripts/doctor.py
```

Honor `tier`, `ready.scverse_ready` / `scvi_ready` / `spatial_ready`, `allowed_next_actions`, and `forbidden_claims`.

Install: `pip install -e .` (kernel). scRNA gold chain: `pip install -e ".[goldchain]"`. Spatial: `pip install -e ".[spatial]"`. Full scVI: `pip install -e ".[scverse]"`.

## Route by tier

| Priority | Tier | Skills | When |
|---|---|---|---|
| 1 | **core** | `single-cell-rna-qc`, `spatial-transcriptomics` (squidpy), `scvi-tools`, `nextflow-development` | Default for real data |
| 2 | wrapper | Allotrope, provenance | Named lab-ops jobs |
| 3 | heuristic (not auto-discovered) | biologics, pLM, ACMG combiner, structure, multiome | Only if user asked **and** accepts grade C |
| 4 | outline | start, problem-selection | Planning only |

Heuristic skills live as `SKILL.legacy.md`. Do **not** open them for a generic “analyze my data” request. To opt in, rename that file back to `SKILL.md`.

## Core scRNA gold chain

```bash
python scripts/doctor.py
python skills/single-cell-rna-qc/scripts/scrna_inspect.py raw.h5ad
python skills/single-cell-rna-qc/scripts/scrna_convert.py 10x_dir/ -o raw.h5ad
python skills/single-cell-rna-qc/scripts/scrna_pipeline.py raw.h5ad -o clustered.h5ad
python skills/single-cell-rna-qc/scripts/scrna_plot.py clustered.h5ad -o figures/
python skills/single-cell-rna-qc/scripts/scrna_scrublet.py raw.h5ad -o raw_scrub.h5ad
python skills/single-cell-rna-qc/scripts/scrna_pseudobulk.py clustered.h5ad -o pb.csv --by sample condition --design pb_design.tsv
python skills/single-cell-rna-qc/scripts/scrna_deseq.py pb.csv --design pb_design.tsv --condition condition --reference control --contrast-level treated -o de.csv
```

## Core spatial gold chain (squidpy)

```bash
python skills/spatial-transcriptomics/scripts/spatial_inspect.py visium.h5ad
python skills/spatial-transcriptomics/scripts/spatial_pipeline.py visium.h5ad -o spatial_out.h5ad
```

Endpoint: clustered `.h5ad` + markers/SVG CSV. Clusters are numbers. Do not invent cell types.

## When **not** to use a core skill

| User has | Do not use | Use instead |
|---|---|---|
| Only FASTQs / need nf-core | `scrna_pipeline.py` | `nextflow-development` |
| Already-clustered object, just plots | full gold chain | `scrna_plot.py` / `spatial_inspect.py` |
| Technical batch that Harmony cannot fix | Harmony-only | `scvi-tools` on **counts** |
| Spatial without coordinates | spatial gold chain | refuse; do not invent `obsm['spatial']` |
| “What cell type is this?” | this plugin | stop; clusters stay numeric |

## MCP

Local server defaults to **unique** tools (UniProt, Ensembl, gnomAD, PDB, AF, Reactome, STRING, GEO, GTEx). Prefer hosted PubMed/ChEMBL/Open Targets/ClinicalTrials/bioRxiv. Set `BIONEXUS_LOCAL_HOSTED_FALLBACKS=1` only if hosted MCP is down.
