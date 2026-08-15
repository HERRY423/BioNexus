#!/usr/bin/env python3
"""
Automated Hyperparameter Optimization for scvi-tools.
Optimizes latent dimensions, layer depth, learning rate, and gene likelihood
using Optuna (or built-in fallback Bayesian / Random search).

Usage:
    python hyperparam_search.py prepared.h5ad output_dir/ --model scvi --n-trials 20 --batch-key batch
    python hyperparam_search.py prepared.h5ad output_dir/ --model scanvi --batch-key batch --labels-key cell_type --n-trials 15
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional, Tuple

import numpy as np

# Ensure scripts directory is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def evaluate_trial_model(
    adata, model, rep_key: str, batch_key: Optional[str] = None, labels_key: Optional[str] = None
) -> Dict[str, float]:
    """Calculate validation metrics for a trained trial model."""
    metrics: Dict[str, float] = {}

    # Validation ELBO
    if hasattr(model, "history") and "elbo_validation" in model.history:
        elbo_series = model.history["elbo_validation"]
        if hasattr(elbo_series, "values"):
            metrics["val_elbo"] = float(elbo_series.values[-1])
        else:
            metrics["val_elbo"] = float(elbo_series[-1])
    else:
        metrics["val_elbo"] = 0.0

    # Latent space metrics (Silhouette score)
    try:
        from sklearn.metrics import silhouette_score

        latent = model.get_latent_representation()
        sample_size = min(2000, adata.n_obs)
        sub_indices = np.random.choice(adata.n_obs, size=sample_size, replace=False)
        sub_latent = latent[sub_indices]

        if labels_key and labels_key in adata.obs:
            sub_labels = adata.obs[labels_key].values[sub_indices]
            if len(np.unique(sub_labels)) > 1:
                metrics["asw_cell_type"] = float(silhouette_score(sub_latent, sub_labels))

        if batch_key and batch_key in adata.obs:
            sub_batches = adata.obs[batch_key].values[sub_indices]
            if len(np.unique(sub_batches)) > 1:
                # Lower batch silhouette is better (less batch separation = better integration)
                raw_batch_asw = float(silhouette_score(sub_latent, sub_batches))
                metrics["batch_mixing_score"] = float(1.0 - abs(raw_batch_asw))
    except Exception:
        pass

    return metrics


def run_optuna_search(
    adata,
    model_type: str,
    output_dir: str,
    n_trials: int = 15,
    max_epochs_per_trial: int = 40,
    batch_key: Optional[str] = None,
    labels_key: Optional[str] = None,
    study_name: str = "scvi_tuning",
) -> Tuple[Dict[str, Any], Any]:
    """Execute Bayesian hyperparameter search using Optuna."""
    try:
        import optuna

        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        print("Optuna not installed. Running native grid/random search fallback.")
        return run_fallback_search(adata, model_type, output_dir, n_trials, max_epochs_per_trial, batch_key, labels_key)

    import scvi

    trial_records = []

    def objective(trial: optuna.Trial) -> float:
        # Search space suggestions
        n_latent = trial.suggest_int("n_latent", 10, 50, step=5)
        n_layers = trial.suggest_int("n_layers", 1, 3)
        n_hidden = trial.suggest_categorical("n_hidden", [128, 256])
        dropout_rate = trial.suggest_float("dropout_rate", 0.05, 0.25, step=0.05)
        gene_likelihood = trial.suggest_categorical("gene_likelihood", ["nb", "zinb"])
        lr = trial.suggest_float("lr", 1e-4, 5e-3, log=True)

        print(
            f"\n[Trial {trial.number + 1}/{n_trials}] Config: n_latent={n_latent}, n_layers={n_layers}, "
            f"n_hidden={n_hidden}, likelihood={gene_likelihood}, lr={lr:.5f}"
        )

        # Setup AnnData
        if model_type == "scanvi":
            scvi.model.SCANVI.setup_anndata(
                adata,
                layer="counts" if "counts" in adata.layers else None,
                batch_key=batch_key,
                labels_key=labels_key,
                unlabeled_category="Unknown",
            )
            model = scvi.model.SCANVI(
                adata,
                n_latent=n_latent,
                n_layers=n_layers,
                n_hidden=n_hidden,
                dropout_rate=dropout_rate,
                gene_likelihood=gene_likelihood,
            )
        else:
            scvi.model.SCVI.setup_anndata(
                adata, layer="counts" if "counts" in adata.layers else None, batch_key=batch_key
            )
            model = scvi.model.SCVI(
                adata,
                n_latent=n_latent,
                n_layers=n_layers,
                n_hidden=n_hidden,
                dropout_rate=dropout_rate,
                gene_likelihood=gene_likelihood,
            )

        # Train model with early stopping
        model.train(
            max_epochs=max_epochs_per_trial, plan_kwargs={"lr": lr}, early_stopping=True, early_stopping_patience=10
        )

        metrics = evaluate_trial_model(adata, model, "X_scVI", batch_key, labels_key)
        val_elbo = metrics.get("val_elbo", 1e8)

        record = {"trial_id": trial.number, "params": trial.params, "val_elbo": val_elbo, "metrics": metrics}
        trial_records.append(record)

        print(f"  -> Validation ELBO: {val_elbo:.2f}")
        return val_elbo

    study = optuna.create_study(direction="minimize", study_name=study_name)
    study.optimize(objective, n_trials=n_trials)

    best_params = study.best_params
    best_value = study.best_value

    print("\n" + "=" * 65)
    print(" Hyperparameter Search Completed!")
    print(f" Best Validation ELBO: {best_value:.4f}")
    print(" Best Parameters:")
    for k, v in best_params.items():
        print(f"   {k}: {v}")
    print("=" * 65)

    # Save summary
    summary_file = os.path.join(output_dir, "hyperparam_tuning_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({"best_params": best_params, "best_val_elbo": best_value, "trials": trial_records}, f, indent=2)
    print(f"Tuning summary saved to: {summary_file}")

    return best_params, trial_records


def run_fallback_search(
    adata,
    model_type: str,
    output_dir: str,
    n_trials: int = 5,
    max_epochs_per_trial: int = 30,
    batch_key: Optional[str] = None,
    labels_key: Optional[str] = None,
) -> Tuple[Dict[str, Any], Any]:
    """Deterministic grid/random search fallback when Optuna is not available."""
    import scvi

    candidate_params = [
        {"n_latent": 20, "n_layers": 1, "n_hidden": 128, "gene_likelihood": "nb", "lr": 1e-3},
        {"n_latent": 30, "n_layers": 2, "n_hidden": 128, "gene_likelihood": "nb", "lr": 1e-3},
        {"n_latent": 30, "n_layers": 2, "n_hidden": 256, "gene_likelihood": "zinb", "lr": 1e-3},
        {"n_latent": 40, "n_layers": 2, "n_hidden": 256, "gene_likelihood": "nb", "lr": 5e-4},
        {"n_latent": 50, "n_layers": 3, "n_hidden": 256, "gene_likelihood": "zinb", "lr": 5e-4},
    ][:n_trials]

    trial_records = []
    best_elbo = float("inf")
    best_params = candidate_params[0]

    for idx, params in enumerate(candidate_params):
        print(f"\n[Trial {idx + 1}/{len(candidate_params)}] Running params: {params}")
        scvi.model.SCVI.setup_anndata(adata, layer="counts" if "counts" in adata.layers else None, batch_key=batch_key)
        model = scvi.model.SCVI(
            adata,
            n_latent=params["n_latent"],
            n_layers=params["n_layers"],
            n_hidden=params["n_hidden"],
            gene_likelihood=params["gene_likelihood"],
        )
        model.train(max_epochs=max_epochs_per_trial, plan_kwargs={"lr": params["lr"]}, early_stopping=True)
        metrics = evaluate_trial_model(adata, model, "X_scVI", batch_key, labels_key)
        elbo = metrics.get("val_elbo", 1e8)

        record = {"trial_id": idx, "params": params, "val_elbo": elbo, "metrics": metrics}
        trial_records.append(record)
        print(f"  -> Validation ELBO: {elbo:.2f}")

        if elbo < best_elbo:
            best_elbo = elbo
            best_params = params

    summary_file = os.path.join(output_dir, "hyperparam_tuning_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({"best_params": best_params, "best_val_elbo": best_elbo, "trials": trial_records}, f, indent=2)

    return best_params, trial_records


def main():
    parser = argparse.ArgumentParser(
        description="Automated Hyperparameter Optimization for scvi-tools models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python hyperparam_search.py prepared.h5ad results/ --model scvi --n-trials 15 --batch-key batch
    python hyperparam_search.py prepared.h5ad results/ --model scanvi --batch-key batch --labels-key cell_type
        """,
    )
    parser.add_argument("input", help="Input preprocessed .h5ad dataset")
    parser.add_argument("output_dir", help="Output directory for tuning summary and optimal model")
    parser.add_argument(
        "--model", choices=["scvi", "scanvi"], default="scvi", help="Model type to optimize (default: scvi)"
    )
    parser.add_argument("--n-trials", type=int, default=15, help="Number of search trials (default: 15)")
    parser.add_argument("--epochs-per-trial", type=int, default=35, help="Max training epochs per trial (default: 35)")
    parser.add_argument("--batch-key", help="Batch column name in adata.obs")
    parser.add_argument("--labels-key", help="Cell type labels column name in adata.obs (for scANVI)")
    parser.add_argument(
        "--retrain-best", action="store_true", default=True, help="Retrain full model with optimal hyperparameters"
    )
    parser.add_argument("--full-epochs", type=int, default=200, help="Epochs for final retraining (default: 200)")

    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    try:
        import scanpy as sc
        import scvi
    except ImportError:
        print("Error: scanpy and scvi-tools required. Install: pip install scanpy scvi-tools")
        sys.exit(1)

    print(f"Loading dataset from: {args.input}...")
    adata = sc.read_h5ad(args.input)
    print(f"Loaded AnnData: {adata.n_obs} cells x {adata.n_vars} genes")

    best_params, _ = run_optuna_search(
        adata=adata,
        model_type=args.model,
        output_dir=args.output_dir,
        n_trials=args.n_trials,
        max_epochs_per_trial=args.epochs_per_trial,
        batch_key=args.batch_key,
        labels_key=args.labels_key,
    )

    if args.retrain_best:
        print(f"\nRetraining optimal {args.model.upper()} model for {args.full_epochs} epochs with best parameters...")
        if args.model == "scanvi":
            scvi.model.SCANVI.setup_anndata(
                adata,
                layer="counts" if "counts" in adata.layers else None,
                batch_key=args.batch_key,
                labels_key=args.labels_key,
            )
            final_model = scvi.model.SCANVI(
                adata,
                n_latent=best_params.get("n_latent", 30),
                n_layers=best_params.get("n_layers", 2),
                n_hidden=best_params.get("n_hidden", 128),
                gene_likelihood=best_params.get("gene_likelihood", "nb"),
            )
        else:
            scvi.model.SCVI.setup_anndata(
                adata, layer="counts" if "counts" in adata.layers else None, batch_key=args.batch_key
            )
            final_model = scvi.model.SCVI(
                adata,
                n_latent=best_params.get("n_latent", 30),
                n_layers=best_params.get("n_layers", 2),
                n_hidden=best_params.get("n_hidden", 128),
                gene_likelihood=best_params.get("gene_likelihood", "nb"),
            )

        final_model.train(max_epochs=args.full_epochs, early_stopping=True)

        optimal_model_dir = os.path.join(args.output_dir, "optimal_model")
        final_model.save(optimal_model_dir)
        print(f"Optimal model saved to: {optimal_model_dir}")

        adata.obsm[f"X_{args.model}"] = final_model.get_latent_representation()
        out_adata_path = os.path.join(args.output_dir, "adata_optimal.h5ad")
        adata.write_h5ad(out_adata_path)
        print(f"Optimized AnnData saved to: {out_adata_path}")


if __name__ == "__main__":
    main()
