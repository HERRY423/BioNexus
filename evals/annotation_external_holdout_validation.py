"""Run preregistered external-reference annotation studies BN-ANN-IV-002/003.

The RNA rule and reject threshold are fixed before the external Azimuth PBMC
holdout is opened.  Published reference annotations are treated as external
reference labels, not experimental biological ground truth.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence, Tuple

import numpy as np
from scipy import sparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from bionexus.provenance import capture_execution_provenance
from bionexus.validation_verifier import bind_validation_source_provenance
from evals.annotation_external_validation import LINEAGES, RNA_MARKERS, wilson_interval

STUDIES_ROOT = REPO_ROOT / "validation" / "annotation" / "studies"
DEFAULT_STUDY_ID = "BN-ANN-IV-002"


def _file_digest(path: Path, algorithm: str) -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_lock(preregistration: Path, preregistration_lock: Path) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    prereg = json.loads(preregistration.read_text(encoding="utf-8"))
    lock = json.loads(preregistration_lock.read_text(encoding="utf-8"))
    observed = _file_digest(preregistration, "sha256")
    if observed != lock["sha256"]:
        raise RuntimeError(
            f"preregistration hash mismatch: expected {lock['sha256']}, observed {observed}; create a new study_id"
        )
    return prereg, lock


def _as_dense(values: Any) -> np.ndarray:
    return values.toarray() if sparse.issparse(values) else np.asarray(values)


def _validate_and_score_counts(
    matrix: Any,
    n_obs: int,
    marker_indices: Mapping[str, Sequence[int]],
    *,
    block_size: int = 4096,
) -> Tuple[np.ndarray, np.ndarray]:
    """Fail closed on normalized X while scoring only locked marker modules."""
    candidates: list[np.ndarray] = []
    margins: list[np.ndarray] = []
    for start in range(0, int(n_obs), block_size):
        stop = min(start + block_size, int(n_obs))
        block = matrix[start:stop]
        values = block.data if sparse.issparse(block) else np.asarray(block)
        if values.size and (
            not np.all(np.isfinite(values))
            or np.any(values < 0)
            or not np.all(np.equal(values, np.floor(values)))
        ):
            raise ValueError(
                "external holdout X is not a finite non-negative integer count matrix; "
                "the locked study prohibits substituting normalized expression"
            )
        totals = np.asarray(block.sum(axis=1)).ravel().astype(np.float64, copy=False)
        if np.any(totals <= 0):
            raise ValueError("external holdout X contains zero-library cells")
        scores = []
        for lineage in LINEAGES:
            raw = _as_dense(block[:, list(marker_indices[lineage])]).astype(np.float64, copy=False)
            scores.append(np.log1p(raw / totals[:, None] * 10000.0).mean(axis=1))
        score_matrix = np.column_stack(scores)
        order = np.argsort(score_matrix, axis=1)
        rows = np.arange(score_matrix.shape[0])
        top = order[:, -1]
        candidates.append(np.asarray(LINEAGES, dtype=object)[top])
        margins.append(score_matrix[rows, top] - score_matrix[rows, order[:, -2]])
    return np.concatenate(candidates), np.concatenate(margins)


def _map_reference_label(value: Any, mapping: Mapping[str, Sequence[str]]) -> str | None:
    label = str(value).strip().casefold()
    matches = [
        lineage
        for lineage in LINEAGES
        if any(pattern.casefold() in label for pattern in mapping[lineage])
    ]
    return matches[0] if len(matches) == 1 else None


def _counts(values: Iterable[Any]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    for value in values:
        key = str(value)
        result[key] = result.get(key, 0) + 1
    return dict(sorted(result.items()))


def _write_decisions(
    path: Path,
    cell_ids: Sequence[Any],
    original_labels: Sequence[Any],
    mapped: np.ndarray,
    candidates: np.ndarray,
    margins: np.ndarray,
    accepted: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw_handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw_handle, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text_handle:
                writer = csv.writer(text_handle)
                writer.writerow(
                    ["cell_id", "external_label", "mapped_lineage", "rna_candidate", "rna_margin", "accepted"]
                )
                for index in np.flatnonzero(mapped != None):  # noqa: E711
                    writer.writerow(
                        [
                            cell_ids[index],
                            original_labels[index],
                            mapped[index],
                            candidates[index],
                            float(margins[index]),
                            bool(accepted[index]),
                        ]
                    )


def run_study(*, write: bool = True, study_id: str = DEFAULT_STUDY_ID) -> Dict[str, Any]:
    import anndata as ad

    study_root = STUDIES_ROOT / study_id
    preregistration = study_root / "PREREGISTRATION.json"
    preregistration_lock = study_root / "PREREGISTRATION_LOCK.json"
    prereg, lock = _verify_lock(preregistration, preregistration_lock)
    if prereg.get("study_id") != study_id or lock.get("study_id") != study_id:
        raise RuntimeError(f"study identity mismatch for {study_id}")
    holdout = prereg["external_holdout"]
    dataset_path = REPO_ROOT / holdout["path"]
    if dataset_path.stat().st_size != int(holdout["size_bytes"]):
        raise RuntimeError("external holdout byte length does not match the preregistered value")
    observed_md5 = _file_digest(dataset_path, "md5")
    if observed_md5 != holdout["published_md5"]:
        raise RuntimeError(
            f"external holdout MD5 mismatch: expected {holdout['published_md5']}, observed {observed_md5}"
        )
    observed_sha256 = _file_digest(dataset_path, "sha256")

    adata = ad.read_h5ad(dataset_path, backed="r")
    required_label = holdout["required_obs_label"]
    if required_label not in adata.obs:
        raise ValueError(f"external holdout lacks preregistered obs label {required_label!r}")
    matrix_source = prereg["rna_candidate_rule"].get("matrix_source", "adata.X")
    if matrix_source == "adata.X":
        selected_matrix = adata.X
        gene_names = [str(name) for name in adata.var_names]
    elif matrix_source == "adata.raw.X":
        if adata.raw is None or "_index" not in adata.raw.var:
            raise ValueError("locked adata.raw.X source or adata.raw.var['_index'] gene identifiers are unavailable")
        selected_matrix = adata.raw.X
        gene_names = [str(name) for name in adata.raw.var["_index"]]
    else:
        raise ValueError(f"unsupported locked matrix_source {matrix_source!r}")
    var_index = {name: index for index, name in enumerate(gene_names)}
    marker_indices: Dict[str, Sequence[int]] = {}
    markers_used: Dict[str, Sequence[str]] = {}
    for lineage in LINEAGES:
        genes = [gene for gene in RNA_MARKERS[lineage] if gene in var_index]
        if len(genes) < 3:
            raise ValueError(f"fewer than three locked RNA markers available for {lineage}: {genes}")
        markers_used[lineage] = genes
        marker_indices[lineage] = [var_index[gene] for gene in genes]

    try:
        candidates, margins = _validate_and_score_counts(selected_matrix, int(adata.n_obs), marker_indices)
    except ValueError as exc:
        # The input gate precedes reference-label access by design.  Preserve
        # an auditable non-evaluation instead of crashing or silently using
        # ``raw``/another layer that was not permitted by the locked protocol.
        shape = [int(adata.n_obs), int(adata.n_vars)]
        matrix_type = type(selected_matrix).__name__
        matrix_dtype = str(getattr(selected_matrix, "dtype", "unknown"))
        available_layers = [str(layer) for layer in adata.layers.keys()]
        raw_present = adata.raw is not None
        adata.file.close()
        provenance = bind_validation_source_provenance(
            capture_execution_provenance(
                data_source="Zenodo 10213715 pbmc_multimodal.h5ad",
                download_date="2026-08-28",
                repo_root=REPO_ROOT,
                extra_metadata={"study_id": study_id},
            ),
            REPO_ROOT,
        )
        report = {
            "schema_version": "bionexus.annotation-external-reference-validation-report.v1",
            "study_id": study_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "preregistration": {
                "path": str(preregistration.relative_to(REPO_ROOT)).replace("\\", "/"),
                "sha256": lock["sha256"],
                "thresholds_changed_after_lock": False,
                "external_timestamp": False,
            },
            "dataset": {
                "path": str(dataset_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "source": holdout["source"],
                "doi": holdout["doi"],
                "size_bytes": dataset_path.stat().st_size,
                "published_md5": observed_md5,
                "sha256": observed_sha256,
                "shape": shape,
                "reference_label_column_required_but_not_accessed": required_label,
            },
            "input_contract": {
                "passed": False,
                "reason": str(exc),
                "x_matrix_type": matrix_type,
                "x_dtype": matrix_dtype,
                "locked_matrix_source": matrix_source,
                "available_layers": available_layers,
                "raw_present_but_substitution_prohibited_by_lock": raw_present,
                "reference_labels_accessed": False,
            },
            "locked_gate": prereg["locked_candidate_threshold"],
            "primary_endpoints": {
                name: {
                    "observed": None,
                    "passed": False,
                    "status": "NOT_EVALUATED_INPUT_INELIGIBLE",
                }
                for name in (
                    "mapped_holdout_cells",
                    "accepted_precision_wilson_lower_95",
                    "accuracy_improvement",
                    "coverage_range",
                    "accepted_lineages",
                )
            },
            "status": {
                "run_status": "not_evaluated_input_ineligible",
                "primary_endpoints_passed": False,
                "maximum_maturity": "FRAGILE",
                "public_reference_dataset": True,
                "independent_reference_annotations": "NOT_ACCESSED_AFTER_INPUT_GATE_FAILURE",
                "independent_ground_truth": False,
            },
            "claim_boundary": {
                "supported": None,
                "not_supported": prereg["claim_exclusions"],
                "activation_blocked_on": prereg["governance"]["activation_requires"],
            },
            "markers_available": markers_used,
            "evidence_files": [],
            "provenance": provenance,
        }
        if write:
            (study_root / "REPORT.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        return report
    original_labels = np.asarray(adata.obs[required_label].astype(str), dtype=object)
    label_mapping = prereg["external_label_mapping"]
    mapped = np.asarray(
        [_map_reference_label(value, label_mapping) for value in original_labels],
        dtype=object,
    )
    mapped_mask = mapped != None  # noqa: E711
    threshold = float(prereg["locked_candidate_threshold"]["rna_margin_min"])
    accepted = mapped_mask & (margins >= threshold)
    correct = candidates == mapped

    mapped_total = int(mapped_mask.sum())
    accepted_total = int(accepted.sum())
    mapped_correct = int(correct[mapped_mask].sum())
    accepted_correct = int(correct[accepted].sum())
    ungated_accuracy = mapped_correct / mapped_total if mapped_total else 0.0
    accepted_precision = accepted_correct / accepted_total if accepted_total else 0.0
    coverage = accepted_total / mapped_total if mapped_total else 0.0
    lower, upper = wilson_interval(accepted_correct, accepted_total)
    accepted_by_lineage = _counts(mapped[accepted])
    minimum_per_lineage = int(prereg["locked_external_endpoints"]["accepted_cells_per_lineage_min"])
    accepted_lineages = sum(value >= minimum_per_lineage for value in accepted_by_lineage.values())
    endpoints = prereg["locked_external_endpoints"]
    endpoint_results = {
        "mapped_holdout_cells": {
            "observed": mapped_total,
            "threshold": int(endpoints["minimum_mapped_holdout_cells"]),
            "passed": mapped_total >= int(endpoints["minimum_mapped_holdout_cells"]),
        },
        "accepted_precision_wilson_lower_95": {
            "observed": lower,
            "threshold": float(endpoints["accepted_precision_wilson_lower_95_min"]),
            "passed": lower >= float(endpoints["accepted_precision_wilson_lower_95_min"]),
        },
        "accuracy_improvement": {
            "observed": accepted_precision - ungated_accuracy,
            "threshold": float(endpoints["accuracy_improvement_min"]),
            "passed": accepted_precision - ungated_accuracy >= float(endpoints["accuracy_improvement_min"]),
        },
        "coverage_range": {
            "observed": coverage,
            "minimum": float(endpoints["coverage_min"]),
            "maximum": float(endpoints["coverage_max"]),
            "passed": float(endpoints["coverage_min"]) <= coverage <= float(endpoints["coverage_max"]),
        },
        "accepted_lineages": {
            "observed": accepted_lineages,
            "threshold": int(endpoints["accepted_lineages_min"]),
            "minimum_cells_per_lineage": minimum_per_lineage,
            "passed": accepted_lineages >= int(endpoints["accepted_lineages_min"]),
        },
    }
    primary_pass = all(item["passed"] for item in endpoint_results.values())

    evidence_path = study_root / "evidence" / "external_holdout_cell_decisions.csv.gz"
    if write:
        _write_decisions(
            evidence_path,
            np.asarray(adata.obs_names, dtype=object),
            original_labels,
            mapped,
            candidates,
            margins,
            accepted,
        )
    adata.file.close()

    provenance = bind_validation_source_provenance(
        capture_execution_provenance(
            data_source="Zenodo 10213715 pbmc_multimodal.h5ad with externally authored Azimuth PBMC labels",
            download_date="2026-08-28",
            repo_root=REPO_ROOT,
            extra_metadata={"study_id": study_id},
        ),
        REPO_ROOT,
    )
    report: Dict[str, Any] = {
        "schema_version": "bionexus.annotation-external-reference-validation-report.v1",
        "study_id": study_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preregistration": {
            "path": str(preregistration.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": lock["sha256"],
            "thresholds_changed_after_lock": False,
            "external_timestamp": False,
        },
        "dataset": {
            "path": str(dataset_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "source": holdout["source"],
            "doi": holdout["doi"],
            "size_bytes": dataset_path.stat().st_size,
            "published_md5": observed_md5,
            "sha256": observed_sha256,
            "shape": [int(adata.n_obs), int(adata.n_vars)],
            "reference_label_column": required_label,
        },
        "input_contract": {
            "passed": True,
            "locked_matrix_source": matrix_source,
            "complete_matrix_finite_nonnegative_integer": True,
        },
        "access_disclosure": prereg.get("access_disclosure", {"blinding_status": "LOCKED_BLIND_HOLDOUT"}),
        "locked_gate": prereg["locked_candidate_threshold"],
        "holdout": {
            "mapped_cells": mapped_total,
            "unmapped_cells": int((~mapped_mask).sum()),
            "original_label_counts": _counts(original_labels),
            "mapped_lineage_counts": _counts(mapped[mapped_mask]),
            "accepted_cells": accepted_total,
            "accepted_by_external_lineage": accepted_by_lineage,
            "ungated_accuracy": ungated_accuracy,
            "accepted_precision": accepted_precision,
            "accepted_precision_wilson_95": [lower, upper],
            "coverage": coverage,
        },
        "primary_endpoints": endpoint_results,
        "status": {
            "run_status": "positive_candidate" if primary_pass else "negative_result",
            "primary_endpoints_passed": primary_pass,
            "maximum_maturity": (
                prereg["governance"]["successful_result_maximum_status"] if primary_pass else "FRAGILE"
            ),
            "public_reference_dataset": True,
            "independent_reference_annotations": True,
            "independent_ground_truth": False,
        },
        "claim_boundary": {
            "supported_if_positive": prereg["claim_target"],
            "not_supported": prereg["claim_exclusions"],
            "activation_blocked_on": prereg["governance"]["activation_requires"],
        },
        "markers_used": markers_used,
        "evidence_files": [str(evidence_path.relative_to(REPO_ROOT)).replace("\\", "/")],
        "provenance": provenance,
    }
    if write:
        (study_root / "REPORT.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--study-id", choices=("BN-ANN-IV-002", "BN-ANN-IV-003"), default=DEFAULT_STUDY_ID)
    args = parser.parse_args()
    report = run_study(write=not args.no_write, study_id=args.study_id)
    print(json.dumps(report["status"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
