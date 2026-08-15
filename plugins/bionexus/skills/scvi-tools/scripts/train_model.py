#!/usr/bin/env python3
"""
Train scvi-tools models.

Thin CLI wrapper around model_utils.py.  All training logic lives in
model_utils.py (the canonical implementation).  This script only handles
argument parsing and dispatch — no duplicated model code.

Supports scVI, scANVI, totalVI, PeakVI, veloVI, and MultiVI.
Input should be prepared with prepare_data.py or equivalent.

Usage:
    python train_model.py input.h5ad output_dir/ --model scvi --batch-key batch
    python train_model.py input.h5ad output_dir/ --model scanvi --batch-key batch --labels-key cell_type
"""

import argparse
import os
import sys

# Import canonical implementations from model_utils (single source of truth)
from model_utils import (
    train_scvi,
)

MODELS = ["scvi", "scanvi", "totalvi", "peakvi", "velovi", "multivi"]


def train_totalvi(adata, batch_key=None, protein_key="protein_expression", n_latent=20, max_epochs=200):
    """Train totalVI model for CITE-seq data."""
    import numpy as np
    import scvi

    scvi.model.TOTALVI.setup_anndata(
        adata,
        layer="counts",
        batch_key=batch_key,
        protein_expression_obsm_key=protein_key,
    )
    model = scvi.model.TOTALVI(adata, n_latent=n_latent)
    model.train(max_epochs=max_epochs, early_stopping=True)
    adata.obsm["X_totalVI"] = model.get_latent_representation()

    _, protein_denoised = model.get_normalized_expression(return_mean=True)
    adata.obsm["protein_denoised"] = (
        protein_denoised.values if hasattr(protein_denoised, "values") else np.array(protein_denoised)
    )
    return model, "X_totalVI"


def train_peakvi(adata, batch_key=None, n_latent=20, max_epochs=200):
    """Train PeakVI model for scATAC-seq data."""
    import numpy as np
    import scvi

    if adata.X.max() > 1:
        print("Binarizing ATAC data...")
        adata.X = (adata.X > 0).astype(np.float32)

    scvi.model.PEAKVI.setup_anndata(adata, batch_key=batch_key)
    model = scvi.model.PEAKVI(adata, n_latent=n_latent)
    model.train(max_epochs=max_epochs, early_stopping=True)
    adata.obsm["X_PeakVI"] = model.get_latent_representation()
    return model, "X_PeakVI"


def train_velovi(adata, max_epochs=500):
    """Train veloVI model for RNA velocity.

    If Ms/Mu layers are missing, runs scvelo preprocessing automatically.
    """
    import scvelo as scv
    import scvi

    if "Ms" not in adata.layers or "Mu" not in adata.layers:
        print("Preprocessing data for veloVI (scvelo moments)...")
        scv.pp.filter_and_normalize(adata, min_shared_counts=30, n_top_genes=2000)
        scv.pp.moments(adata, n_pcs=30, n_neighbors=30)
        print(f"After preprocessing: {adata.shape}")

    scvi.external.VELOVI.setup_anndata(adata, spliced_layer="Ms", unspliced_layer="Mu")
    model = scvi.external.VELOVI(adata)
    model.train(max_epochs=max_epochs, early_stopping=True)

    adata.obsm["X_veloVI"] = model.get_latent_representation()
    adata.layers["velocity"] = model.get_velocity()

    latent_time_df = model.get_latent_time()
    adata.obs["latent_time_mean"] = latent_time_df.mean(axis=1).values
    return model, "X_veloVI"


def train_multivi(adata, batch_key=None, n_latent=20, max_epochs=300):
    """Train MultiVI model for multiome (RNA + ATAC) data."""
    import scvi

    try:
        import mudata as md
    except ImportError:
        raise ImportError("MultiVI requires mudata. Install: pip install mudata")

    if isinstance(adata, md.MuData):
        scvi.model.MULTIVI.setup_mudata(
            adata,
            rna_layer="counts",
            atac_layer="counts",
            batch_key=batch_key,
            modalities={"rna_layer": "rna", "batch_key": "rna", "atac_layer": "atac"},
        )
    else:
        raise ValueError("MultiVI requires MuData format with 'rna' and 'atac' modalities")

    model = scvi.model.MULTIVI(adata, n_latent=n_latent)
    model.train(max_epochs=max_epochs, early_stopping=True)
    adata.obsm["X_MultiVI"] = model.get_latent_representation()
    return model, "X_MultiVI"


def main():
    parser = argparse.ArgumentParser(
        description="Train scvi-tools models (uses model_utils.py for core logic)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python train_model.py prepared.h5ad results/ --model scvi --batch-key batch
    python train_model.py prepared.h5ad results/ --model scanvi --batch-key batch --labels-key cell_type
    python train_model.py citeseq.h5ad results/ --model totalvi --batch-key batch
    python train_model.py atac.h5ad results/ --model peakvi
    python train_model.py velocity.h5ad results/ --model velovi
    python train_model.py multiome.h5mu results/ --model multivi --batch-key batch
        """,
    )
    parser.add_argument("input", help="Input h5ad file (prepared)")
    parser.add_argument("output_dir", help="Output directory for model and results")
    parser.add_argument("--model", choices=MODELS, default="scvi", help="Model type (default: scvi)")
    parser.add_argument("--batch-key", help="Batch column in obs")
    parser.add_argument("--labels-key", help="Labels column (required for scanvi)")
    parser.add_argument("--protein-key", default="protein_expression", help="Protein obsm key for totalvi")
    parser.add_argument("--n-latent", type=int, default=30, help="Latent dimensions (default: 30)")
    parser.add_argument("--n-layers", type=int, default=2, help="Encoder/decoder layers (default: 2)")
    parser.add_argument("--max-epochs", type=int, default=200, help="Max training epochs (default: 200)")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Mini-batch size (default: auto, 128 for <50k cells, 512 for 100k+ cells)",
    )
    parser.add_argument(
        "--precision",
        choices=["16-mixed", "bf16-mixed", "32"],
        default=None,
        help="PyTorch Lightning mixed precision mode (16-mixed or bf16-mixed for GPU/MPS acceleration)",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=0,
        help="Number of DataLoader worker processes for multi-threaded data loading (default: 0)",
    )
    parser.add_argument("--patience", type=int, default=15, help="Early stopping patience epochs (default: 15)")

    args = parser.parse_args()

    if args.model == "scanvi" and args.labels_key is None:
        print("Error: --labels-key required for scanvi model")
        sys.exit(1)

    try:
        import scanpy as sc
        import scvi  # noqa: F401
    except ImportError:
        print("Error: scvi-tools and scanpy required. Install: pip install scvi-tools scanpy")
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    # ---- Load data -------------------------------------------------------
    print(f"Loading {args.input}...")
    if args.input.endswith(".h5mu") or args.model == "multivi":
        try:
            import mudata as md

            adata = md.read(args.input)
            print(f"MuData: {adata.n_obs} cells")
            for mod_name, mod in adata.mod.items():
                print(f"  {mod_name}: {mod.shape}")
        except ImportError:
            print("Error: mudata required. Install: pip install mudata")
            sys.exit(1)
    else:
        adata = sc.read_h5ad(args.input)
        print(f"Data: {adata.shape}")

    if "counts" not in adata.layers:
        print("Warning: 'counts' layer not found, using .X")
        adata.layers["counts"] = adata.X.copy()

    # ---- Train -----------------------------------------------------------
    print(
        f"\nTraining {args.model.upper()} (Acceleration: precision={args.precision or '32'}, batch_size={args.batch_size or 'auto'}, workers={args.num_workers})..."
    )

    if args.model in ("scvi", "scanvi"):
        model, rep_key = train_scvi(
            adata,
            batch_key=args.batch_key,
            labels_key=args.labels_key,
            n_latent=args.n_latent,
            n_layers=args.n_layers,
            max_epochs=args.max_epochs,
            batch_size=args.batch_size,
            precision=args.precision,
            num_workers=args.num_workers,
            early_stopping_patience=args.patience,
        )
    elif args.model == "totalvi":
        model, rep_key = train_totalvi(
            adata,
            args.batch_key,
            args.protein_key,
            args.n_latent,
            args.max_epochs,
        )
    elif args.model == "peakvi":
        model, rep_key = train_peakvi(
            adata,
            args.batch_key,
            args.n_latent,
            args.max_epochs,
        )
    elif args.model == "velovi":
        model, rep_key = train_velovi(adata, args.max_epochs)
    elif args.model == "multivi":
        model, rep_key = train_multivi(
            adata,
            args.batch_key,
            args.n_latent,
            args.max_epochs,
        )

    print("Training complete!")

    # ---- Save ------------------------------------------------------------
    model_path = os.path.join(args.output_dir, "model")
    model.save(model_path)
    print(f"Model saved to {model_path}")

    adata_path = os.path.join(args.output_dir, "adata_trained.h5ad")
    adata.write_h5ad(adata_path)
    print(f"AnnData saved to {adata_path}")

    # Training history plot
    try:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 4))
        if "elbo_train" in model.history:
            ax.plot(model.history["elbo_train"], label="Train")
        if "elbo_validation" in model.history:
            ax.plot(model.history["elbo_validation"], label="Validation")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("ELBO")
        ax.legend()
        ax.set_title(f"{args.model.upper()} Training History")
        plot_path = os.path.join(args.output_dir, "training_history.png")
        plt.savefig(plot_path, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"Training plot saved to {plot_path}")
    except Exception as e:
        print(f"Could not save training plot: {e}")

    print("\nDone! Next steps:")
    print(f"  - Run clustering: python cluster_embed.py {adata_path} {args.output_dir}")
    print(f"  - Load model: scvi.model.{args.model.upper()}.load('{model_path}')")


if __name__ == "__main__":
    main()
