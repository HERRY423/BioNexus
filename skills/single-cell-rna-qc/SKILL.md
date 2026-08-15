---
name: single-cell-rna-qc
display_name: "Single-Cell RNA-seq Quality Control & Gold Chain"
description: scverse scRNA gold chain on .h5ad/.h5 — inspect, convert, MAD QC, optional scanpy.pp.scrublet, preprocess, Harmony/ComBat, PCA-UMAP-Leiden, Wilcoxon markers, subset, pseudobulk, pydeseq2, stable plots. Use when the user has scRNA-seq counts. Does not assign cell-type labels. rank_genes_groups is not condition DE. Do not call local doublet/ambient helpers SoupX, CellBender, or scDblFinder.
tier: core
grade: gold-wrapper
status: canonical
backend: "scanpy + pydeseq2 (optional)"
---

# Single-Cell RNA-seq Gold Chain (`single-cell-rna-qc`)

> [!NOTE]
> **Gold Reference Plugin**: This skill serves as the canonical reference implementation for all BioNexus analytical tools. All contributors must follow this architecture.

The `single-cell-rna-qc` skill implements the official [scverse](https://scverse.org/) community standard workflow for single-cell RNA sequencing data. It strictly enforces the distinction between **Execution Fidelity** and **Scientific Evidence Quality**, providing multi-dimensional `EvidenceCard` validation, input distribution audits, and reproducible provenance sidecars.

---

## ⚡ Canonical Workflow (Command-Line Interface)

The canonical execution path is the **modular scverse gold chain**:

```bash
# 0. Verify environment backend (scanpy, anndata)
python scripts/doctor.py --require-scverse

# 1. Inspect data semantics, sparsity, library size, and log-transformation
python skills/single-cell-rna-qc/scripts/scrna_inspect.py raw.h5ad

# 2. Run the complete canonical pipeline (MAD QC -> norm/log1p -> HVG -> PCA -> Leiden -> markers)
python skills/single-cell-rna-qc/scripts/scrna_pipeline.py raw.h5ad -o clustered.h5ad

# 3. Official doublet detection on raw count layer (scanpy.pp.scrublet)
python skills/single-cell-rna-qc/scripts/scrna_scrublet.py raw.h5ad -o raw_scrub.h5ad

# 4. Pseudobulk aggregation by biological replicate × condition
python skills/single-cell-rna-qc/scripts/scrna_pseudobulk.py clustered.h5ad -o pb.csv --by sample condition --design pb_design.tsv

# 5. Condition Differential Expression (Wald test via PyDESeq2)
python skills/single-cell-rna-qc/scripts/scrna_deseq.py pb.csv --design pb_design.tsv --condition condition --reference control --contrast-level treated -o de.csv

# 6. Generate standardized exploratory figures
python skills/single-cell-rna-qc/scripts/scrna_plot.py clustered.h5ad -o figures/ --color leiden
```

---

## 🧬 Canonical Scripts & Architecture Matrix

| Step | Script | Canonical Backend | Evidence Grade | Output Artifacts |
| :--- | :--- | :--- | :---: | :--- |
| **Inspect** | `scrna_inspect.py` | `anndata` + `bionexus.integrity` | `A` | JSON summary (sparsity, log-scale check) |
| **Convert** | `scrna_convert.py` | `scanpy.read_*` | `A` | Standardized `.h5ad` |
| **QC (MAD)** | `qc_core.py` | `scanpy` / Median Absolute Deviation | `A` | Filtered `.h5ad` + QC metrics |
| **Doublets** | `scrna_scrublet.py` | **`scanpy.pp.scrublet` only** | `A` | `.h5ad` with doublet scores (Refuse if missing) |
| **Preprocess** | `scrna_preprocess.py` | `scanpy.pp.normalize_total`, `log1p`, `highly_variable_genes` | `A` | Preprocessed `.h5ad` |
| **Integrate** | `scrna_integrate.py` | `harmonypy` / `scanpy.pp.combat` | `A` | Batch-corrected PCA space |
| **Cluster** | `scrna_reduce_cluster.py` | `scanpy.tl.pca`, `neighbors`, `umap`, `leiden` | `A` | Clustered `.h5ad` (Numeric labels only) |
| **Markers** | `scrna_markers.py` | `scanpy.tl.rank_genes_groups` (Wilcoxon) | `A` | Cluster marker gene rankings table |
| **Plot** | `scrna_plot.py` | `scanpy.pl` / `matplotlib` | `A` | `umap_leiden.png`, `dotplot_markers.png`, `violin_qc.png` |
| **Subset** | `scrna_subset.py` | `anndata` slice & stale embedding drop | `A` | Subsampled `.h5ad` |
| **Pseudobulk** | `scrna_pseudobulk.py` | Sum raw counts over replicate groups | `A` | Pseudobulk count matrix `pb.csv` + `pb_design.tsv` |
| **Condition DE** | `scrna_deseq.py` | **`pydeseq2` (Wald test)** | `A` | Differential expression table `de.csv` (Refuse if missing) |

---

## 🛡️ Scientific Honesty Invariants & Non-Negotiables

1. **Numeric Cluster Labels Only**:
   - The pipeline writes numeric cluster identities (`leiden: "0"`, `"1"`, `"2"`).
   - **Strictly Forbidden:** Guessing or hallucinating biological cell-type labels (e.g. "T-cell", "Macrophage") without validated reference annotations or orthogonal experimental ground truth.
2. **Marker Genes vs Condition DE**:
   - Exploratory marker gene identification (`rank_genes_groups`) discovers cluster-specific expression within a single dataset.
   - **Strictly Forbidden:** Publishing exploratory marker p-values as experimental condition treatment effect p-values. Condition DE requires pseudobulk replicate aggregation and `pydeseq2`.
3. **No Masquerading Heuristics**:
   - Local fallback scripts (`ambient_rna.py`, `doublet_detection.py`, `qc_analysis.py`) are legacy Grade C heuristics.
   - **Strictly Forbidden:** Claiming or labeling local heuristics as official community algorithms like SoupX, CellBender, or scDblFinder.
4. **Deterministic Refusal**:
   - If a gold-standard backend (`scanpy`, `pydeseq2`) is missing, the tool must cleanly return `refuse()` with `EvidenceGrade.ABSTAIN`.

---

## 📊 Scientific EvidenceCard Contract

Every analytical run produces a structured `EvidenceCard` evaluating the 7 quality dimensions:

```json
{
  "method": "scanpy_gold_chain",
  "backend": "scanpy",
  "evidence_grade": "A",
  "conclusion_status": "SUPPORTED",
  "evidence_card": {
    "execution_fidelity": "A",
    "input_integrity": "A",
    "assumption_validity": "A",
    "statistical_support": "A",
    "parameter_robustness": "B",
    "cross_method_concordance": "UNTESTED",
    "external_validation": "UNTESTED"
  },
  "limitations": [
    "This plugin does not assign cell-type identity. Leiden/KMeans labels are numeric only.",
    "Research-use only. Not a clinical diagnostic, not CLIA/CAP validated, and not an authorized medical device."
  ]
}
```

---

## ⚠️ Deprecated / Legacy Scripts (Grade C Heuristics)

The following scripts are maintained solely for backward compatibility. They are not part of the default canonical path:
- `qc_analysis.py` (Replaced by `scrna_pipeline.py`)
- `doublet_detection.py` (Replaced by `scrna_scrublet.py`)
- `ambient_rna.py` (Local NNLS heuristic; not SoupX/CellBender)
