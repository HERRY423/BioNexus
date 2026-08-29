"""Preregistered real CITE-seq calibration/holdout study BN-ANN-IV-001.

The study evaluates a conservative acceptance gate for coarse RNA-derived PBMC
lineage candidates against paired ADT anchors. BioNexus does not assign the
labels and a successful run produces a CANDIDATE calibration artifact only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

import numpy as np
from scipy import sparse

from bionexus.integrity import require_raw_count_matrix
from bionexus.provenance import capture_execution_provenance
from bionexus.validation_verifier import bind_validation_source_provenance

REPO_ROOT = Path(__file__).resolve().parents[1]
STUDY_ROOT = REPO_ROOT / "validation" / "annotation" / "studies" / "BN-ANN-IV-001"
PREREGISTRATION = STUDY_ROOT / "PREREGISTRATION.json"
PREREGISTRATION_LOCK = STUDY_ROOT / "PREREGISTRATION_LOCK.json"

LINEAGES: Tuple[str, ...] = ("T", "B", "MONOCYTE", "NK")
ANCHOR_PROTEINS: Mapping[str, str] = {
    "T": "CD3_TotalSeqB",
    "B": "CD19_TotalSeqB",
    "MONOCYTE": "CD14_TotalSeqB",
    "NK": "CD56_TotalSeqB",
}
RNA_MARKERS: Mapping[str, Tuple[str, ...]] = {
    "T": ("CD3D", "CD3E", "TRBC1", "TRBC2", "LCK"),
    "B": ("MS4A1", "CD79A", "CD79B", "CD37", "CD74"),
    "MONOCYTE": ("LST1", "S100A8", "S100A9", "CTSS", "LILRB1"),
    "NK": ("NKG7", "GNLY", "PRF1", "KLRD1", "CTSW"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> Tuple[float, float]:
    if total <= 0:
        return 0.0, 1.0
    proportion = successes / total
    denominator = 1.0 + z * z / total
    centre = proportion + z * z / (2.0 * total)
    radius = z * math.sqrt(proportion * (1.0 - proportion) / total + z * z / (4.0 * total * total))
    return (centre - radius) / denominator, (centre + radius) / denominator


def _verify_preregistration_lock() -> Dict[str, Any]:
    lock = json.loads(PREREGISTRATION_LOCK.read_text(encoding="utf-8"))
    observed = sha256_file(PREREGISTRATION)
    if observed != lock["sha256"]:
        raise RuntimeError(
            f"preregistration hash mismatch: expected {lock['sha256']}, observed {observed}; create a new study_id"
        )
    return lock


def _dense_slice(matrix: Any, columns: Sequence[int]) -> np.ndarray:
    selected = matrix[:, list(columns)]
    return selected.toarray() if sparse.issparse(selected) else np.asarray(selected)


def _row_sums(matrix: Any) -> np.ndarray:
    return np.asarray(matrix.sum(axis=1)).ravel()


def _protein_matrix(adata: Any) -> Tuple[np.ndarray, Sequence[str]]:
    if "protein_expression" not in adata.obsm:
        raise ValueError("missing obsm['protein_expression']")
    names = [str(item) for item in adata.uns.get("protein_names", [])]
    values = np.asarray(adata.obsm["protein_expression"])
    if values.ndim != 2 or len(names) != values.shape[1]:
        raise ValueError("protein_expression columns are not aligned with uns['protein_names']")
    require_raw_count_matrix(values, label="CITE-seq ADT counts")
    return values, names


def _orthogonal_anchors(protein: np.ndarray, names: Sequence[str]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    name_to_index = {name: index for index, name in enumerate(names)}
    missing = [name for name in ANCHOR_PROTEINS.values() if name not in name_to_index]
    if missing:
        raise ValueError(f"missing preregistered ADT anchors: {missing}")
    anchor = np.column_stack([protein[:, name_to_index[ANCHOR_PROTEINS[label]]] for label in LINEAGES])
    order = np.argsort(anchor, axis=1)
    top_index = order[:, -1]
    runner_index = order[:, -2]
    rows = np.arange(anchor.shape[0])
    top = anchor[rows, top_index]
    runner = anchor[rows, runner_index]
    high_confidence = (top >= 5.0) & ((top + 1.0) / (runner + 1.0) >= 2.0)
    labels = np.asarray(LINEAGES, dtype=object)[top_index]
    return labels, high_confidence, (top + 1.0) / (runner + 1.0)


def _rna_candidates(adata: Any) -> Tuple[np.ndarray, np.ndarray, Dict[str, Sequence[str]]]:
    require_raw_count_matrix(adata.X, label="CITE-seq RNA counts")
    var_index = {str(name): index for index, name in enumerate(adata.var_names)}
    totals = _row_sums(adata.X)
    if np.any(totals <= 0):
        raise ValueError("RNA matrix contains zero-library cells")
    module_scores = []
    used: Dict[str, Sequence[str]] = {}
    for lineage in LINEAGES:
        genes = [gene for gene in RNA_MARKERS[lineage] if gene in var_index]
        if len(genes) < 3:
            raise ValueError(f"fewer than three preregistered RNA markers available for {lineage}: {genes}")
        used[lineage] = genes
        raw = _dense_slice(adata.X, [var_index[gene] for gene in genes]).astype(np.float64, copy=False)
        normalized = np.log1p(raw / totals[:, None] * 10000.0)
        module_scores.append(normalized.mean(axis=1))
    scores = np.column_stack(module_scores)
    order = np.argsort(scores, axis=1)
    rows = np.arange(scores.shape[0])
    top_index = order[:, -1]
    margin = scores[rows, top_index] - scores[rows, order[:, -2]]
    labels = np.asarray(LINEAGES, dtype=object)[top_index]
    return labels, margin, used


def _fit_candidate_threshold(margins: np.ndarray, correct: np.ndarray) -> Dict[str, Any] | None:
    order = np.argsort(-margins, kind="mergesort")
    ordered_margin = margins[order]
    ordered_correct = correct[order].astype(int)
    cumulative = np.cumsum(ordered_correct)
    best: Dict[str, Any] | None = None
    for index, threshold in enumerate(ordered_margin):
        if index + 1 < len(ordered_margin) and ordered_margin[index + 1] == threshold:
            continue
        accepted = index + 1
        if accepted < 100:
            continue
        successes = int(cumulative[index])
        lower, upper = wilson_interval(successes, accepted)
        if lower >= 0.90:
            best = {
                "threshold": float(threshold),
                "accepted": accepted,
                "correct": successes,
                "precision": successes / accepted,
                "precision_wilson_95": [lower, upper],
                "coverage": accepted / len(margins),
            }
    return best


def _dataset_records(path: Path) -> Dict[str, Any]:
    import anndata as ad

    adata = ad.read_h5ad(path)
    protein, protein_names = _protein_matrix(adata)
    truth, anchored, anchor_ratio = _orthogonal_anchors(protein, protein_names)
    candidate, margin, markers_used = _rna_candidates(adata)
    return {
        "cell_ids": np.asarray(adata.obs_names, dtype=object),
        "truth": truth,
        "anchored": anchored,
        "anchor_ratio": anchor_ratio,
        "candidate": candidate,
        "margin": margin,
        "correct": candidate == truth,
        "shape": [int(adata.n_obs), int(adata.n_vars)],
        "markers_used": markers_used,
        "protein_names": protein_names,
    }


def _counts(values: Iterable[Any]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def run_study(*, write: bool = True) -> Dict[str, Any]:
    lock = _verify_preregistration_lock()
    prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    calibration_path = REPO_ROOT / prereg["datasets"]["calibration"]["path"]
    holdout_path = REPO_ROOT / prereg["datasets"]["holdout"]["path"]
    for role, path in (("calibration", calibration_path), ("holdout", holdout_path)):
        expected = prereg["datasets"][role]["sha256"]
        observed = sha256_file(path)
        if observed != expected:
            raise RuntimeError(f"{role} dataset hash mismatch: expected {expected}, observed {observed}")

    calibration = _dataset_records(calibration_path)
    calibration_mask = calibration["anchored"]
    fitted = _fit_candidate_threshold(
        calibration["margin"][calibration_mask], calibration["correct"][calibration_mask]
    )
    holdout = _dataset_records(holdout_path)
    holdout_mask = holdout["anchored"]
    holdout_total = int(holdout_mask.sum())
    holdout_correct = int(holdout["correct"][holdout_mask].sum())
    all_lower, all_upper = wilson_interval(holdout_correct, holdout_total)

    if fitted is None:
        accepted_mask = np.zeros_like(holdout_mask, dtype=bool)
    else:
        accepted_mask = holdout_mask & (holdout["margin"] >= fitted["threshold"])
    accepted_total = int(accepted_mask.sum())
    accepted_correct = int(holdout["correct"][accepted_mask].sum())
    accepted_lower, accepted_upper = wilson_interval(accepted_correct, accepted_total)
    coverage = accepted_total / holdout_total if holdout_total else 0.0
    ungated_accuracy = holdout_correct / holdout_total if holdout_total else 0.0
    accepted_precision = accepted_correct / accepted_total if accepted_total else 0.0
    accepted_by_lineage = _counts(holdout["truth"][accepted_mask])
    holdout_anchor_by_lineage = _counts(holdout["truth"][holdout_mask])
    lineages_with_minimum = sum(count >= 20 for count in accepted_by_lineage.values())

    endpoint_results = {
        "precision_wilson_lower_95": {
            "observed": accepted_lower,
            "threshold": 0.90,
            "passed": fitted is not None and accepted_lower >= 0.90,
        },
        "coverage": {"observed": coverage, "threshold": 0.10, "passed": coverage >= 0.10},
        "accepted_lineages": {
            "observed": lineages_with_minimum,
            "threshold": 3,
            "passed": lineages_with_minimum >= 3,
        },
        "accuracy_enrichment": {
            "accepted": accepted_precision,
            "ungated": ungated_accuracy,
            "passed": accepted_total > 0 and accepted_precision >= ungated_accuracy,
        },
    }
    primary_pass = fitted is not None and all(item["passed"] for item in endpoint_results.values())
    # This audit does not alter or re-fit any preregistered endpoint. It prevents
    # a numerically passing but non-selective threshold from being promoted as
    # evidence that the gate enriched correctness.
    degenerate_gate = bool(
        fitted is not None
        and (
            fitted["threshold"] <= 0.0
            or coverage >= 0.999999
            or accepted_precision <= ungated_accuracy
        )
    )
    if primary_pass and degenerate_gate:
        status = "endpoints_met_inconclusive"
    else:
        status = "positive_candidate" if primary_pass else "negative_result"

    STUDY_ROOT.mkdir(parents=True, exist_ok=True)
    evidence_path = STUDY_ROOT / "evidence" / "holdout_cell_decisions.csv"
    report_path = STUDY_ROOT / "REPORT.json"
    if write:
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        with evidence_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                ["cell_id", "adt_anchor", "anchor_ratio", "rna_candidate", "rna_margin", "correct", "accepted"]
            )
            for index in np.flatnonzero(holdout_mask):
                writer.writerow(
                    [
                        holdout["cell_ids"][index],
                        holdout["truth"][index],
                        float(holdout["anchor_ratio"][index]),
                        holdout["candidate"][index],
                        float(holdout["margin"][index]),
                        bool(holdout["correct"][index]),
                        bool(accepted_mask[index]),
                    ]
                )

    provenance = bind_validation_source_provenance(
        capture_execution_provenance(
            data_source="YosefLab/scVI-data processed public 10x PBMC CITE-seq",
            download_date="2026-08-28",
            repo_root=REPO_ROOT,
            extra_metadata={"study_id": "BN-ANN-IV-001"},
        ),
        REPO_ROOT,
    )
    report: Dict[str, Any] = {
        "schema_version": "bionexus.annotation-independent-validation-report.v1",
        "study_id": "BN-ANN-IV-001",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preregistration": {
            "path": str(PREREGISTRATION.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": lock["sha256"],
            "thresholds_changed_after_lock": False,
            "external_timestamp": False,
        },
        "datasets": {
            "calibration": {
                "path": str(calibration_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "sha256": sha256_file(calibration_path),
                "shape": calibration["shape"],
                "anchor_cells": int(calibration_mask.sum()),
                "anchor_lineages": _counts(calibration["truth"][calibration_mask]),
            },
            "holdout": {
                "path": str(holdout_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "sha256": sha256_file(holdout_path),
                "shape": holdout["shape"],
                "anchor_cells": holdout_total,
                "ambiguous_cells": int((~holdout_mask).sum()),
                "anchor_lineages": holdout_anchor_by_lineage,
            },
        },
        "candidate_gate": fitted,
        "holdout": {
            "ungated_accuracy": ungated_accuracy,
            "ungated_accuracy_wilson_95": [all_lower, all_upper],
            "accepted_cells": accepted_total,
            "accepted_correct": accepted_correct,
            "accepted_precision": accepted_precision,
            "accepted_precision_wilson_95": [accepted_lower, accepted_upper],
            "coverage": coverage,
            "accepted_by_adt_anchor": accepted_by_lineage,
        },
        "primary_endpoints": endpoint_results,
        "post_run_scientific_audit": {
            "preregistered_endpoint": False,
            "degenerate_nonselective_gate": degenerate_gate,
            "claim_target_supported": primary_pass and not degenerate_gate,
            "reason": (
                "The fitted gate accepted the full held-out anchor set or did not improve accuracy; "
                "the preregistered numeric endpoints were met but correctness enrichment was not demonstrated."
                if degenerate_gate
                else "No degeneracy condition was observed."
            ),
        },
        "status": {
            "run_status": status,
            "primary_endpoints_passed": primary_pass,
            "maximum_maturity": "CANDIDATE" if primary_pass and not degenerate_gate else "FRAGILE",
            "public_reference_dataset": True,
            "independent_ground_truth": False,
        },
        "claim_boundary": {
            "supported_if_positive": "context-specific candidate gate on two real public paired RNA/ADT PBMC datasets",
            "not_supported": prereg["claim_exclusions"],
            "activation_blocked_on": prereg["governance"]["activation_requires"],
        },
        "markers_used": holdout["markers_used"],
        "evidence_files": [str(evidence_path.relative_to(REPO_ROOT)).replace("\\", "/")],
        "provenance": provenance,
    }
    if write:
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true", help="run without writing evidence artifacts")
    args = parser.parse_args()
    report = run_study(write=not args.no_write)
    print(json.dumps(report["status"], indent=2))
    return 0 if report["status"]["run_status"] in {
        "positive_candidate",
        "endpoints_met_inconclusive",
        "negative_result",
    } else 1


if __name__ == "__main__":
    raise SystemExit(main())
