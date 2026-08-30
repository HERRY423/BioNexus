"""Run the donor-aware blinded annotation study BN-ANN-IV-004.

Successor to BN-ANN-IV-003 addressing its published limitation (non-blinded
external reference evaluation): the acceptance threshold is derived ONLY on
development donors of a never-seen donor-aware cohort (Kang et al. 2018,
GSE96583; 8 donors; published GEO/Seurat cell assignments) and the held-out
donors are scored strictly after the preregistration lock.

Honesty contract:
- The lineage marker modules and candidate rule are byte-identical to
  BN-ANN-IV-001/003 (imported from evals.annotation_external_validation).
- Donor split, threshold grid, and endpoints are fixed in PREREGISTRATION.json
  before any holdout label access; PREREGISTRATION_LOCK.json binds the file
  hash and is verified again before the holdout phase runs.
- Holdout label marginals are not consulted before the lock. Category names
  were visible during dataset reconnaissance and are disclosed as such.
- Dendritic cells map to the coarse MONOCYTE family (shared myeloid module
  markers) — the conservative choice; Megakaryocytes have no module and are
  excluded and enumerated. Any successful result is capped below independent
  blinded validation and does not promote certification on its own.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np
from scipy import sparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from bionexus.provenance import capture_execution_provenance, sha256_file
from bionexus.validation_verifier import bind_validation_source_provenance
from bionexus.versions import VERSION
from evals.annotation_external_validation import LINEAGES, RNA_MARKERS, wilson_interval

STUDY_ROOT = REPO_ROOT / "validation" / "annotation" / "studies" / "BN-ANN-IV-004"
PREREGISTRATION = STUDY_ROOT / "PREREGISTRATION.json"
PREREGISTRATION_LOCK = STUDY_ROOT / "PREREGISTRATION_LOCK.json"
DATASET = REPO_ROOT / "data" / "flagship" / "kang2018_pbmc_ifnb" / "pbmc_ifnb_counts.h5ad"
DATASET_SHA256 = "46122ba4e196561a781123614d856fed7d1ca05743d39a1d117597fd6d0bb993"

SCHEMA_VERSION = "bionexus.annotation-donor-holdout-validation-preregistration.v1"
STUDY_ID = "BN-ANN-IV-004"
THRESHOLD_GRID = [round(0.05 * i, 2) for i in range(0, 61)]  # 0.00 .. 3.00
DEV_WILSON_LOWER_MIN = 0.9
DEV_COVERAGE_RANGE = (0.1, 0.8)

# Published Kang et al. 2017 (GSE96583) GEO/Seurat assignments -> coarse lineage.
EXTERNAL_LABEL_MAPPING: Dict[str, str | None] = {
    "B cells": "B",
    "CD4 T cells": "T",
    "CD8 T cells": "T",
    "CD14+ Monocytes": "MONOCYTE",
    "FCGR3A+ Monocytes": "MONOCYTE",
    "Dendritic cells": "MONOCYTE",
    "NK cells": "NK",
    "Megakaryocytes": None,
}
EXCLUDED_LABELS = sorted(label for label, mapped in EXTERNAL_LABEL_MAPPING.items() if mapped is None)
DEVELOPMENT_DONORS = ["101", "107", "1015", "1016"]
HOLDOUT_DONORS = ["1039", "1244", "1256", "1488"]


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _verify_lock() -> Dict[str, Any]:
    lock = json.loads(PREREGISTRATION_LOCK.read_text(encoding="utf-8"))
    observed = sha256_file(PREREGISTRATION)
    if observed != lock["sha256"]:
        raise RuntimeError(
            f"preregistration hash mismatch: expected {lock['sha256']}, observed {observed}; create a new study_id"
        )
    return lock


def load_cohort() -> Tuple[Any, List[str], np.ndarray]:
    """Read the committed cohort and verify the hash, raw-count contract, and donors."""
    import anndata as ad

    if sha256_file(DATASET) != DATASET_SHA256:
        raise RuntimeError(
            "cohort hash mismatch: pbmc_ifnb_counts.h5ad does not match the preregistered "
            "SHA-256; refusing to run the study on substituted data"
        )
    adata = ad.read_h5ad(DATASET)
    obs = adata.obs
    required = {"donor", "geo_cell_type"}
    missing = required - set(obs.columns)
    if missing:
        raise RuntimeError(f"cohort obs is missing preregistered columns: {sorted(missing)}")
    donors = [str(d) for d in obs["donor"].astype(str)]
    unknown = sorted(set(donors) - set(DEVELOPMENT_DONORS) - set(HOLDOUT_DONORS))
    if unknown:
        raise RuntimeError(f"cohort contains donors outside the preregistered split: {unknown}")
    return adata, donors, np.asarray(obs["geo_cell_type"].astype(str))


def panel_var_names(adata: Any) -> List[str]:
    raw = adata.raw if adata.raw is not None else adata
    return [str(v) for v in raw.var_names]


def score_cells(adata: Any, marker_modules: Mapping[str, Sequence[str]]) -> Tuple[np.ndarray, np.ndarray]:
    """Apply the frozen candidate rule (panel-intersected modules) to the raw-count matrix."""
    matrix = adata.raw.X if adata.raw is not None else adata.X
    var_index = panel_var_names(adata)
    marker_indices: Dict[str, List[int]] = {}
    for lineage in LINEAGES:
        indices: List[int] = []
        for marker in marker_modules[lineage]:
            if marker not in var_index:
                raise RuntimeError(
                    f"frozen module marker {marker} absent from cohort gene index; "
                    "the preregistration must be re-audited, not patched at runtime"
                )
            indices.append(var_index.index(marker))
        marker_indices[lineage] = indices

    totals = np.asarray(matrix.sum(axis=1)).ravel().astype(np.float64, copy=False)
    if np.any(totals <= 0):
        raise RuntimeError("cohort X contains zero-library cells; raw-count contract violated")

    score_rows: List[np.ndarray] = []
    for lineage in LINEAGES:
        block = matrix[:, marker_indices[lineage]]
        values = block.toarray() if sparse.issparse(block) else np.asarray(block)
        values = values.astype(np.float64, copy=False)
        if values.size and (not np.all(np.isfinite(values)) or np.any(values < 0)
                            or not np.all(np.equal(values, np.floor(values)))):
            raise RuntimeError(
                "cohort X is not a finite non-negative integer count matrix; the locked study "
                "prohibits substituting normalized expression"
            )
        score_rows.append(np.log1p(values / totals[:, None] * 10000.0).mean(axis=1))
    score_matrix = np.column_stack(score_rows)
    order = np.argsort(score_matrix, axis=1)
    rows = np.arange(score_matrix.shape[0])
    candidates = np.asarray(LINEAGES, dtype=object)[order[:, -1]]
    margins = score_matrix[rows, order[:, -1]] - score_matrix[rows, order[:, -2]]
    return candidates, margins


def map_labels(labels: np.ndarray) -> Tuple[np.ndarray, Dict[str, int]]:
    """Map published labels to coarse lineages; unmapped labels are excluded and counted."""
    mapped = np.empty(labels.shape, dtype=object)
    counts: Dict[str, int] = {}
    for i, label in enumerate(labels):
        lineage = EXTERNAL_LABEL_MAPPING.get(str(label))
        mapped[i] = lineage
        key = str(label)
        counts[key] = counts.get(key, 0) + 1
    return mapped, counts


def _metrics(mask_mapped: np.ndarray, mask_accepted: np.ndarray, correct: np.ndarray) -> Dict[str, Any]:
    mapped_total = int(mask_mapped.sum())
    accepted_total = int((mask_mapped & mask_accepted).sum())
    accepted_correct = int((mask_mapped & mask_accepted & correct).sum())
    mapped_correct = int((mask_mapped & correct).sum())
    precision = accepted_correct / accepted_total if accepted_total else 0.0
    lower, upper = wilson_interval(accepted_correct, accepted_total)
    ungated = mapped_correct / mapped_total if mapped_total else 0.0
    coverage = accepted_total / mapped_total if mapped_total else 0.0
    return {
        "mapped_cells": mapped_total,
        "accepted_cells": accepted_total,
        "accepted_correct": accepted_correct,
        "accepted_precision": precision,
        "accepted_precision_wilson_lower_95": lower,
        "accepted_precision_wilson_upper_95": upper,
        "ungated_accuracy": ungated,
        "accuracy_improvement": precision - ungated,
        "coverage": coverage,
    }


def evaluate_at_threshold(
    candidates: np.ndarray,
    margins: np.ndarray,
    mapped: np.ndarray,
    donor: Sequence[str],
    threshold: float,
    donors_subset: Sequence[str] | None = None,
) -> Dict[str, Any]:
    donor_arr = np.asarray(donor, dtype=object)
    if donors_subset is not None:
        keep = np.isin(donor_arr, np.asarray(donors_subset, dtype=object))
        candidates, margins, mapped = candidates[keep], margins[keep], mapped[keep]
        donor_arr = donor_arr[keep]
    correct = mapped == candidates
    accepted = margins >= threshold
    pooled = _metrics(np.isin(mapped, LINEAGES), accepted, correct)
    by_donor: Dict[str, Dict[str, Any]] = {}
    for d in sorted(set(donor_arr.tolist())):
        mask = donor_arr == d
        by_donor[str(d)] = _metrics(np.isin(mapped[mask], LINEAGES), accepted[mask], correct[mask])
    by_lineage_accepted: Dict[str, int] = {}
    for lineage in LINEAGES:
        by_lineage_accepted[lineage] = int((np.isin(mapped, LINEAGES) & accepted & (mapped == lineage)).sum())
    return {
        "threshold": threshold,
        **pooled,
        "by_donor": by_donor,
        "accepted_by_external_lineage": by_lineage_accepted,
        "accepted_lineages": sum(1 for v in by_lineage_accepted.values() if v >= 20),
    }


# ----------------------------------------------------------------- phases


def phase_init() -> int:
    if PREREGISTRATION.exists():
        print(f"[SKIP] {PREREGISTRATION} already exists; init must not overwrite a preregistration.")
        return 1
    import anndata as ad

    adata = ad.read_h5ad(DATASET)
    var_names = set(panel_var_names(adata))
    frozen_modules: Dict[str, List[str]] = {}
    dropped: Dict[str, List[str]] = {}
    for lineage in LINEAGES:
        present = [m for m in RNA_MARKERS[lineage] if m in var_names]
        absent = [m for m in RNA_MARKERS[lineage] if m not in var_names]
        if len(present) < 2:
            raise RuntimeError(
                f"panel audit failure: lineage {lineage} retains {len(present)} of "
                f"{len(RNA_MARKERS[lineage])} markers on this capture panel; "
                "the module is not evaluable and the study design must change"
            )
        frozen_modules[lineage] = present
        if absent:
            dropped[lineage] = absent

    payload = {
        "schema_version": SCHEMA_VERSION,
        "study_id": STUDY_ID,
        "title": "Donor-held-out blinded successor evaluation on the never-seen Kang 2018 GSE96583 cohort",
        "amendment_history": [
            {
                "at": "before-dev-phase",
                "change": "initial preregistration draft failed the panel audit at scoring time "
                "(TRBC1/TRBC2 absent from the GSE96583 capture panel); the design was amended to "
                "freeze panel-intersected modules before any scoring. No labels were accessed and "
                "no threshold was derived at amendment time.",
            }
        ],
        "locked_at": None,
        "study_status_at_lock": "PREREGISTERED_BEFORE_DEVELOPMENT_PHASE",
        "capability_id": "scrna.annotation_evidence",
        "predecessor": {
            "study_id": "BN-ANN-IV-003",
            "retained_result": "candidate_external_reference_nonblinded",
            "reason_for_successor": (
                "BN-ANN-IV-003 met all endpoints but was explicitly NOT_BLINDED_TO_LABEL_DISTRIBUTION "
                "on a single-pool external reference. This successor derives the threshold only on "
                "development donors of a never-seen donor-aware cohort and locks before any holdout "
                "label access; BN-ANN-IV-003 remains unchanged."
            ),
        },
        "access_disclosure": {
            "dataset_structure_seen": True,
            "dev_label_distributions_seen": True,
            "holdout_label_marginal_counts_seen_before_lock": False,
            "holdout_label_category_names_seen": True,
            "panel_audit_before_any_scoring": True,
            "blinding_status": "THRESHOLD_DERIVED_ON_DEV_DONORS_HOLDOUT_LABELS_NOT_CONSULTED_BEFORE_LOCK",
            "consequence": (
                "Same-implementer blinding cannot be absolute; a successful result is capped below "
                "independent blinded external validation and below CERTIFIED, which additionally "
                "requires cross-host execution and an external reviewer."
            ),
        },
        "claim_target": (
            "With the BN-ANN-IV-001 candidate rule unchanged except for the capture-panel "
            "intersection of its marker modules (frozen before any scoring), the RNA margin gate "
            "with a threshold derived only on development donors selectively enriches agreement "
            "with the published external reference labels on held-out donors never used for "
            "threshold derivation."
        ),
        "claim_exclusions": [
            "independent blinded external validation",
            "BioNexus cell-type assignment",
            "fine-grained subtype validity",
            "cross-tissue transfer",
            "clinical validity",
            "certification promotion without cross-host execution and external review",
        ],
        "external_holdout": {
            "path": "data/flagship/kang2018_pbmc_ifnb/pbmc_ifnb_counts.h5ad",
            "sha256": DATASET_SHA256,
            "n_cells": 13487,
            "n_genes": 14053,
            "n_donors": 8,
            "reference_labels": "geo_cell_type (published Kang et al. 2017 GEO/Seurat assignments, "
            "corroborated by the committed GSE96583_batch2.total.tsne.df.tsv.gz supplementary)",
            "source_citation": "Kang et al. 2017, Nat Biotechnol 35:404-406, GSE96583 (GPL24676)",
        },
        "donor_split": {
            "rule": "sorted donor identifiers, first half development, second half holdout",
            "development_donors": DEVELOPMENT_DONORS,
            "holdout_donors": HOLDOUT_DONORS,
            "holdout_labels_accessed_before_lock": False,
        },
        "rna_candidate_rule": {
            "matrix_source": "adata.X (verified finite non-negative integer raw counts)",
            "normalization": "per-cell raw counts per 10000 followed by log1p",
            "label": "highest mean expression across the panel-intersected lineage modules",
            "marker_modules_reference": {k: list(v) for k, v in RNA_MARKERS.items()},
            "panel_intersected_marker_modules": frozen_modules,
            "markers_dropped_by_panel_audit": dropped,
            "minimum_module_size_rule": "every intersected module retains >= 2 markers; otherwise the study design must change",
            "confidence_score": "top module mean minus runner-up module mean",
            "external_label_mapping": EXTERNAL_LABEL_MAPPING,
            "excluded_labels": EXCLUDED_LABELS,
            "mapping_notes": (
                "Dendritic cells map to the coarse MONOCYTE family (shared myeloid module markers); "
                "this is the conservative direction. Megakaryocytes have no preregistered module and "
                "are excluded and enumerated."
            ),
        },
        "threshold_selection_protocol": {
            "grid": {"start": 0.0, "stop": 3.0, "step": 0.05},
            "eligibility": "development-donor pooled accepted-precision Wilson lower 95 >= 0.9 AND development coverage in [0.1, 0.8]",
            "selection": "eligible threshold with maximum development coverage; ties broken toward the smaller margin",
            "no_eligible_threshold_outcome": "NOT_EVALUATED_NO_ELIGIBLE_THRESHOLD (negative result retained)",
        },
        "locked_candidate_threshold": None,
        "locked_external_endpoints": {
            "minimum_mapped_holdout_cells": 1000,
            "accepted_precision_wilson_lower_95_min": 0.9,
            "accuracy_improvement_min": 0.03,
            "coverage_min": 0.1,
            "coverage_max": 0.8,
            "accepted_lineages_min": 3,
            "accepted_cells_per_lineage_min": 20,
            "donor_direction_consistency_min_donors": 3,
            "per_donor_accuracy_improvement_min": 0.0,
        },
        "governance": {
            "successful_result_maximum_status": "CANDIDATE_EXTERNAL_REFERENCE_DONOR_HELD_OUT",
            "independent_ground_truth": False,
            "independent_ground_truth_reason": (
                "Published GEO/Seurat assignments are external reference labels, not an independent "
                "experimental truth standard; same-implementer blinding is partial by construction."
            ),
            "negative_results_retained": True,
        },
    }
    _write_json(PREREGISTRATION, payload)
    print(f"[OK] preregistration written: {PREREGISTRATION}")
    return 0


def phase_dev() -> int:
    prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    if prereg.get("locked_candidate_threshold") is not None:
        print("[SKIP] threshold already locked; refusing to re-run the development phase.")
        return 1
    adata, donors, labels = load_cohort()
    frozen = prereg["rna_candidate_rule"]["panel_intersected_marker_modules"]
    candidates, margins = score_cells(adata, frozen)
    mapped, label_counts = map_labels(labels)

    grid_rows: List[Dict[str, Any]] = []
    for threshold in THRESHOLD_GRID:
        res = evaluate_at_threshold(candidates, margins, mapped, donors, threshold, DEVELOPMENT_DONORS)
        grid_rows.append(
            {
                "threshold": threshold,
                "mapped_cells": res["mapped_cells"],
                "accepted_cells": res["accepted_cells"],
                "accepted_precision": round(res["accepted_precision"], 6),
                "accepted_precision_wilson_lower_95": round(res["accepted_precision_wilson_lower_95"], 6),
                "coverage": round(res["coverage"], 6),
                "eligible": bool(
                    res["accepted_precision_wilson_lower_95"] >= DEV_WILSON_LOWER_MIN
                    and DEV_COVERAGE_RANGE[0] <= res["coverage"] <= DEV_COVERAGE_RANGE[1]
                ),
            }
        )
    eligible = [row for row in grid_rows if row["eligible"]]
    selected = None
    if eligible:
        best = max(row["coverage"] for row in eligible)
        selected = min(
            (row for row in eligible if abs(row["coverage"] - best) < 1e-12),
            key=lambda row: row["threshold"],
        )

    dev_selection = {
        "study_id": STUDY_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "development_donors": DEVELOPMENT_DONORS,
        "grid_rows": grid_rows,
        "eligible_thresholds": [row["threshold"] for row in eligible],
        "selected_threshold": selected["threshold"] if selected else None,
        "no_eligible_threshold": selected is None,
    }
    _write_json(STUDY_ROOT / "dev_selection.json", dev_selection)

    if selected is None:
        prereg["locked_candidate_threshold"] = {
            "selected": False,
            "outcome": "NOT_EVALUATED_NO_ELIGIBLE_THRESHOLD",
            "note": "No grid threshold met the preregistered development eligibility rule.",
        }
        prereg["locked_at"] = datetime.now(timezone.utc).isoformat()
        prereg["study_status_at_lock"] = "PREREGISTERED_AFTER_DEV_PHASE_NO_ELIGIBLE_THRESHOLD"
        _write_json(PREREGISTRATION, prereg)
        PREREGISTRATION_LOCK.write_text(
            json.dumps(
                {
                    "schema_version": "bionexus.preregistration-lock.v1",
                    "study_id": STUDY_ID,
                    "locked_path": "validation/annotation/studies/BN-ANN-IV-004/PREREGISTRATION.json",
                    "sha256": sha256_file(PREREGISTRATION),
                    "locked_at": prereg["locked_at"],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("[OK] no eligible threshold on development donors; negative result locked.")
        return 0

    dev_metrics = evaluate_at_threshold(
        candidates, margins, mapped, donors, selected["threshold"], DEVELOPMENT_DONORS
    )
    prereg["locked_candidate_threshold"] = {
        "rna_margin_min": selected["threshold"],
        "selected_on": "development donors only (101, 107, 1015, 1016) of GSE96583; holdout labels not consulted",
        "development_coverage": dev_metrics["coverage"],
        "development_precision": dev_metrics["accepted_precision"],
        "development_precision_wilson_lower_95": dev_metrics["accepted_precision_wilson_lower_95"],
        "development_accuracy_improvement": dev_metrics["accuracy_improvement"],
        "changed_from_BN_ANN_IV_001_rule": False,
    }
    prereg["locked_at"] = datetime.now(timezone.utc).isoformat()
    prereg["study_status_at_lock"] = "PREREGISTERED_AFTER_DEV_PHASE_BEFORE_HOLDOUT_EXECUTION"
    _write_json(PREREGISTRATION, prereg)
    lock = {
        "schema_version": "bionexus.preregistration-lock.v1",
        "study_id": STUDY_ID,
        "locked_path": "validation/annotation/studies/BN-ANN-IV-004/PREREGISTRATION.json",
        "sha256": sha256_file(PREREGISTRATION),
        "locked_at": prereg["locked_at"],
    }
    _write_json(PREREGISTRATION_LOCK, lock)
    print(f"[OK] threshold {selected['threshold']} locked; dev coverage {dev_metrics['coverage']:.4f}, "
          f"dev precision {dev_metrics['accepted_precision']:.4f} "
          f"(Wilson lower {dev_metrics['accepted_precision_wilson_lower_95']:.4f})")
    return 0


def phase_holdout() -> int:
    lock = _verify_lock()
    prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    locked = prereg.get("locked_candidate_threshold") or {}
    if locked.get("rna_margin_min") is None:
        outcome = {
            "schema_version": "bionexus.annotation-donor-holdout-report.v1",
            "study_id": STUDY_ID,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": locked.get("outcome", "NOT_EVALUATED_NO_ELIGIBLE_THRESHOLD"),
            "note": "Holdout endpoints were not evaluated: the development phase produced no eligible threshold.",
        }
        _write_json(STUDY_ROOT / "REPORT.json", outcome)
        print("[OK] negative result retained (no eligible threshold).")
        return 0

    threshold = float(locked["rna_margin_min"])
    adata, donors, labels = load_cohort()
    frozen = prereg["rna_candidate_rule"]["panel_intersected_marker_modules"]
    candidates, margins = score_cells(adata, frozen)
    mapped, label_counts = map_labels(labels)

    keep = np.isin(np.asarray(donors, dtype=object), np.asarray(HOLDOUT_DONORS, dtype=object))
    res = evaluate_at_threshold(candidates, margins, mapped, donors, threshold, HOLDOUT_DONORS)

    endpoints = prereg["locked_external_endpoints"]
    per_donor_improvements = {
        d: m["accuracy_improvement"] for d, m in res["by_donor"].items()
    }
    direction_consistent = sum(1 for v in per_donor_improvements.values() if v >= endpoints["per_donor_accuracy_improvement_min"])
    observed = {
        "mapped_holdout_cells": res["mapped_cells"],
        "accepted_precision_wilson_lower_95": res["accepted_precision_wilson_lower_95"],
        "accuracy_improvement": res["accuracy_improvement"],
        "coverage": res["coverage"],
        "accepted_lineages": res["accepted_lineages"],
        "minimum_cells_per_accepted_lineage": min(res["accepted_by_external_lineage"].values()) if res["accepted_by_external_lineage"] else 0,
        "donor_direction_consistent_donors": direction_consistent,
    }
    checks = {
        "mapped_holdout_cells": observed["mapped_holdout_cells"] >= endpoints["minimum_mapped_holdout_cells"],
        "accepted_precision_wilson_lower_95": observed["accepted_precision_wilson_lower_95"] >= endpoints["accepted_precision_wilson_lower_95_min"],
        "accuracy_improvement": observed["accuracy_improvement"] >= endpoints["accuracy_improvement_min"],
        "coverage_range": endpoints["coverage_min"] <= observed["coverage"] <= endpoints["coverage_max"],
        "accepted_lineages": observed["accepted_lineages"] >= endpoints["accepted_lineages_min"],
        "donor_direction_consistency": direction_consistent >= endpoints["donor_direction_consistency_min_donors"],
    }
    all_passed = all(checks.values())
    status = "CANDIDATE_EXTERNAL_REFERENCE_DONOR_HELD_OUT" if all_passed else "ENDPOINTS_NOT_MET_NEGATIVE_RESULT_RETAINED"

    evidence_dir = STUDY_ROOT / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "holdout_cell_decisions.csv.gz"
    donor_arr = np.asarray(donors, dtype=object)
    with gzip.open(evidence_path, "wt", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["cell_id", "donor", "phase", "candidate_lineage", "margin", "accepted",
                         "external_label", "mapped_lineage", "candidate_correct"])
        index = adata.obs_names
        for i in range(len(donors)):
            if not keep[i]:
                continue
            writer.writerow([
                str(index[i]), donor_arr[i], "holdout", str(candidates[i]), f"{margins[i]:.6f}",
                str(bool(margins[i] >= threshold)).lower(), str(labels[i]), str(mapped[i]),
                str(bool(mapped[i] == candidates[i])).lower(),
            ])

    endpoint_keys = [k for k in checks if k != "coverage_range"]
    threshold_key_map = {
        "mapped_holdout_cells": "minimum_mapped_holdout_cells",
        "accepted_precision_wilson_lower_95": "accepted_precision_wilson_lower_95_min",
        "accuracy_improvement": "accuracy_improvement_min",
        "accepted_lineages": "accepted_lineages_min",
        "donor_direction_consistency": "donor_direction_consistency_min_donors",
        "minimum_cells_per_accepted_lineage": "accepted_cells_per_lineage_min",
    }
    primary_endpoints = {
        key: {
            "observed": observed[key],
            "threshold": endpoints.get(threshold_key_map[key]),
            "passed": checks[key],
        }
        for key in endpoint_keys
        if key in observed
    }
    primary_endpoints["coverage_range"] = {
        "observed": observed["coverage"],
        "threshold": [endpoints["coverage_min"], endpoints["coverage_max"]],
        "passed": checks["coverage_range"],
    }
    report = {
        "schema_version": "bionexus.annotation-donor-holdout-report.v1",
        "study_id": STUDY_ID,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preregistration": {
            "sha256": sha256_file(PREREGISTRATION),
            "locked_at": prereg["locked_at"],
            "study_status_at_lock": prereg["study_status_at_lock"],
            "claim_target": prereg["claim_target"],
            "claim_exclusions": prereg["claim_exclusions"],
        },
        "dataset": {
            "path": str(DATASET.relative_to(REPO_ROOT)).replace("\\", "/"),
            "sha256": DATASET_SHA256,
            "n_cells": int(adata.n_obs),
            "n_genes": int(adata.n_vars),
            "reference_labels": prereg["external_holdout"]["reference_labels"],
            "source_citation": prereg["external_holdout"]["source_citation"],
        },
        "input_contract": {
            "raw_nonnegative_integer_counts_verified": True,
            "zero_library_cells": 0,
            "matrix_source": prereg["rna_candidate_rule"]["matrix_source"],
        },
        "access_disclosure": prereg["access_disclosure"],
        "locked_gate": {
            "rna_margin_min": threshold,
            "selected_on": locked.get("selected_on"),
            "development_coverage": locked.get("development_coverage"),
            "development_precision": locked.get("development_precision"),
            "development_precision_wilson_lower_95": locked.get("development_precision_wilson_lower_95"),
            "development_accuracy_improvement": locked.get("development_accuracy_improvement"),
        },
        "holdout": {
            "donors": HOLDOUT_DONORS,
            "mapped_cells": res["mapped_cells"],
            "unmapped_cells": sum(v for k, v in label_counts.items() if EXTERNAL_LABEL_MAPPING.get(k) is None),
            "original_label_counts": dict(sorted(label_counts.items())),
            "mapped_lineage_counts": {
                lineage: int((mapped[keep] == lineage).sum())
                for lineage in LINEAGES
            },
            "accepted_cells": res["accepted_cells"],
            "accepted_by_external_lineage": res["accepted_by_external_lineage"],
            "ungated_accuracy": res["ungated_accuracy"],
            "accepted_precision": res["accepted_precision"],
            "accepted_precision_wilson_95": [
                res["accepted_precision_wilson_lower_95"], res["accepted_precision_wilson_upper_95"]
            ],
            "coverage": res["coverage"],
            "per_donor_accuracy_improvement": per_donor_improvements,
        },
        "primary_endpoints": primary_endpoints,
        "coverage_range": {"observed": observed["coverage"], "minimum": endpoints["coverage_min"],
                           "maximum": endpoints["coverage_max"], "passed": checks["coverage_range"]},
        "status": status,
        "claim_boundary": (
            "Donor-held-out candidate external-reference evidence on one published PBMC cohort. "
            "It does not establish independent blinded validation, cross-host conformance, external "
            "reviewer sign-off, or certification promotion."
        ),
        "markers_used": {
            "panel_intersected_marker_modules": prereg["rna_candidate_rule"]["panel_intersected_marker_modules"],
            "markers_dropped_by_panel_audit": prereg["rna_candidate_rule"]["markers_dropped_by_panel_audit"],
        },
        "evidence_files": ["evidence/holdout_cell_decisions.csv.gz"],
        "provenance": bind_validation_source_provenance(
            capture_execution_provenance(
                data_source=prereg["external_holdout"]["source_citation"],
                repo_root=REPO_ROOT,
                generator_version=VERSION,
                extra_metadata={"study_id": STUDY_ID, "phase": "holdout", "lock_sha256": lock["sha256"]},
            ),
            REPO_ROOT,
        ),
    }
    _write_json(STUDY_ROOT / "REPORT.json", report)
    print(f"[OK] status={status}")
    for key, block in primary_endpoints.items():
        print(f"     {'PASS' if block['passed'] else 'FAIL'}  {key}: observed={block['observed']}")
    return 0 if all_passed else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="BN-ANN-IV-004 donor-held-out annotation study")
    parser.add_argument("--phase", required=True, choices=["init", "dev", "holdout"])
    args = parser.parse_args()
    return {"init": phase_init, "dev": phase_dev, "holdout": phase_holdout}[args.phase]()


if __name__ == "__main__":
    sys.exit(main())
