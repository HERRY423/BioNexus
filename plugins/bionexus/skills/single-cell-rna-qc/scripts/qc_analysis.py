#!/usr/bin/env python3
"""
Quality Control Analysis for Single-Cell RNA-seq Data
High-Performance & Scalable Edition (Supporting 100k - 1M+ Cells)
Comprehensive Pipeline: MAD-filtering, Doublet Detection, and Ambient RNA Correction.

Following scverse & Bioconductor best practices:
https://www.sc-best-practices.org/preprocessing_visualization/quality_control.html
"""

import argparse
import os
import sys
import time

import anndata as ad
import numpy as np
import scanpy as sc
from ambient_rna import correct_ambient_rna
from doublet_detection import run_doublet_detection

# Import our modular utilities
from qc_core import (
    apply_hard_threshold,
    calculate_qc_metrics,
    calculate_qc_metrics_chunked,
    detect_outliers_mad,
    filter_cells,
    filter_genes,
    print_qc_summary,
)
from qc_plotting import plot_filtering_thresholds, plot_qc_after_filtering, plot_qc_distributions

print("=" * 80)
print("Single-Cell RNA-seq Quality Control Analysis (High-Performance Engine v1.3.0)")
print("=" * 80)

# Default parameters
DEFAULT_MAD_COUNTS = 5
DEFAULT_MAD_GENES = 5
DEFAULT_MAD_MT = 3
DEFAULT_MT_THRESHOLD = 8
DEFAULT_MIN_CELLS = 20
DEFAULT_MT_PATTERN = "mt-,MT-"
DEFAULT_RIBO_PATTERN = "Rpl,Rps,RPL,RPS"
DEFAULT_HB_PATTERN = "^Hb[^(p)]|^HB[^(P)]"

# Parse command-line arguments
parser = argparse.ArgumentParser(
    description="Comprehensive QC Analysis for Single-Cell RNA-seq Data (scverse best practices)",
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Examples:
  python3 qc_analysis.py data.h5ad
  python3 qc_analysis.py raw_feature_bc_matrix.h5 --run-doublets --run-ambient
  python3 qc_analysis.py data.h5ad --backed r --chunk-size 50000
  python3 qc_analysis.py data.h5ad --mad-counts 4 --mad-genes 4 --mad-mt 2.5 --run-doublets
    """,
)

parser.add_argument("input_file", help="Input .h5ad or .h5 file (10X Genomics format)")
parser.add_argument("--output-dir", type=str, help="Output directory (default: <input_basename>_qc_results)")
parser.add_argument(
    "--backed",
    type=str,
    choices=["r", "r+"],
    default=None,
    help="Load .h5ad in disk-backed mode for low memory footprint on huge datasets (default: None, loads in RAM)",
)
parser.add_argument(
    "--chunk-size", type=int, default=50000, help="Chunk size for processing ultra-large datasets (default: 50000)"
)
parser.add_argument(
    "--mad-counts",
    type=float,
    default=DEFAULT_MAD_COUNTS,
    help=f"MAD threshold for total counts (default: {DEFAULT_MAD_COUNTS})",
)
parser.add_argument(
    "--mad-genes",
    type=float,
    default=DEFAULT_MAD_GENES,
    help=f"MAD threshold for gene counts (default: {DEFAULT_MAD_GENES})",
)
parser.add_argument(
    "--mad-mt",
    type=float,
    default=DEFAULT_MAD_MT,
    help=f"MAD threshold for mitochondrial percentage (default: {DEFAULT_MAD_MT})",
)
parser.add_argument(
    "--mt-threshold",
    type=float,
    default=DEFAULT_MT_THRESHOLD,
    help=f"Hard threshold for mitochondrial percentage (default: {DEFAULT_MT_THRESHOLD})",
)
parser.add_argument(
    "--min-cells",
    type=int,
    default=DEFAULT_MIN_CELLS,
    help=f"Minimum cells for gene filtering (default: {DEFAULT_MIN_CELLS})",
)
parser.add_argument(
    "--mt-pattern",
    type=str,
    default=DEFAULT_MT_PATTERN,
    help=f'Comma-separated mitochondrial gene prefixes (default: "{DEFAULT_MT_PATTERN}")',
)
parser.add_argument(
    "--ribo-pattern",
    type=str,
    default=DEFAULT_RIBO_PATTERN,
    help=f'Comma-separated ribosomal gene prefixes (default: "{DEFAULT_RIBO_PATTERN}")',
)
parser.add_argument(
    "--hb-pattern",
    type=str,
    default=DEFAULT_HB_PATTERN,
    help=f'Hemoglobin gene regex pattern (default: "{DEFAULT_HB_PATTERN}")',
)
parser.add_argument(
    "--run-doublets",
    action="store_true",
    default=True,
    help="Local kNN doublet score (not scanpy.pp.scrublet; use scrna_scrublet.py)",
)
parser.add_argument("--no-doublets", dest="run_doublets", action="store_false", help="Disable doublet detection")
parser.add_argument(
    "--doublet-rate",
    type=float,
    default=None,
    help="Expected doublet rate (default: auto-estimated based on cell count)",
)
parser.add_argument(
    "--run-ambient", action="store_true", help="Local ambient background estimate (not SoupX/CellBender)"
)
parser.add_argument("--skip-doctor", action="store_true")

args = parser.parse_args()

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
if os.path.isdir(_SRC) and _SRC not in sys.path:
    sys.path.insert(0, _SRC)
from bionexus.gate import require_doctor

require_doctor(require_scverse=True, skip=args.skip_doctor)

# Verify input file exists
if not os.path.exists(args.input_file):
    print(f"\nError: File '{args.input_file}' not found!")
    sys.exit(1)

input_file = args.input_file
base_name = os.path.splitext(os.path.basename(input_file))[0]

# Set up output directory
if args.output_dir:
    output_dir = args.output_dir
else:
    output_dir = f"{base_name}_qc_results"

os.makedirs(output_dir, exist_ok=True)
print(f"\nOutput directory: {output_dir}")

# Display parameters
print("\nParameters:")
print(f"  MAD thresholds: counts={args.mad_counts}, genes={args.mad_genes}, MT%={args.mad_mt}")
print(f"  MT hard threshold: {args.mt_threshold}%")
print(f"  Min cells for gene filtering: {args.min_cells}")
print(f"  Gene patterns: MT={args.mt_pattern}, Ribo={args.ribo_pattern}")
print(f"  Doublet detection: {'Enabled' if args.run_doublets else 'Disabled'}")
print(f"  Ambient RNA correction: {'Enabled' if args.run_ambient else 'Disabled'}")
if args.backed:
    print(f"  Memory optimization: Backed mode '{args.backed}' (chunk size: {args.chunk_size})")

total_start = time.time()

# Load the data
print("\n[1/6] Loading data...")
t0 = time.time()
file_ext = os.path.splitext(input_file)[1].lower()

if file_ext == ".h5ad":
    if args.backed:
        adata = ad.read_h5ad(input_file, backed=args.backed)
        print(f"Loaded .h5ad in backed mode: {adata.n_obs} cells x {adata.n_vars} genes")
    else:
        adata = ad.read_h5ad(input_file)
        print(f"Loaded .h5ad file: {adata.n_obs} cells x {adata.n_vars} genes")
elif file_ext == ".h5":
    adata = sc.read_10x_h5(input_file)
    print(f"Loaded 10X .h5 file: {adata.n_obs} cells x {adata.n_vars} genes")
    adata.var_names_make_unique()
else:
    print(f"\nError: Unsupported file format '{file_ext}'. Expected .h5ad or .h5")
    sys.exit(1)

print(f"  Data load time: {time.time() - t0:.2f}s")

# Store original counts for comparison
n_cells_original = adata.n_obs
n_genes_original = adata.n_vars

# Calculate QC metrics
print("\n[2/6] Calculating QC metrics (vectorized acceleration)...")
t0 = time.time()
if args.backed or adata.n_obs > 200000:
    calculate_qc_metrics_chunked(
        adata,
        chunk_size=args.chunk_size,
        mt_pattern=args.mt_pattern,
        ribo_pattern=args.ribo_pattern,
        hb_pattern=args.hb_pattern,
    )
else:
    calculate_qc_metrics(
        adata, mt_pattern=args.mt_pattern, ribo_pattern=args.ribo_pattern, hb_pattern=args.hb_pattern, inplace=True
    )

print(f"  Found {adata.var['mt'].sum()} mitochondrial genes (pattern: {args.mt_pattern})")
print(f"  Found {adata.var['ribo'].sum()} ribosomal genes (pattern: {args.ribo_pattern})")
print(f"  Found {adata.var['hb'].sum()} hemoglobin genes (pattern: {args.hb_pattern})")
print(f"  QC calculation time: {time.time() - t0:.2f}s")

print_qc_summary(adata, label="QC Metrics Summary (before filtering)")

# Doublet Detection
doublet_mask = np.zeros(adata.n_obs, dtype=bool)
if args.run_doublets and not args.backed:
    print("\n[3/6] Local kNN doublet score (not scanpy.pp.scrublet; not scDblFinder)...")
    t0 = time.time()
    try:
        adata, doublet_summary = run_doublet_detection(adata, expected_doublet_rate=args.doublet_rate)
        doublet_mask = adata.obs["predicted_doublet"].values
        print(
            f"  Detected {doublet_summary['n_doublets_detected']} doublets ({doublet_summary['doublet_percentage']}%) "
            f"with threshold {doublet_summary['doublet_threshold']} in {time.time() - t0:.2f}s"
        )
    except Exception as e:
        print(f"  Warning: Doublet detection could not complete: {e}")
else:
    print("\n[3/6] Skipping doublet detection.")

# Ambient RNA Correction
if args.run_ambient and not args.backed:
    print("\n[4/6] Estimating and correcting ambient RNA background...")
    t0 = time.time()
    try:
        adata, ambient_summary = correct_ambient_rna(adata)
        print(
            f"  Estimated mean ambient contamination: {ambient_summary['mean_contamination_fraction'] * 100:.1f}% "
            f"({ambient_summary['pct_umi_removed']}% UMI corrected) in {time.time() - t0:.2f}s"
        )
    except Exception as e:
        print(f"  Warning: Ambient RNA correction could not complete: {e}")
else:
    print("\n[4/6] Skipping ambient RNA correction.")

# Create before-filtering visualizations
print("\nCreating QC visualizations...")
t0 = time.time()
before_plot = os.path.join(output_dir, "qc_metrics_before_filtering.png")
plot_qc_distributions(adata, before_plot, title="Quality Control Metrics - Before Filtering")
print(f"  Saved: {before_plot} ({time.time() - t0:.2f}s)")

# Apply MAD-based filtering
print("\n[5/6] Applying filtering thresholds (MAD + MT hard cutoff + Doublets)...")
t0 = time.time()

# Detect outliers for each metric
adata.obs["outlier_counts"] = detect_outliers_mad(adata, "total_counts", args.mad_counts)
adata.obs["outlier_genes"] = detect_outliers_mad(adata, "n_genes_by_counts", args.mad_genes)
adata.obs["outlier_mt"] = detect_outliers_mad(adata, "pct_counts_mt", args.mad_mt)

# Apply hard threshold for mitochondrial content
print(f"\n  Applying hard threshold for mitochondrial content (>{args.mt_threshold}%):")
high_mt_mask = apply_hard_threshold(adata, "pct_counts_mt", args.mt_threshold, operator=">")

# Combine MT filters (MAD + hard threshold)
adata.obs["outlier_mt"] = adata.obs["outlier_mt"] | high_mt_mask

# Overall filtering decision
adata.obs["pass_qc"] = ~(
    adata.obs["outlier_counts"] | adata.obs["outlier_genes"] | adata.obs["outlier_mt"] | doublet_mask
)

print(
    f"\n  Total cells failing QC: {(~adata.obs['pass_qc']).sum()} ({(~adata.obs['pass_qc']).sum() / adata.n_obs * 100:.2f}%)"
)
print(f"  Cells passing QC: {adata.obs['pass_qc'].sum()} ({adata.obs['pass_qc'].sum() / adata.n_obs * 100:.2f}%)")

# Visualize filtering thresholds
outlier_masks = {
    "total_counts": adata.obs["outlier_counts"].values,
    "n_genes_by_counts": adata.obs["outlier_genes"].values,
    "pct_counts_mt": adata.obs["outlier_mt"].values,
}

thresholds = {
    "total_counts": {"n_mads": args.mad_counts},
    "n_genes_by_counts": {"n_mads": args.mad_genes},
    "pct_counts_mt": {"n_mads": args.mad_mt, "hard": args.mt_threshold},
}

threshold_plot = os.path.join(output_dir, "qc_filtering_thresholds.png")
plot_filtering_thresholds(adata, outlier_masks, thresholds, threshold_plot)
print(f"\n  Saved: {threshold_plot}")

# Apply filtering
print("\n[6/6] Applying filters and writing cleaned dataset...")
t0 = time.time()
adata_filtered = filter_cells(adata, adata.obs["pass_qc"].values)
print(f"  Cells after filtering: {adata_filtered.n_obs} (removed {n_cells_original - adata_filtered.n_obs})")

# Filter genes
print(f"\n  Filtering genes detected in <{args.min_cells} cells...")
filter_genes(adata_filtered, min_cells=args.min_cells, inplace=True)
print(f"  Genes after filtering: {adata_filtered.n_vars} (removed {n_genes_original - adata_filtered.n_vars})")

# Generate summary statistics
print("\n" + "=" * 80)
print("QC Summary")
print("=" * 80)

print("\nBefore filtering:")
print(f"  Cells: {n_cells_original}")
print(f"  Genes: {n_genes_original}")

print("\nAfter filtering:")
print(f"  Cells: {adata_filtered.n_obs} ({adata_filtered.n_obs / n_cells_original * 100:.1f}% retained)")
print(f"  Genes: {adata_filtered.n_vars} ({adata_filtered.n_vars / n_genes_original * 100:.1f}% retained)")

# After-filtering visualizations
print("\nCreating post-filtering visualizations...")
after_plot = os.path.join(output_dir, "qc_metrics_after_filtering.png")
plot_qc_after_filtering(adata_filtered, after_plot, title="Quality Control Metrics - After Filtering")
print(f"  Saved: {after_plot}")

# Save filtered data
output_h5ad = os.path.join(output_dir, f"{base_name}_qc_filtered.h5ad")
print(f"\nSaving filtered AnnData to: {output_h5ad}")
adata_filtered.write_h5ad(output_h5ad)
print("  Save complete.")

total_elapsed = time.time() - total_start
print("\n" + "=" * 80)
print(f"Quality Control Analysis Complete in {total_elapsed:.2f}s!")
print(f"Outputs saved to: {output_dir}")
print("=" * 80)
