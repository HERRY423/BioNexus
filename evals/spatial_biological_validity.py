"""BN-SP-IV-002: real Xenium tiny-input inspection, pending biological validation.

The vendor kidney tiny bundle provides coordinates for format testing. It has no
independent pathology annotations or executed biological/artifact controls here.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from bionexus.provenance import capture_execution_provenance
from bionexus.validation_verifier import bind_validation_source_provenance

STUDY_DIR = REPO_ROOT / "validation" / "spatial" / "studies" / "BN-SP-IV-002"
XENIUM_DIR = REPO_ROOT / "data" / "flagship" / "xenium_spatial_truth" / "official_tiny_outs"


def load_spatial_cells_and_pathology_annotations():
    """Legacy endpoint fails closed: this source contains no pathology labels."""
    raise ValueError("Independent pathology annotations are unavailable for the kidney tiny format dataset")


def run_benchmark(*, write: bool = False, output_path: Optional[Path] = None) -> Dict[str, Any]:
    import pandas as pd

    source = XENIUM_DIR / "cells.parquet"
    frame = pd.read_parquet(source, columns=["x_centroid", "y_centroid"])
    coords = frame.to_numpy(dtype=float)
    if len(coords) == 0 or not np.all(np.isfinite(coords)):
        raise ValueError("source coordinates must be nonempty and finite")
    provenance = bind_validation_source_provenance(capture_execution_provenance(
        data_source="10x Xenium V1 Protein Human Kidney tiny: format-testing coordinates only",
        download_date="2026-08-28", repo_root=REPO_ROOT,
        extra_metadata={"study_id": "BN-SP-IV-002", "evidence_kind": "REAL_INSTRUMENT_FORMAT_INPUT_ONLY"},
    ), REPO_ROOT)
    names = ["tumor_stroma_interface_chemokine_interaction", "optical_diffusion_segmentation_leakage",
             "cell_density_crowding_confounding", "fov_tile_edge_stitching_artifact"]
    report = {
        "schema_version": "bionexus.spatial-pathology-biological-validity-report.v1",
        "study_id": "BN-SP-IV-002", "generated_at": datetime.now(timezone.utc).isoformat(),
        "capability_id": "spatial.inference_validity", "evidence_kind": "REAL_INSTRUMENT_FORMAT_INPUT_ONLY",
        "scientific_authorization": "NONE",
        "dataset": {"source": XENIUM_DIR.relative_to(REPO_ROOT).as_posix(), "n_cells_read": len(coords),
            "n_total_cells_evaluated": 0, "tissue_type": "human_kidney_tiny_format_example",
            "pathological_domains": [], "coordinate_columns_checked": list(frame.columns)},
        "pathological_concordance": {"mean_dice_coefficient": None, "domain_metrics": [],
            "passed": False, "estimation_status": "NOT_ESTIMABLE"},
        "artifact_discrimination_battery": [{"test_name": name, "is_true_biology": None,
            "raw_spatial_statistic": None, "post_control_statistic": None,
            "system_verdict": "NOT_EVALUATED", "correctly_discriminated": None,
            "notes": "No actual control experiment or independent biological/artifact truth is available."} for name in names],
        "status": {"run_status": "technical_input_inspected_biology_pending", "maximum_maturity": "TECHNICAL_INPUT_ONLY",
            "public_reference_dataset_satisfied": False, "independent_pathology_truth_satisfied": False,
            "artifact_discrimination_satisfied": False},
        "claim_boundary": {"supported": ["Read finite coordinate columns from a real vendor kidney tiny format example."],
            "not_supported": ["Clinical pathology labels", "Spatial biological validity", "Segmentation accuracy",
                              "Discrimination of biological signal and artifacts", "Independent tissue cohort replication"]},
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
