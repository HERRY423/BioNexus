# R / Seurat / SingleCellExperiment interop

This plugin does **not** convert `.rds` / `.rdata`. `scrna_convert.py` refuses those paths.

## Seurat or SingleCellExperiment → h5ad (in R)

```r
# Bioconductor
if (!requireNamespace("zellkonverter", quietly = TRUE)) {
  BiocManager::install("zellkonverter")
}
library(zellkonverter)

# SingleCellExperiment
zellkonverter::writeH5AD(sce, "counts.h5ad")

# Seurat → SCE → h5ad
sce <- Seurat::as.SingleCellExperiment(seurat_obj)
zellkonverter::writeH5AD(sce, "counts.h5ad")
```

Keep **raw counts** in `X` or a `counts` layer. Do not write only log-normalized data if you still need scVI or DESeq2.

## After conversion

```bash
python skills/single-cell-rna-qc/scripts/scrna_inspect.py counts.h5ad
python skills/single-cell-rna-qc/scripts/scrna_pipeline.py counts.h5ad -o clustered.h5ad
```

## h5ad → R

```r
sce <- zellkonverter::readH5AD("clustered.h5ad")
```

Alternative: `sceasy` / `SeuratDisk`. Those are R-side tools, not this plugin.
