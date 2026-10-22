"""Descriptive RNA annotation agreement and calibration against supplied labels.

Legacy FACS names do not authenticate physical sorting or blinding. A label hash
only tests integrity. These calculations cannot promote scientific maturity.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass, field
from statistics import NormalDist
from typing import Any, Dict, List, Mapping, Optional, Sequence

import numpy as np


@dataclass(frozen=True)
class CalibrationMetrics:
    """Rigorous probabilistic calibration metrics for cell annotation confidence."""

    n_samples: int
    n_bins: int
    expected_calibration_error: float  # ECE
    maximum_calibration_error: float   # MCE
    brier_score: float
    is_well_calibrated: Optional[bool]          # ECE <= 0.08
    bin_accuracies: List[float] = field(default_factory=list)
    bin_confidences: List[float] = field(default_factory=list)
    bin_counts: List[int] = field(default_factory=list)
    calibration_status: str = "DESCRIPTIVE_IN_SAMPLE_ONLY"
    ece_below_threshold: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SelectiveAbstentionPoint:
    """Performance metrics at a specific abstention / warrant ceiling."""

    warrant_tier: str
    n_accepted: int
    n_abstained: int
    coverage_fraction: Optional[float]
    accuracy_on_accepted: Optional[float]
    wilson_lower_95: Optional[float]
    abstention_effective: Optional[bool]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FACSGroundTruthAuditResult:
    """Benchmark evaluation on physical flow-cytometry sorted cell populations."""

    dataset_name: str
    n_total_cells: int
    physical_cell_types: List[str]
    overall_accuracy: float
    supported_tier_precision: Optional[float]
    calibration: CalibrationMetrics
    selective_abstention: List[SelectiveAbstentionPoint]
    blinding_verified: bool
    positive_candidate_promoted: bool  # Can now promote to VALIDATED_BIOLOGICAL_TRUTH
    claim_boundary_summary: str
    reference_hash_matches: bool = False
    evidence_kind: str = "CALLER_SUPPLIED_REFERENCE_LABELS"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "n_total_cells": self.n_total_cells,
            "physical_cell_types": self.physical_cell_types,
            "overall_accuracy": self.overall_accuracy,
            "supported_tier_precision": self.supported_tier_precision,
            "calibration": self.calibration.to_dict(),
            "selective_abstention": [p.to_dict() for p in self.selective_abstention],
            "blinding_verified": self.blinding_verified,
            "positive_candidate_promoted": self.positive_candidate_promoted,
            "claim_boundary_summary": self.claim_boundary_summary,
            "reference_hash_matches": self.reference_hash_matches,
            "evidence_kind": self.evidence_kind,
            "scientific_authorization": "NONE",
        }


def compute_wilson_lower_bound(k: int, n: int, confidence: float = .95) -> Optional[float]:
    """Cell-level descriptive interval; not a donor/cluster-adjusted interval."""
    if not isinstance(k, int) or not isinstance(n, int) or n < 0 or k < 0 or k > n or not 0 < confidence < 1:
        raise ValueError("invalid binomial counts or confidence level")
    if n == 0:
        return None
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    p = k / n
    return max(0.0, (p + z*z/(2*n) - z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))) / (1 + z*z/n))


def compute_calibration_metrics(
    *,
    probabilities: np.ndarray,
    ground_truth_indices: np.ndarray,
    n_bins: int = 10,
) -> CalibrationMetrics:
    """
    Compute Expected Calibration Error (ECE), Maximum Calibration Error (MCE), and Brier Score.

    Parameters:
        probabilities: (N, K) array of predicted class probabilities.
        ground_truth_indices: (N,) array of true class integer indices in [0, K-1].
        n_bins: Number of equal-width bins for confidence partitioning.
    """
    probabilities = np.asarray(probabilities, dtype=float)
    ground_truth_indices = np.asarray(ground_truth_indices)
    if probabilities.ndim != 2 or probabilities.shape[1] < 2:
        raise ValueError("probabilities must have shape (N, K) with at least two classes")
    if len(probabilities) == 0:
        raise ValueError("probabilities array cannot be empty")
    if not isinstance(n_bins, int) or n_bins < 1:
        raise ValueError("n_bins must be a positive integer")
    if (not np.all(np.isfinite(probabilities)) or np.any((probabilities < 0) | (probabilities > 1))
            or not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-8, rtol=0)):
        raise ValueError("probabilities must be finite, within [0, 1], and sum to one")
    if (ground_truth_indices.shape != (len(probabilities),) or
            not np.issubdtype(ground_truth_indices.dtype, np.integer) or
            np.any((ground_truth_indices < 0) | (ground_truth_indices >= probabilities.shape[1]))):
        raise ValueError("reference indices must align and identify a known class")

    n_samples = probabilities.shape[0]
    n_classes = probabilities.shape[1]

    confidences = np.max(probabilities, axis=1)
    predictions = np.argmax(probabilities, axis=1)
    accuracies = (predictions == ground_truth_indices).astype(np.float64)

    # Multi-class Brier score: 1/N * sum_{i} sum_{k} (p_{ik} - y_{ik})^2
    one_hot = np.zeros((n_samples, n_classes), dtype=np.float64)
    for i, true_idx in enumerate(ground_truth_indices):
        if 0 <= true_idx < n_classes:
            one_hot[i, true_idx] = 1.0
    brier = float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))

    bin_boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    mce = 0.0

    bin_accs: List[float] = []
    bin_confs: List[float] = []
    bin_counts: List[int] = []

    for bin_idx in range(n_bins):
        bin_lower = bin_boundaries[bin_idx]
        bin_upper = bin_boundaries[bin_idx + 1]

        if bin_idx == n_bins - 1:
            in_bin = (confidences >= bin_lower) & (confidences <= bin_upper)
        else:
            in_bin = (confidences >= bin_lower) & (confidences < bin_upper)

        count = int(np.sum(in_bin))
        bin_counts.append(count)

        if count > 0:
            bin_acc = float(np.mean(accuracies[in_bin]))
            bin_conf = float(np.mean(confidences[in_bin]))
            diff = abs(bin_acc - bin_conf)
            ece += (count / n_samples) * diff
            mce = max(mce, diff)
            bin_accs.append(bin_acc)
            bin_confs.append(bin_conf)
        else:
            bin_accs.append(0.0)
            bin_confs.append(0.0)

    ece_below_threshold = (ece <= 0.08)

    return CalibrationMetrics(
        n_samples=n_samples,
        n_bins=n_bins,
        expected_calibration_error=float(ece),
        maximum_calibration_error=float(mce),
        brier_score=float(brier),
        is_well_calibrated=None,
        ece_below_threshold=ece_below_threshold,
        bin_accuracies=bin_accs,
        bin_confidences=bin_confs,
        bin_counts=bin_counts,
    )


def evaluate_selective_abstention_curve(
    *,
    warrant_verdicts: Sequence[str],  # "SUPPORTED", "TENTATIVE", "ABSTAIN"
    predictions: Sequence[str],
    ground_truth_labels: Sequence[str],
) -> List[SelectiveAbstentionPoint]:
    """
    Evaluate selective prediction: verify that as criteria tighten, accuracy rises to >= 95%.
    """
    if len(warrant_verdicts) != len(predictions) or len(predictions) != len(ground_truth_labels):
        raise ValueError("Inputs must have identical lengths")

    if any(v not in {"SUPPORTED", "TENTATIVE", "ABSTAIN"} for v in warrant_verdicts):
        raise ValueError("unrecognized warrant verdict")
    n_total = len(predictions)
    tiers = [
        ("ALL_CALLS", {"SUPPORTED", "TENTATIVE", "ABSTAIN"}),
        ("NON_ABSTAIN", {"SUPPORTED", "TENTATIVE"}),
        ("SUPPORTED_ONLY", {"SUPPORTED"}),
    ]

    points: List[SelectiveAbstentionPoint] = []
    for tier_name, allowed_verdicts in tiers:
        accepted_indices = [i for i, v in enumerate(warrant_verdicts) if v in allowed_verdicts]
        n_accepted = len(accepted_indices)
        n_abstained = n_total - n_accepted
        coverage = n_accepted / n_total if n_total > 0 else None

        if n_accepted > 0:
            correct = sum(1 for i in accepted_indices if predictions[i] == ground_truth_labels[i])
            acc = float(correct / n_accepted)
            wilson_low = compute_wilson_lower_bound(correct, n_accepted)
        else:
            acc = None
            wilson_low = None

        effective = (acc >= .95 and wilson_low >= .90) if acc is not None and tier_name == "SUPPORTED_ONLY" else None

        points.append(
            SelectiveAbstentionPoint(
                warrant_tier=tier_name,
                n_accepted=n_accepted,
                n_abstained=n_abstained,
                coverage_fraction=coverage,
                accuracy_on_accepted=acc,
                wilson_lower_95=wilson_low,
                abstention_effective=effective,
            )
        )

    return points


def evaluate_facs_physical_ground_truth_benchmark(
    *,
    dataset_name: str,
    raw_counts_matrix: np.ndarray,
    gene_names: Sequence[str],
    physical_ground_truth: Sequence[str],
    marker_modules: Mapping[str, Sequence[str]],
    blinded_key_hash: str,
    confidence_margin_threshold: float = 0.70,
    temperature: float = 0.40,
) -> FACSGroundTruthAuditResult:
    """
    Compute descriptive agreement against supplied reference labels.

    RNA scores do not use the reference labels. The shared process and a matching
    hash do not establish a blinded protocol or independent experimental truth.
    """
    raw_counts_matrix = np.asarray(raw_counts_matrix, dtype=float)
    if raw_counts_matrix.ndim != 2 or raw_counts_matrix.shape != (len(physical_ground_truth), len(gene_names)) or not len(physical_ground_truth):
        raise ValueError("nonempty counts, gene names, and reference labels must align")
    if not np.all(np.isfinite(raw_counts_matrix)) or np.any(raw_counts_matrix < 0):
        raise ValueError("counts must be finite and nonnegative")
    if len(set(gene_names)) != len(gene_names):
        raise ValueError("gene names must be unique")
    if len(marker_modules) < 2 or any(not set(markers) & set(gene_names) for markers in marker_modules.values()):
        raise ValueError("at least two marker modules with observed genes are required")
    if any(label not in marker_modules for label in physical_ground_truth):
        raise ValueError("reference labels must identify a known marker module")
    if not math.isfinite(temperature) or temperature <= 0 or not math.isfinite(confidence_margin_threshold) or confidence_margin_threshold < .20:
        raise ValueError("invalid temperature or margin threshold")
    observed_key_hash = hashlib.sha256(",".join(physical_ground_truth).encode("utf-8")).hexdigest()
    reference_hash_matches = (blinded_key_hash == observed_key_hash)
    # Labels are passed to this function. Hash equality cannot prove blinding.
    blinding_verified = False

    # Marker index mapping
    gene_to_idx = {g: i for i, g in enumerate(gene_names)}
    lineages = sorted(marker_modules.keys())
    lineage_to_idx = {lin: i for i, lin in enumerate(lineages)}

    n_cells = raw_counts_matrix.shape[0]
    scores = np.zeros((n_cells, len(lineages)), dtype=np.float64)

    # Per-cell library normalization and module scoring
    totals = np.maximum(np.asarray(raw_counts_matrix.sum(axis=1)).ravel(), 1.0)
    for lin_idx, lin in enumerate(lineages):
        present_genes = [gene_to_idx[g] for g in marker_modules[lin] if g in gene_to_idx]
        if present_genes:
            raw_sub = raw_counts_matrix[:, present_genes]
            cpm = np.asarray(raw_sub / totals[:, None] * 10000.0)
            scores[:, lin_idx] = np.mean(np.log1p(cpm), axis=1)

    # Temperature-scaled softmax probabilities for probabilistic calibration
    scaled_scores = scores / max(1e-6, temperature)
    exp_scores = np.exp(scaled_scores - np.max(scaled_scores, axis=1, keepdims=True))
    probs = exp_scores / np.sum(exp_scores, axis=1, keepdims=True)

    # Margins and top predictions
    order = np.argsort(scores, axis=1)
    top_indices = order[:, -1]
    runner_up_indices = order[:, -2] if scores.shape[1] > 1 else order[:, -1]

    margins = scores[np.arange(n_cells), top_indices] - scores[np.arange(n_cells), runner_up_indices]
    predicted_labels = [lineages[idx] for idx in top_indices]

    # Assign formal BioNexus warrant verdicts
    verdicts: List[str] = []
    for i in range(n_cells):
        if margins[i] >= confidence_margin_threshold:
            verdicts.append("SUPPORTED")
        elif margins[i] >= 0.20:
            verdicts.append("TENTATIVE")
        else:
            verdicts.append("ABSTAIN")

    # True class indices
    gt_indices = np.asarray(
        [lineage_to_idx.get(lbl, -1) for lbl in physical_ground_truth], dtype=int
    )

    # Compute calibration metrics
    calibration = compute_calibration_metrics(
        probabilities=probs,
        ground_truth_indices=gt_indices,
        n_bins=10,
    )

    # Compute selective prediction and abstention
    selective_points = evaluate_selective_abstention_curve(
        warrant_verdicts=verdicts,
        predictions=predicted_labels,
        ground_truth_labels=physical_ground_truth,
    )

    supported_point = next(p for p in selective_points if p.warrant_tier == "SUPPORTED_ONLY")
    overall_point = next(p for p in selective_points if p.warrant_tier == "ALL_CALLS")

    promoted = False
    summary = (
        f"Descriptive RNA marker agreement on {n_cells} cells against caller-supplied labels. "
        "Reference-label integrity does not establish blinded assessment, independent physical truth, "
        "out-of-sample calibration, or scientific authorization."
    )

    return FACSGroundTruthAuditResult(
        dataset_name=dataset_name,
        n_total_cells=n_cells,
        physical_cell_types=lineages,
        overall_accuracy=overall_point.accuracy_on_accepted,
        supported_tier_precision=supported_point.accuracy_on_accepted,
        calibration=calibration,
        selective_abstention=selective_points,
        blinding_verified=blinding_verified,
        positive_candidate_promoted=promoted,
        claim_boundary_summary=summary,
        reference_hash_matches=reference_hash_matches,
    )
