---
name: single-cell-rna-qc
description: scverse scRNA gold chain on .h5ad/.h5 — inspect, convert, MAD QC, optional scanpy.pp.scrublet, preprocess, Harmony/ComBat, PCA-UMAP-Leiden, Wilcoxon markers, subset, pseudobulk, pydeseq2, stable plots. Use when the user has scRNA-seq counts. Does not assign cell-type labels. rank_genes_groups is not condition DE. Do not call local doublet/ambient helpers SoupX, CellBender, or scDblFinder.
---

# Single-Cell RNA-seq gold chain

Default path is the **full exploratory chain**, not `qc_analysis.py`.

```bash
python scripts/doctor.py   # need scanpy + anndata
python skills/single-cell-rna-qc/scripts/scrna_inspect.py raw.h5ad
python skills/single-cell-rna-qc/scripts/scrna_pipeline.py raw.h5ad -o clustered.h5ad
# official doublets on raw counts (before or instead of log1p pipeline):
python skills/single-cell-rna-qc/scripts/scrna_scrublet.py raw.h5ad -o raw_scrub.h5ad
# condition DE: aggregate by biological sample × condition, then pydeseq2
python skills/single-cell-rna-qc/scripts/scrna_pseudobulk.py clustered.h5ad -o pb.csv --by sample condition --design pb_design.tsv
python skills/single-cell-rna-qc/scripts/scrna_deseq.py pb.csv --design pb_design.tsv --condition condition --reference control --contrast-level treated -o de.csv
```

Writes numeric `leiden`/`cluster` labels only. Seurat `.rds` is refused — see `references/r_interop.md`.

| Step | Script | Backend |
|---|---|---|
| inspect | `scrna_inspect.py` | AnnData summary, log-like X, library size |
| convert | `scrna_convert.py` | 10x dir/.h5/.csv → h5ad |
| QC | `qc_core.py` (MAD) | scanpy/local |
| doublets | `scrna_scrublet.py` | **`scanpy.pp.scrublet` only** — refuse if missing |
| preprocess | `scrna_preprocess.py` | normalize_total + log1p + HVG |
| integrate | `scrna_integrate.py` | Harmony or ComBat |
| reduce/cluster | `scrna_reduce_cluster.py` | PCA + UMAP + Leiden |
| markers | `scrna_markers.py` | Wilcoxon (exploratory) |
| plot | `scrna_plot.py` | `umap_{color}.png`, `dotplot_markers.png`, `violin_qc.png` |
| subset | `scrna_subset.py` | Filter; drop stale embeddings |
| pseudobulk | `scrna_pseudobulk.py` | Sum counts + design.tsv |
| DE | `scrna_deseq.py` | **pydeseq2** — refuse if missing |

**Forbidden:** inventing cell types; publishing marker p-values as condition DE; calling local ambient/doublet helpers SoupX / CellBender / scDblFinder.

## Non-default (grade C — only if the user names them)

`qc_analysis.py`, `doublet_detection.py`, and `ambient_rna.py` are **local heuristics**. They are not SoupX, not CellBender, not scDblFinder. Prefer `scrna_pipeline.py` + `scrna_scrublet.py`.
