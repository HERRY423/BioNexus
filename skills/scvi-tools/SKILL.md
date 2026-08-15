---
name: scvi-tools
description: Train official scvi-tools models (scVI/scANVI/totalVI/PeakVI/MultiVI/veloVI) on raw counts after the scRNA gold chain. Use for probabilistic batch integration or those named models. Does not run DestVI/Cell2location. Do not log-normalize before setup_anndata.
---

# scvi-tools Deep Learning Skill

Train official scvi-tools models. Use **after** the scRNA gold chain (or on raw counts). Do not log-normalize before `setup_anndata`.

Pins and pitfalls live in `bio_research.versions` (`scvi-tools` 1.1+, train on counts only).

## When to Use This Skill

- When scvi-tools, scVI, scANVI, or related deep generative models are mentioned
- When deep learning-based batch correction or multi-study integration is needed
- When automated hyperparameter tuning is required for latent dimensions, layer depths, or learning rates
- When working with multi-modal data (CITE-seq, multiome)
- When reference mapping or label transfer is required
- When analyzing ATAC-seq or spatial transcriptomics data

---

## CLI Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `prepare_data.py` | QC, filter, HVG selection | `python scripts/prepare_data.py raw.h5ad prepared.h5ad --batch-key batch` |
| `hyperparam_search.py` | Automated hyperparameter optimization | `python scripts/hyperparam_search.py prepared.h5ad results/ --model scvi --n-trials 20 --batch-key batch` |
| `train_model.py` | Train any scvi-tools model | `python scripts/train_model.py prepared.h5ad results/ --model scvi --batch-key batch` |
| `cluster_embed.py` | Neighbors, UMAP, Leiden | `python scripts/cluster_embed.py adata.h5ad results/` |
| `differential_expression.py` | Probabilistic DE analysis | `python scripts/differential_expression.py model/ adata.h5ad de.csv --groupby leiden` |
| `transfer_labels.py` | Label transfer with scANVI | `python scripts/transfer_labels.py ref_model/ query.h5ad results/` |
| `integrate_datasets.py` | Multi-dataset integration | `python scripts/integrate_datasets.py results/ data1.h5ad data2.h5ad` |
| `validate_adata.py` | Check data compatibility | `python scripts/validate_adata.py data.h5ad --batch-key batch` |
| `scvi_smoke.py` | 1-epoch scVI on `layers['counts']` | `python scripts/scvi_smoke.py prepared.h5ad -o smoke.h5ad` |

---

## Automated Hyperparameter Search (`scripts/hyperparam_search.py`)

Tune latent dimensions (`n_latent`), network depth (`n_layers`), hidden layer width (`n_hidden`), gene likelihood (`nb` vs `zinb`), and learning rates:

```bash
# Bayesian hyperparameter optimization with Optuna
python scripts/hyperparam_search.py prepared.h5ad tuning_results/ \
    --model scvi \
    --batch-key batch \
    --n-trials 20 \
    --epochs-per-trial 35 \
    --retrain-best
```

Outputs include:
- `hyperparam_tuning_summary.json`: Detailed trial records and best hyperparameter configuration
- `optimal_model/`: Saved scvi model trained with the best parameter combination
- `adata_optimal.h5ad`: AnnData annotated with optimal latent representations
