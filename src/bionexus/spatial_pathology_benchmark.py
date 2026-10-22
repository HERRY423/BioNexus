"""Spatial label overlap and explicit pending artifact-control assessments.

These utilities cannot authenticate pathology labels or infer that a spatial
correlation is biological. No control experiment is fabricated by this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np


@dataclass(frozen=True)
class PathologicalDomainMetric:
    """Morphological concordance between spatial inference and pathologist ground truth."""

    domain_name: str
    n_ground_truth_cells: int
    n_inferred_cells: int
    dice_coefficient: float
    jaccard_index: float
    boundary_precision: Optional[float]
    domain_validated: bool
    label_precision: Optional[float] = None
    overlap_threshold_met: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactDiscriminationResult:
    """Ability to differentiate genuine spatial biology from technical confounders."""

    test_name: str
    is_true_biology: Optional[bool]
    raw_spatial_statistic: Optional[float]
    post_control_statistic: Optional[float]
    system_verdict: str  # "CONTROLLED_VALID_BIOLOGY", "REJECTED_AS_TECHNICAL_ARTIFACT"
    correctly_discriminated: Optional[bool]
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SpatialPathologyValidationResult:
    """Comprehensive biological validity assessment against clinical pathology ground truth."""

    cohort_name: str
    tissue_type: str
    n_total_cells: int
    mean_dice_coefficient: Optional[float]
    domain_metrics: List[PathologicalDomainMetric]
    discrimination_tests: List[ArtifactDiscriminationResult]
    pathology_concordance_pass: bool
    artifact_discrimination_pass: bool
    biological_validity_promoted: bool
    claim_boundary_summary: str
    reference_concordance_threshold_met: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cohort_name": self.cohort_name,
            "tissue_type": self.tissue_type,
            "n_total_cells": self.n_total_cells,
            "mean_dice_coefficient": self.mean_dice_coefficient,
            "domain_metrics": [m.to_dict() for m in self.domain_metrics],
            "discrimination_tests": [t.to_dict() for t in self.discrimination_tests],
            "pathology_concordance_pass": self.pathology_concordance_pass,
            "artifact_discrimination_pass": self.artifact_discrimination_pass,
            "biological_validity_promoted": self.biological_validity_promoted,
            "claim_boundary_summary": self.claim_boundary_summary,
            "reference_concordance_threshold_met": self.reference_concordance_threshold_met,
            "evidence_kind": "UNVERIFIED_REFERENCE_LABEL_COMPARISON",
            "scientific_authorization": "NONE",
        }


def compute_dice_and_jaccard(
    mask_true: np.ndarray, mask_pred: np.ndarray,
) -> Tuple[Optional[float], Optional[float]]:
    """Return overlap measures; two empty masks have no estimable denominator."""
    truth, pred = np.asarray(mask_true), np.asarray(mask_pred)
    if truth.shape != pred.shape or truth.ndim != 1 or truth.dtype != bool or pred.dtype != bool:
        raise ValueError("masks must be aligned one-dimensional boolean arrays")
    intersection = int(np.sum(truth & pred))
    total = int(np.sum(truth)) + int(np.sum(pred))
    if not total:
        return None, None
    return 2 * intersection / total, intersection / (total - intersection)


def evaluate_pathology_domain_concordance(
    *, inferred_domain_labels: Sequence[str], pathologist_ground_truth: Sequence[str],
    min_dice_threshold: float = .70,
) -> List[PathologicalDomainMetric]:
    """Compare supplied labels, including domains present only in predictions."""
    inferred, reference = np.asarray(inferred_domain_labels), np.asarray(pathologist_ground_truth)
    if inferred.ndim != 1 or reference.ndim != 1 or inferred.shape != reference.shape:
        raise ValueError("inferred and reference labels must align")
    if not 0 <= min_dice_threshold <= 1:
        raise ValueError("min_dice_threshold must be in [0, 1]")
    if any(not isinstance(v, (str, np.str_)) or not v for v in list(inferred) + list(reference)):
        raise ValueError("domain labels must be nonempty strings")
    metrics = []
    for domain in sorted(set(reference) | set(inferred)):
        truth, pred = reference == domain, inferred == domain
        dice, jaccard = compute_dice_and_jaccard(truth, pred)
        n_true, n_pred = int(np.sum(truth)), int(np.sum(pred))
        metrics.append(PathologicalDomainMetric(
            domain_name=str(domain), n_ground_truth_cells=n_true, n_inferred_cells=n_pred,
            dice_coefficient=dice, jaccard_index=jaccard, boundary_precision=None,
            domain_validated=False,  # Label arrays carry no verified pathology provenance.
            label_precision=int(np.sum(truth & pred)) / n_pred if n_pred else None,
            overlap_threshold_met=bool(dice is not None and dice >= min_dice_threshold),
        ))
    return metrics


def evaluate_spatial_biological_vs_artifact_discrimination(
    *, coords: np.ndarray, expression_matrix: np.ndarray, gene_names: Sequence[str],
    pathologist_domains: Sequence[str], fov_ids: Optional[Sequence[str]] = None,
) -> List[ArtifactDiscriminationResult]:
    """Return missing-control assessments; raw arrays cannot supply control outcomes.

    Required future evidence includes independently executed perturbation/control
    outputs, predeclared statistics, and independently supplied reference outcomes.
    """
    coords, expression = np.asarray(coords), np.asarray(expression_matrix)
    if coords.ndim != 2 or coords.shape[1] not in (2, 3) or expression.ndim != 2:
        raise ValueError("coordinates and expression must be two-dimensional arrays")
    if expression.shape != (len(coords), len(gene_names)) or len(pathologist_domains) != len(coords):
        raise ValueError("coordinates, expression, genes and domain labels must align")
    if not np.all(np.isfinite(coords)) or not np.all(np.isfinite(expression)) or np.any(expression < 0):
        raise ValueError("coordinates and expression must be finite, with nonnegative expression")
    if len(set(gene_names)) != len(gene_names) or (fov_ids is not None and len(fov_ids) != len(coords)):
        raise ValueError("genes must be unique and FOV identifiers must align")
    names = ["tumor_stroma_interface_chemokine_interaction", "optical_diffusion_segmentation_leakage",
             "cell_density_crowding_confounding", "fov_tile_edge_stitching_artifact"]
    return [ArtifactDiscriminationResult(
        test_name=name, is_true_biology=None, raw_spatial_statistic=None,
        post_control_statistic=None, system_verdict="NOT_EVALUATED",
        correctly_discriminated=None,
        notes="No executed control comparison or independently established biological/artifact label is supplied.",
    ) for name in names]


def run_spatial_pathology_validation_suite(
    *, cohort_name: str, tissue_type: str, coords: np.ndarray,
    inferred_domains: Sequence[str], pathologist_ground_truth: Sequence[str],
    expression_matrix: np.ndarray, gene_names: Sequence[str],
) -> SpatialPathologyValidationResult:
    """Describe supplied-label overlap without independent-truth promotion."""
    domains = evaluate_pathology_domain_concordance(
        inferred_domain_labels=inferred_domains, pathologist_ground_truth=pathologist_ground_truth,
    )
    controls = evaluate_spatial_biological_vs_artifact_discrimination(
        coords=coords, expression_matrix=expression_matrix, gene_names=gene_names,
        pathologist_domains=pathologist_ground_truth,
    )
    mean_dice = float(np.mean([m.dice_coefficient for m in domains])) if domains else None
    threshold_met = bool(domains and mean_dice >= .75 and all(m.dice_coefficient >= .65 for m in domains))
    return SpatialPathologyValidationResult(
        cohort_name=cohort_name, tissue_type=tissue_type, n_total_cells=len(coords),
        mean_dice_coefficient=mean_dice, domain_metrics=domains, discrimination_tests=controls,
        pathology_concordance_pass=False, artifact_discrimination_pass=False,
        biological_validity_promoted=False,
        reference_concordance_threshold_met=threshold_met,
        claim_boundary_summary="Descriptive supplied-label overlap only. Independent pathology truth and artifact discrimination remain unverified; no biological validity promotion.",
    )
