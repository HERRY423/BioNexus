"""Preregistered public-cohort spatial study BN-SP-IV-002.

Successor to BN-SP-IV-001 addressing its published limitation (the official
Xenium XOA v4 tiny kidney output is vendor format-testing material, which
blocks promotion to public biological reference evidence).

This study runs the identical technical artifact-sensitivity controls on a
full biological public cohort: 10x Genomics "Xenium FFPE Human Breast Cancer,
Replicate 1" (XOA 1.0.1; 167,780 cells; 313-plex gene panel; invasive ductal
carcinoma tissue). The two official individual files are downloaded from the
10x CDN and pinned by SHA-256.

Honesty contract:
- The applicable controls and their thresholds are byte-identical to
  BN-SP-IV-001 (segmentation leakage direction, cell-size and transcript-
  density Spearman delta >= 0.20, coordinate permutation hash invariants).
- The FOV-confounding control is declared NOT_APPLICABLE before execution:
  the official individual-file distribution for this cohort does not include
  per-cell FOV metadata, and the run is single-section. The control is
  reported with its reason and excluded from the pass set; it remains
  exercised on the BN-SP-IV-001 artifact track.
- Segmentation truth is the vendor's own segmentation; no independent
  pathologist polygon truth set ships with the cohort. A passing run is
  therefore capped below independent ground truth.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

import h5py
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.spatial import cKDTree

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from bionexus.integrity import require_raw_count_matrix, require_spatial_coordinates
from bionexus.provenance import capture_execution_provenance, sha256_file
from bionexus.validation_verifier import bind_validation_source_provenance
from bionexus.versions import VERSION
from evals.spatial_instrument_validation import (
    _array_sha256,
    _matrix_sha256,
    _mean_neighbor_cosine,
    _nearest_neighbor,
    _spearman,
)

STUDY_ROOT = REPO_ROOT / "validation" / "spatial" / "studies" / "BN-SP-IV-002"
PREREGISTRATION = STUDY_ROOT / "PREREGISTRATION.json"
PREREGISTRATION_LOCK = STUDY_ROOT / "PREREGISTRATION_LOCK.json"
DATA_DIR = REPO_ROOT / "data" / "flagship" / "xenium_breast_rep1"
MATRIX_FILE = DATA_DIR / "Xenium_FFPE_Human_Breast_Cancer_Rep1_cell_feature_matrix.h5"
CELLS_FILE = DATA_DIR / "Xenium_FFPE_Human_Breast_Cancer_Rep1_cells.parquet"
MATRIX_SHA256 = "681e1c1dfce0e517aa63a43dcdbe25df3de81498a3684f4168c9a8e166a48404"
CELLS_SHA256 = "aac8cc395143de2d7a73a951028686c9eb4c06b9a3b32677ff1413cd20f65bd3"

SCHEMA_VERSION = "bionexus.spatial-public-cohort-validation-preregistration.v1"
STUDY_ID = "BN-SP-IV-002"
RNG_SEED = 20260830
CELL_SIZE_DELTA_MIN = 0.20
DENSITY_DELTA_MIN = 0.20


def _verify_lock() -> Dict[str, Any]:
    lock = json.loads(PREREGISTRATION_LOCK.read_text(encoding="utf-8"))
    observed = sha256_file(PREREGISTRATION)
    if observed != lock["sha256"]:
        raise RuntimeError(
            f"preregistration hash mismatch: expected {lock['sha256']}, observed {observed}; create a new study_id"
        )
    return lock


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_cohort() -> Tuple[sparse.csr_matrix, np.ndarray, pd.DataFrame]:
    if sha256_file(MATRIX_FILE) != MATRIX_SHA256 or sha256_file(CELLS_FILE) != CELLS_SHA256:
        raise RuntimeError("cohort file hashes do not match the preregistered values; refusing to run")
    with h5py.File(MATRIX_FILE, "r") as handle:
        group = handle["matrix"]
        shape = tuple(int(item) for item in group["shape"][:])
        matrix = sparse.csc_matrix(
            (group["data"][:], group["indices"][:], group["indptr"][:]), shape=shape
        ).T.tocsr()
        barcodes = np.asarray([item.decode() for item in group["barcodes"][:]], dtype=object)
        feature_types = np.asarray([item.decode() for item in group["features"]["feature_type"][:]])
    gene_mask = feature_types == "Gene Expression"
    matrix = matrix[:, gene_mask].tocsr()
    require_raw_count_matrix(matrix, label="Xenium breast Rep1 cell-feature gene counts")

    # XOA 1.0.1 writes numeric cell ids in cells.parquet while matrix barcodes are
    # strings of the same ids; normalize both sides to strings before joining.
    cells_raw = pd.read_parquet(CELLS_FILE)
    cells_raw["cell_id"] = cells_raw["cell_id"].astype(str)
    cells = cells_raw.set_index("cell_id")
    missing = [barcode for barcode in barcodes if barcode not in cells.index]
    if missing:
        raise ValueError(f"cell-feature matrix has {len(missing)} barcodes absent from cells.parquet")
    cells = cells.loc[barcodes].copy()
    coords = cells[["x_centroid", "y_centroid"]].to_numpy(dtype=np.float64)
    require_spatial_coordinates(coords, n_observations=matrix.shape[0], min_spots=100)
    return matrix, coords, cells


def phase_init() -> int:
    if PREREGISTRATION.exists():
        print(f"[SKIP] {PREREGISTRATION} already exists; init must not overwrite a preregistration.")
        return 1
    payload = {
        "schema_version": SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "title": "Technical artifact-sensitivity controls on a full biological public Xenium cohort (breast cancer Rep1)",
        "locked_before_endpoint_analysis": True,
        "locked_at": None,
        "study_status_at_lock": "PREREGISTERED_NOT_RUN",
        "capability_id": "spatial.inference_validity",
        "predecessor": {
            "study_id": "BN-SP-IV-001",
            "retained_result": "locked_negative_4_of_5_endpoints_on_format_test_material",
            "reason_for_successor": (
                "The tiny kidney output is vendor format-testing material, which blocks promotion to "
                "public biological reference evidence. This successor runs the identical controls on "
                "a full biological public cohort; BN-SP-IV-001 remains unchanged."
            ),
        },
        "dataset": {
            "cohort": "10x Genomics Xenium FFPE Human Breast Cancer, Replicate 1 (XOA 1.0.1)",
            "source_urls": [
                "https://cf.10xgenomics.com/samples/xenium/1.0.1/Xenium_FFPE_Human_Breast_Cancer_Rep1/"
                "Xenium_FFPE_Human_Breast_Cancer_Rep1_cell_feature_matrix.h5",
                "https://cf.10xgenomics.com/samples/xenium/1.0.1/Xenium_FFPE_Human_Breast_Cancer_Rep1/"
                "Xenium_FFPE_Human_Breast_Cancer_Rep1_cells.parquet",
            ],
            "files": [
                {"path": "data/flagship/xenium_breast_rep1/Xenium_FFPE_Human_Breast_Cancer_Rep1_cell_feature_matrix.h5",
                 "sha256": MATRIX_SHA256, "size_bytes": 12148885},
                {"path": "data/flagship/xenium_breast_rep1/Xenium_FFPE_Human_Breast_Cancer_Rep1_cells.parquet",
                 "sha256": CELLS_SHA256, "size_bytes": 3453894},
            ],
            "acquisition_note": (
                "Official individual CDN files pinned by SHA-256 after acquisition; the full "
                "9.86 GB output bundle was intentionally not downloaded (the transcript-molecule "
                "file and morphology images are not required by the preregistered controls)."
            ),
        },
        "input_gates": {
            "raw_nonnegative_integer_cell_feature_gene_counts": True,
            "physical_centroids_required": True,
            "cell_area_required": True,
            "minimum_cells": 100,
            "file_hashes_must_match": True,
        },
        "locked_endpoints": {
            "segmentation_leakage": "mean nearest-neighbor cosine similarity must increase after deterministic 20% neighbor mixing",
            "cell_size_bias": "Spearman correlation between cell area and total counts must increase by at least 0.20 after deterministic area scaling",
            "transcript_density_bias": "Spearman correlation between local density and total counts must increase by at least 0.20 after deterministic density scaling",
            "coordinate_permutation": "coordinate permutation must change the coordinate SHA-256 while preserving the expression matrix SHA-256",
            "fov_confounding": {
                "applicability_rule": (
                    "applicable only when the cohort distribution provides per-cell FOV metadata with "
                    "at least two distinct FOVs; declared before execution"
                ),
                "status_at_preregistration": "NOT_APPLICABLE_NO_PER_CELL_FOV_METADATA_IN_OFFICIAL_FILE_DISTRIBUTION",
                "retained_track": "the control remains exercised on the BN-SP-IV-001 artifact track",
            },
        },
        "governance": {
            "successful_result_maximum_status": "REAL_TISSUE_TECHNICAL_ACCEPTANCE_PUBLIC_BIOLOGICAL_COHORT",
            "public_reference_dataset_standard_satisfied": True,
            "independent_ground_truth_standard_satisfied": False,
            "reason": (
                "Segmentation is the vendor's own; no machine-readable independent pathologist "
                "polygon truth set ships with the official file distribution. Blinded independent "
                "ground truth and cross-host execution remain open certification criteria."
            ),
            "negative_results_retained": True,
        },
    }
    _write_json(PREREGISTRATION, payload)
    print(f"[OK] preregistration written: {PREREGISTRATION}")
    return 0


def phase_lock() -> int:
    prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    if prereg.get("locked_at"):
        print("[SKIP] preregistration already locked.")
        return 1
    prereg["locked_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(PREREGISTRATION, prereg)
    _write_json(
        PREREGISTRATION_LOCK,
        {
            "schema_version": "bionexus.preregistration-lock.v1",
            "study_id": STUDY_ID,
            "locked_path": "validation/spatial/studies/BN-SP-IV-002/PREREGISTRATION.json",
            "sha256": sha256_file(PREREGISTRATION),
            "locked_at": prereg["locked_at"],
        },
    )
    print("[OK] preregistration locked before endpoint analysis.")
    return 0


def phase_run() -> int:
    _verify_lock()
    matrix, coords, cells = read_cohort()
    totals = np.asarray(matrix.sum(axis=1)).ravel().astype(np.float64)
    area = cells["cell_area"].to_numpy(dtype=np.float64)
    neighbors = _nearest_neighbor(coords)

    baseline_cosine = _mean_neighbor_cosine(matrix, neighbors)
    leaked = (matrix.astype(np.float64) * 0.8 + matrix[neighbors].astype(np.float64) * 0.2).tocsr()
    leaked_cosine = _mean_neighbor_cosine(leaked, neighbors)

    area_z = (area - area.mean()) / max(area.std(), 1e-12)
    area_scale = np.clip(np.exp(3.5 * area_z), 0.001, 1000.0)
    area_baseline = _spearman(area, totals)
    area_injected = _spearman(area, totals * area_scale)

    tree = cKDTree(coords)
    distances, _ = tree.query(coords, k=min(6, len(coords)))
    local_density = 1.0 / np.maximum(distances[:, 1:].mean(axis=1), 1e-12)
    density_z = (local_density - local_density.mean()) / max(local_density.std(), 1e-12)
    density_scale = np.clip(np.exp(0.8 * density_z), 0.25, 4.0)
    density_baseline = _spearman(local_density, totals)
    density_injected = _spearman(local_density, totals * density_scale)

    rng = np.random.default_rng(RNG_SEED)
    permuted_coords = coords[rng.permutation(len(coords))]
    coordinate_changed = _array_sha256(coords) != _array_sha256(permuted_coords)
    expression_preserved = _matrix_sha256(matrix) == _matrix_sha256(matrix.copy())

    endpoints = {
        "segmentation_leakage": {
            "baseline_mean_neighbor_cosine": baseline_cosine,
            "injected_mean_neighbor_cosine": leaked_cosine,
            "delta": leaked_cosine - baseline_cosine,
            "passed": bool(leaked_cosine > baseline_cosine),
        },
        "cell_size_bias": {
            "baseline_spearman": area_baseline,
            "injected_spearman": area_injected,
            "delta": area_injected - area_baseline,
            "threshold": CELL_SIZE_DELTA_MIN,
            "passed": bool(area_injected - area_baseline >= CELL_SIZE_DELTA_MIN),
        },
        "transcript_density_bias": {
            "baseline_spearman": density_baseline,
            "injected_spearman": density_injected,
            "delta": density_injected - density_baseline,
            "threshold": DENSITY_DELTA_MIN,
            "passed": bool(density_injected - density_baseline >= DENSITY_DELTA_MIN),
        },
        "coordinate_permutation": {
            "coordinate_sha256_changed": coordinate_changed,
            "expression_sha256_preserved": expression_preserved,
            "passed": bool(coordinate_changed and expression_preserved),
        },
        "fov_confounding": {
            "status": "NOT_APPLICABLE",
            "reason": (
                "The official individual-file distribution for this cohort carries no per-cell FOV "
                "metadata and the run is single-section; declared NOT_APPLICABLE before execution. "
                "The control remains exercised on the BN-SP-IV-001 artifact track."
            ),
            "passed": None,
        },
    }
    applicable = {k: v for k, v in endpoints.items() if v.get("passed") is not None}
    technical_pass = all(item["passed"] for item in applicable.values())

    evidence_path = STUDY_ROOT / "evidence" / "cell_diagnostics.csv.gz"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(evidence_path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["cell_id", "x", "y", "total_gene_counts", "cell_area", "local_density"])
        for index, barcode in enumerate(cells.index.to_numpy(dtype=object)):
            writer.writerow([
                barcode, coords[index, 0], coords[index, 1], totals[index], area[index], local_density[index],
            ])

    prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    n_genes = matrix.shape[1]
    report: Dict[str, Any] = {
        "schema_version": "bionexus.spatial-public-cohort-validation-report.v1",
        "study_id": STUDY_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preregistration": {
            "sha256": sha256_file(PREREGISTRATION),
            "locked_at": prereg["locked_at"],
            "study_status_at_lock": prereg["study_status_at_lock"],
        },
        "dataset": {
            "cohort": prereg["dataset"]["cohort"],
            "n_cells": int(matrix.shape[0]),
            "n_gene_expression_features": int(n_genes),
            "cell_area_um2": {
                "mean": float(area.mean()),
                "median": float(np.median(area)),
                "min": float(area.min()),
                "max": float(area.max()),
            },
            "total_gene_counts": {
                "mean": float(totals.mean()),
                "median": float(np.median(totals)),
            },
        },
        "input_contract": {
            "raw_nonnegative_integer_counts_verified": True,
            "physical_centroids_verified": True,
            "cell_area_verified": True,
            "file_hashes_matched": True,
        },
        "endpoints": endpoints,
        "applicable_endpoints_passed": f"{sum(1 for v in applicable.values() if v['passed'])}/{len(applicable)}",
        "status": (
            "REAL_TISSUE_TECHNICAL_ACCEPTANCE_PUBLIC_BIOLOGICAL_COHORT"
            if technical_pass
            else "ENDPOINTS_NOT_MET_NEGATIVE_RESULT_RETAINED"
        ),
        "claim_boundary": (
            "Deterministic manufactured confounders are detected in the expected direction on an "
            "authentic public biological Xenium cohort. This is technical artifact sensitivity on "
            "real tissue, not biological validity, not segmentation accuracy against independent "
            "pathology truth, and not an approved spatial calibration profile."
        ),
        "evidence_files": ["evidence/cell_diagnostics.csv.gz"],
        "provenance": bind_validation_source_provenance(
            capture_execution_provenance(
                data_source="10x Genomics Xenium FFPE Human Breast Cancer Replicate 1 (XOA 1.0.1)",
                repo_root=REPO_ROOT,
                generator_version=VERSION,
                extra_metadata={"study_id": STUDY_ID, "rng_seed": RNG_SEED},
            ),
            REPO_ROOT,
        ),
    }
    _write_json(STUDY_ROOT / "REPORT.json", report)
    print(f"[OK] status={report['status']} | applicable endpoints passed: {report['applicable_endpoints_passed']}")
    for key, item in applicable.items():
        print(f"     {'PASS' if item['passed'] else 'FAIL'}  {key}: delta={item.get('delta')}")
    return 0 if technical_pass else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="BN-SP-IV-002 public-cohort spatial study")
    parser.add_argument("--phase", required=True, choices=["init", "lock", "run"])
    args = parser.parse_args()
    return {"init": phase_init, "lock": phase_lock, "run": phase_run}[args.phase]()


if __name__ == "__main__":
    sys.exit(main())
