"""BN-ANN-IV-004: exploratory RNA agreement with program-derived ADT proxy labels.

This reused public dataset provides orthogonal measurements but no authenticated
FACS sorting, blinded predictions, or independent out-of-sample calibration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import sparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from bionexus.annotation_calibration_audit import (
    evaluate_facs_physical_ground_truth_benchmark,
)
from bionexus.provenance import capture_execution_provenance
from bionexus.validation_verifier import bind_validation_source_provenance

STUDY_DIR = REPO_ROOT / "validation" / "annotation" / "studies" / "BN-ANN-IV-004"
CITESEQ_H5AD = REPO_ROOT / "data" / "flagship" / "citeseq_pbmc_sorted" / "pbmc_5k_protein_v3.h5ad"

# Lineage-defining RNA marker modules
RNA_MARKER_MODULES: Dict[str, List[str]] = {
    "T": ["CD3D", "CD3E", "TRBC1", "TRBC2", "LCK"],
    "B": ["MS4A1", "CD79A", "CD79B", "CD37", "CD74"],
    "MONOCYTE": ["LST1", "S100A8", "S100A9", "CTSS", "LILRB1"],
    "NK": ["NKG7", "GNLY", "PRF1", "KLRD1", "CTSW"],
}


def derive_physical_surface_truth(adata: Any) -> Tuple[np.ndarray, List[str], List[str]]:
    """
    Derive author-defined proxy labels from TotalSeq-B protein quantiles; not FACS sorting.
    Gating criteria:
    - T: CD3_TotalSeqB high, CD19 low, CD14 low
    - B: CD19_TotalSeqB high, CD3 low, CD14 low
    - MONOCYTE: CD14_TotalSeqB high, CD3 low, CD19 low
    - NK: CD56_TotalSeqB high, CD3 low
    """
    protein_names = list(adata.uns["protein_names"])
    prot_matrix = np.asarray(adata.obsm["protein_expression"])

    name_to_idx = {name: i for i, name in enumerate(protein_names)}
    cd3_idx = name_to_idx.get("CD3_TotalSeqB")
    cd14_idx = name_to_idx.get("CD14_TotalSeqB")
    cd19_idx = name_to_idx.get("CD19_TotalSeqB")
    cd56_idx = name_to_idx.get("CD56_TotalSeqB")

    if None in (cd3_idx, cd14_idx, cd19_idx, cd56_idx):
        raise ValueError("Essential surface protein channels not found in dataset")

    cd3 = prot_matrix[:, cd3_idx]
    cd14 = prot_matrix[:, cd14_idx]
    cd19 = prot_matrix[:, cd19_idx]
    cd56 = prot_matrix[:, cd56_idx]

    # Normalize protein expression by CLR or quantile gating
    cd3_thresh = np.quantile(cd3, 0.40)
    cd14_thresh = np.quantile(cd14, 0.70)
    cd19_thresh = np.quantile(cd19, 0.75)
    cd56_thresh = np.quantile(cd56, 0.75)

    gated_labels: List[str] = []
    gated_indices: List[int] = []

    for i in range(adata.n_obs):
        is_t = (cd3[i] > cd3_thresh) and (cd19[i] < cd19_thresh) and (cd14[i] < cd14_thresh)
        is_b = (cd19[i] > cd19_thresh) and (cd3[i] < cd3_thresh) and (cd14[i] < cd14_thresh)
        is_mono = (cd14[i] > cd14_thresh) and (cd3[i] < cd3_thresh) and (cd19[i] < cd19_thresh)
        is_nk = (cd56[i] > cd56_thresh) and (cd3[i] < cd3_thresh) and (cd19[i] < cd19_thresh)

        # Ensure unambiguous single gate assignment
        gates = [("T", is_t), ("B", is_b), ("MONOCYTE", is_mono), ("NK", is_nk)]
        assigned = [lbl for lbl, flag in gates if flag]

        if len(assigned) == 1:
            gated_labels.append(assigned[0])
            gated_indices.append(i)

    # Extract raw counts subset for gated cells
    raw_sub = adata.X[gated_indices]
    if sparse.issparse(raw_sub):
        dense_counts = raw_sub.toarray()
    else:
        dense_counts = np.asarray(raw_sub)

    gene_names = list(adata.var_names)
    return dense_counts, gene_names, gated_labels


def run_benchmark(*, write: bool = False, output_path: Optional[Path] = None) -> Dict[str, Any]:
    import anndata as ad

    if not CITESEQ_H5AD.is_file():
        raise FileNotFoundError(f"CITE-seq dataset not found at {CITESEQ_H5AD}")
    adata = ad.read_h5ad(CITESEQ_H5AD)
    counts, genes, reference = derive_physical_surface_truth(adata)
    reference_hash = hashlib.sha256(",".join(reference).encode("utf-8")).hexdigest()
    audit = evaluate_facs_physical_ground_truth_benchmark(
        dataset_name="10x_pbmc_5k_adt_proxy_reference", raw_counts_matrix=counts,
        gene_names=genes, physical_ground_truth=reference, marker_modules=RNA_MARKER_MODULES,
        blinded_key_hash=reference_hash, confidence_margin_threshold=.70, temperature=.35,
    )
    supported = next(p for p in audit.selective_abstention if p.warrant_tier == "SUPPORTED_ONLY")
    provenance = bind_validation_source_provenance(capture_execution_provenance(
        data_source="Reused public 10x PBMC 5k processed CITE-seq; author-derived ADT quantile labels",
        download_date="2026-08-28", repo_root=REPO_ROOT,
        extra_metadata={"study_id": "BN-ANN-IV-004", "evidence_kind": "ADT_PROXY_REFERENCE_NONBLINDED"},
    ), REPO_ROOT)
    report = {
        "schema_version": "bionexus.annotation-facs-ground-truth-report.v1",
        "study_id": "BN-ANN-IV-004", "generated_at": datetime.now(timezone.utc).isoformat(),
        "capability_id": "scrna.annotation_evidence", "evidence_kind": "ADT_PROXY_REFERENCE_NONBLINDED",
        "scientific_authorization": "NONE",
        "truth_modality": {"kind": "author_defined_surface_protein_quantile_proxy",
            "channels": ["CD3_TotalSeqB", "CD19_TotalSeqB", "CD14_TotalSeqB", "CD56_TotalSeqB"],
            "independent_of_algorithms": False, "reference_labels_sha256": reference_hash,
            "reference_hash_matches": audit.reference_hash_matches, "blinding_verified": False,
            "physical_sorting_verified": False},
        "dataset": {"source": CITESEQ_H5AD.relative_to(REPO_ROOT).as_posix(),
            "n_original_cells": adata.n_obs, "n_total_cells_evaluated": audit.n_total_cells,
            "n_excluded_by_proxy_gating": adata.n_obs - audit.n_total_cells,
            "evaluated_fraction_of_original": audit.n_total_cells / adata.n_obs,
            "supported_fraction_of_original": supported.n_accepted / adata.n_obs,
            "reference_lineages": audit.physical_cell_types, "previously_used_dataset": True},
        "overall_accuracy": audit.overall_accuracy,
        "supported_tier_precision": audit.supported_tier_precision,
        "probabilistic_calibration": audit.calibration.to_dict(),
        "selective_abstention_curve": [p.to_dict() for p in audit.selective_abstention],
        "parameter_selection": {"temperature": .35, "supported_margin": .70,
            "independent_calibration_verified": False, "selection_history": "NOT_VERIFIED"},
        "status": {"run_status": "completed_proxy_reference_analysis", "maximum_maturity": "RESEARCH_ONLY",
            "independent_ground_truth_satisfied": False, "blinding_satisfied": False},
        "claim_boundary": {"supported": ["Descriptive RNA marker agreement with author-derived ADT labels on the selected subset."],
            "not_supported": ["Independent FACS ground truth", "Blinded evaluation", "Out-of-sample probability calibration",
                              "Cross-donor or laboratory generalization", "Performance on gating-excluded cells"]},
        "provenance": provenance,
    }
    if write:
        destination = output_path or STUDY_DIR / "REPORT.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--output", type=Path, help="write a new report without replacing existing evidence")
    args = parser.parse_args()
    report = run_benchmark(write=args.output is not None and not args.no_write, output_path=args.output)
    print(json.dumps({"study_id": report["study_id"], "status": report["status"], "scientific_authorization": "NONE"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
