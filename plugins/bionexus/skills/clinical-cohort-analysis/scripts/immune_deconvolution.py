#!/usr/bin/env python3
"""
NNLS mixture deconvolution. Requires a caller-supplied signature matrix.
This is not CIBERSORT/LM22 unless that matrix is the published LM22 matrix.
"""

import argparse
import logging
from typing import List, Optional

import numpy as np
import pandas as pd
from scipy.optimize import nnls

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("ImmuneDeconvolution")


def deconvolve_immune_microenvironment(
    bulk_tpm: np.ndarray,
    gene_names: List[str],
    reference_signature_matrix: Optional[np.ndarray] = None,
    cell_type_names: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Deconvolve bulk RNA mixture expression vector/matrix into immune cell fractions.
    bulk_tpm: (n_samples, n_genes) or (n_genes,)
    """
    if bulk_tpm.ndim == 1:
        bulk_tpm = bulk_tpm.reshape(1, -1)

    n_samples, n_genes = bulk_tpm.shape

    if reference_signature_matrix is None:
        raise ValueError(
            "NNLS deconvolution requires a caller-supplied signature matrix "
            "(genes x cell types). Refusing to invent an LM22-like random matrix."
        )
    ref_matrix = np.asarray(reference_signature_matrix, dtype=float)
    if ref_matrix.shape[0] != n_genes:
        raise ValueError(f"Signature matrix has {ref_matrix.shape[0]} genes but bulk has {n_genes}.")
    if cell_type_names is None:
        cell_names = [f"component_{i}" for i in range(ref_matrix.shape[1])]
    else:
        cell_names = list(cell_type_names)
    k_types = len(cell_names)
    if ref_matrix.shape[1] != k_types:
        raise ValueError(f"Signature has {ref_matrix.shape[1]} columns but {k_types} cell-type names.")

    proportions = []
    for s_idx in range(n_samples):
        y = bulk_tpm[s_idx, :]
        # Solve argmin || ref_matrix * x - y ||_2  s.t. x >= 0
        weights, _ = nnls(ref_matrix, y)
        total = np.sum(weights)
        norm_weights = (weights / total) if total > 0 else np.ones(k_types) / k_types
        proportions.append(norm_weights)

    df_res = pd.DataFrame(proportions, columns=cell_names)
    return df_res


def main() -> None:
    parser = argparse.ArgumentParser(description="NNLS deconvolution (requires a signature matrix)")
    parser.add_argument("--bulk", required=True, help="CSV: samples x genes")
    parser.add_argument("--signature", required=True, help="CSV: genes x cell types")
    parser.add_argument("--output", "-o", default="deconvolution.csv")
    args = parser.parse_args()
    bulk = pd.read_csv(args.bulk, index_col=0)
    signature = pd.read_csv(args.signature, index_col=0)
    shared = [g for g in bulk.columns if g in signature.index]
    if not shared:
        raise ValueError("No shared gene names between bulk and signature.")
    df = deconvolve_immune_microenvironment(
        bulk[shared].to_numpy(),
        shared,
        reference_signature_matrix=signature.loc[shared].to_numpy(),
        cell_type_names=list(signature.columns),
    )
    df.index = bulk.index
    df.to_csv(args.output)
    print(df.to_csv(index=True))


if __name__ == "__main__":
    main()
