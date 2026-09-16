"""Executable Spatial Alternative Explanation Battery.

The battery deepens the existing ``spatial.inference_validity`` capability; it
is not a new omics capability and it does not run a generic spatial workflow.
For one declared spatial observation it asks whether the same effect survives
bounded perturbations of segmentation, leakage, morphology, density, contact
geometry, field/batch, neighborhood radius, coordinates, and cell labels.

Numeric pass/fail decisions are delegated to the empirical calibration layer.
Without a complete context and a runtime-verified Spatial Gold Program profile,
the battery still returns diagnostics but cannot promote them to controlled
evidence. A generic ``APPROVED`` flag is never sufficient. No physical
coordinates, contact graph, or segmentation variant is fabricated when absent.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np
from scipy import sparse
from scipy.spatial import cKDTree

from bionexus.empirical_warrant import (
    CalibrationContext,
    CalibrationRegistry,
    MetricAssessment,
    default_calibration_registry,
)
from bionexus.spatial_empirical_gold import (
    SPATIAL_CONTROL_METRICS,
    SPATIAL_GOLD_PLATFORMS,
    SPATIAL_GOLD_PROGRAM_VERSION,
    SpatialGoldRuntimeEvidence,
    is_spatial_gold_platform,
)
from bionexus.spatial_inference import ControlResult, SpatialInferenceVerdict, assess_spatial_inference


class SpatialBatteryError(ValueError):
    """Raised when a battery input violates a data-integrity contract."""


class SpatialClaimKind(str, Enum):
    """Spatial observation class evaluated by the battery."""

    CONTACT_EXPRESSION_ENRICHMENT = "CONTACT_EXPRESSION_ENRICHMENT"
    NEIGHBORHOOD_EXPRESSION_ENRICHMENT = "NEIGHBORHOOD_EXPRESSION_ENRICHMENT"
    LIGAND_RECEPTOR_INTERACTION = "LIGAND_RECEPTOR_INTERACTION"


class DiagnosticState(str, Enum):
    """Scientific state of one executable alternative-explanation test."""

    CONTROLLED = "CONTROLLED"
    FAILED = "FAILED"
    UNTESTED = "UNTESTED"


@dataclass(frozen=True)
class SpatialObservation:
    """One spatial claim whose effect is re-estimated under perturbations."""

    observation_id: str
    statement: str
    target_gene: str
    focal_cell_label: str
    neighbor_cell_label: str
    claim_kind: SpatialClaimKind = SpatialClaimKind.CONTACT_EXPRESSION_ENRICHMENT
    ligand_receptor_pair: Optional[Tuple[str, str]] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["claim_kind"] = self.claim_kind.value
        if self.ligand_receptor_pair is not None:
            data["ligand_receptor_pair"] = list(self.ligand_receptor_pair)
        return data


@dataclass
class SpatialBatteryData:
    """State-bound inputs for the alternative-explanation battery.

    ``contact_graph`` is an exact segmentation-derived cell-contact graph. Its
    non-zero weights may encode contact surface length/area. Radius graphs are
    derived separately from physical coordinates and never substituted for an
    exact contact graph when the claim is explicitly about contact.
    """

    expression: Any
    gene_names: Sequence[str]
    coordinates: Any
    cell_labels: Sequence[str]
    dataset_id: str
    state_revision_id: str
    segmentation_revision_id: str
    label_revision_id: str
    coordinate_system_id: str
    coordinate_unit: str
    expression_scale: str  # counts | log1p
    resolution: str = "cell"  # cell | spot
    contact_graph: Optional[Any] = None
    cell_size: Optional[Sequence[float]] = None
    nuclear_eccentricity: Optional[Sequence[float]] = None
    total_transcript_counts: Optional[Sequence[float]] = None
    fov_or_batch: Optional[Sequence[str]] = None
    segmentation_expression_variants: Mapping[str, Any] = field(default_factory=dict)
    segmentation_contact_variants: Mapping[str, Any] = field(default_factory=dict)
    leakage_expression_variants: Mapping[str, Any] = field(default_factory=dict)
    cell_label_variants: Mapping[str, Sequence[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class SpatialBatteryPlan:
    """Predeclared perturbation plan; values are not hidden engine defaults."""

    primary_radius: float
    radius_grid: Tuple[float, ...]
    assumed_leakage_fractions: Tuple[float, ...]
    label_flip_fraction: float
    label_perturbations: int
    coordinate_permutations: int
    random_seed: int
    minimum_group_cells: int
    max_graph_edges: int

    def __post_init__(self) -> None:
        if not math.isfinite(self.primary_radius) or self.primary_radius <= 0:
            raise SpatialBatteryError("primary_radius must be a positive finite physical distance")
        if not self.radius_grid or any(not math.isfinite(v) or v <= 0 for v in self.radius_grid):
            raise SpatialBatteryError("radius_grid must contain positive finite physical distances")
        if any(not math.isfinite(v) or not 0 <= v < 1 for v in self.assumed_leakage_fractions):
            raise SpatialBatteryError("assumed_leakage_fractions must be within [0, 1)")
        if not 0 < self.label_flip_fraction <= 1:
            raise SpatialBatteryError("label_flip_fraction must be within (0, 1]")
        if self.label_perturbations <= 0 or self.coordinate_permutations <= 0:
            raise SpatialBatteryError("label_perturbations and coordinate_permutations must be positive")
        if self.minimum_group_cells < 2:
            raise SpatialBatteryError("minimum_group_cells must be at least 2")
        if self.max_graph_edges <= 0:
            raise SpatialBatteryError("max_graph_edges must be positive")

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["radius_grid"] = list(self.radius_grid)
        data["assumed_leakage_fractions"] = list(self.assumed_leakage_fractions)
        return data


@dataclass
class BatteryDiagnostic:
    """One alternative-explanation result and its calibration decision."""

    control_name: str
    metric: str
    state: DiagnosticState
    score: Optional[float]
    baseline_effect: Optional[float]
    perturbed_effects: Dict[str, Optional[float]] = field(default_factory=dict)
    note: str = ""
    calibration: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_name": self.control_name,
            "metric": self.metric,
            "state": self.state.value,
            "score": self.score,
            "baseline_effect": self.baseline_effect,
            "perturbed_effects": dict(self.perturbed_effects),
            "note": self.note,
            "calibration": self.calibration,
        }


@dataclass
class SpatialBatteryResult:
    """Complete diagnostic battery plus the existing capability verdict."""

    observation: SpatialObservation
    baseline_effect: Optional[float]
    baseline_exposed_cells: int
    baseline_unexposed_cells: int
    diagnostics: Dict[str, BatteryDiagnostic]
    verdict: SpatialInferenceVerdict
    provenance: Dict[str, Any]
    semantic_envelope: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": "bionexus.spatial-alternative-battery.v1",
            "capability_id": "spatial.inference_validity",
            "observation": self.observation.to_dict(),
            "baseline_effect": self.baseline_effect,
            "baseline_exposed_cells": self.baseline_exposed_cells,
            "baseline_unexposed_cells": self.baseline_unexposed_cells,
            "diagnostics": {name: item.to_dict() for name, item in self.diagnostics.items()},
            "verdict": self.verdict.to_dict(),
            "provenance": dict(self.provenance),
            "semantic_envelope": self.semantic_envelope,
        }


@dataclass(frozen=True)
class _Effect:
    value: Optional[float]
    exposed_cells: int
    unexposed_cells: int


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _array_sha256(value: Any) -> str:
    array = np.ascontiguousarray(np.asarray(value))
    digest = hashlib.sha256()
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(str(array.shape).encode("ascii"))
    digest.update(array.tobytes())
    return digest.hexdigest()


def _validate_data(data: SpatialBatteryData) -> Tuple[np.ndarray, np.ndarray, np.ndarray, sparse.csr_matrix]:
    if not data.dataset_id or not data.state_revision_id:
        raise SpatialBatteryError("dataset_id and state_revision_id are required")
    if not data.segmentation_revision_id or not data.label_revision_id:
        raise SpatialBatteryError("segmentation_revision_id and label_revision_id are required")
    if not data.coordinate_system_id:
        raise SpatialBatteryError("coordinate_system_id is required")
    if data.coordinate_unit.casefold() not in {"micrometer", "micrometers", "um", "µm"}:
        raise SpatialBatteryError("physical coordinates in micrometers are required; embeddings are not accepted")
    if data.expression_scale not in {"counts", "log1p"}:
        raise SpatialBatteryError("expression_scale must be 'counts' or 'log1p'")
    if data.resolution not in {"cell", "spot"}:
        raise SpatialBatteryError("resolution must be 'cell' or 'spot'")

    coordinates = np.asarray(data.coordinates, dtype=float)
    labels = np.asarray(data.cell_labels, dtype=str)
    genes = np.asarray(data.gene_names, dtype=str)
    if coordinates.ndim != 2 or coordinates.shape[1] not in {2, 3}:
        raise SpatialBatteryError("coordinates must have shape (n_cells, 2|3)")
    if not np.isfinite(coordinates).all():
        raise SpatialBatteryError("coordinates contain non-finite values")
    if labels.ndim != 1 or labels.shape[0] != coordinates.shape[0]:
        raise SpatialBatteryError("cell_labels must align one-to-one with coordinates")
    if genes.ndim != 1 or len(set(genes.tolist())) != genes.size:
        raise SpatialBatteryError("gene_names must be a unique one-dimensional sequence")
    if not hasattr(data.expression, "shape") or len(data.expression.shape) != 2:
        raise SpatialBatteryError("expression must be a two-dimensional dense or sparse matrix")
    n_rows, n_cols = data.expression.shape
    if n_rows != coordinates.shape[0] or n_cols != genes.size:
        raise SpatialBatteryError("expression shape must align with coordinates and gene_names")
    if labels.size == 0 or np.any(np.char.str_len(labels) == 0):
        raise SpatialBatteryError("cell_labels must be non-empty")

    if data.contact_graph is None:
        contact = sparse.csr_matrix((coordinates.shape[0], coordinates.shape[0]), dtype=float)
    else:
        contact = sparse.csr_matrix(data.contact_graph, dtype=float)
        if contact.shape != (coordinates.shape[0], coordinates.shape[0]):
            raise SpatialBatteryError("contact_graph must have shape (n_cells, n_cells)")
        if contact.nnz and (not np.isfinite(contact.data).all() or np.any(contact.data < 0)):
            raise SpatialBatteryError("contact_graph weights must be finite and non-negative")
        contact = contact.maximum(contact.T).tocsr()
        contact.setdiag(0)
        contact.eliminate_zeros()
    return coordinates, labels, genes, contact


def _gene_vector(
    data: SpatialBatteryData, genes: np.ndarray, gene: str, expression: Optional[Any] = None
) -> np.ndarray:
    matches = np.flatnonzero(genes == gene)
    if matches.size != 1:
        raise SpatialBatteryError(f"target gene '{gene}' is absent or non-unique")
    matrix = data.expression if expression is None else expression
    if matrix.shape != data.expression.shape:
        raise SpatialBatteryError("perturbed expression matrix shape differs from the primary expression matrix")
    column = matrix[:, int(matches[0])]
    if sparse.issparse(column):
        values = np.asarray(column.toarray()).ravel().astype(float)
    else:
        values = np.asarray(column, dtype=float).ravel()
    if not np.isfinite(values).all() or np.any(values < 0):
        raise SpatialBatteryError("target-gene expression must be finite and non-negative")
    return np.log1p(values) if data.expression_scale == "counts" else values


def _radius_graph(coordinates: np.ndarray, radius: float, max_edges: int) -> sparse.csr_matrix:
    tree = cKDTree(coordinates)
    neighbor_counts = np.asarray(tree.query_ball_point(coordinates, radius, return_length=True), dtype=np.int64)
    estimated_edges = int((neighbor_counts.sum() - coordinates.shape[0]) // 2)
    if estimated_edges > max_edges:
        raise SpatialBatteryError(
            f"radius graph would contain approximately {estimated_edges} undirected edges, above max_graph_edges={max_edges}"
        )
    pairs = tree.query_pairs(radius, output_type="ndarray")
    if pairs.size == 0:
        return sparse.csr_matrix((coordinates.shape[0], coordinates.shape[0]), dtype=float)
    rows = np.concatenate([pairs[:, 0], pairs[:, 1]])
    cols = np.concatenate([pairs[:, 1], pairs[:, 0]])
    values = np.ones(rows.size, dtype=float)
    return sparse.csr_matrix((values, (rows, cols)), shape=(coordinates.shape[0], coordinates.shape[0]))


def _validated_variant_graph(graph: Any, n_cells: int, max_edges: int, variant_id: str) -> sparse.csr_matrix:
    result = sparse.csr_matrix(graph, dtype=float)
    if result.shape != (n_cells, n_cells):
        raise SpatialBatteryError(f"segmentation contact variant '{variant_id}' has the wrong shape")
    if result.nnz and (not np.isfinite(result.data).all() or np.any(result.data < 0)):
        raise SpatialBatteryError(f"segmentation contact variant '{variant_id}' has invalid weights")
    result = result.maximum(result.T).tocsr()
    result.setdiag(0)
    result.eliminate_zeros()
    if int(result.nnz // 2) > max_edges:
        raise SpatialBatteryError(f"segmentation contact variant '{variant_id}' exceeds max_graph_edges")
    return result


def _neighbor_exposure(graph: sparse.csr_matrix, labels: np.ndarray, neighbor_label: str) -> np.ndarray:
    neighbor_mask = (labels == neighbor_label).astype(float)
    return np.asarray(graph @ neighbor_mask).ravel() > 0


def _effect(
    values: np.ndarray,
    labels: np.ndarray,
    exposure: np.ndarray,
    focal_label: str,
    minimum_group_cells: int,
) -> _Effect:
    focal = labels == focal_label
    exposed = focal & exposure
    unexposed = focal & ~exposure
    n_exposed = int(exposed.sum())
    n_unexposed = int(unexposed.sum())
    if n_exposed < minimum_group_cells or n_unexposed < minimum_group_cells:
        return _Effect(None, n_exposed, n_unexposed)
    return _Effect(float(values[exposed].mean() - values[unexposed].mean()), n_exposed, n_unexposed)


def _adjusted_effect(
    values: np.ndarray,
    labels: np.ndarray,
    exposure: np.ndarray,
    focal_label: str,
    covariate: Sequence[float],
    minimum_group_cells: int,
) -> Optional[float]:
    raw = _effect(values, labels, exposure, focal_label, minimum_group_cells)
    if raw.value is None:
        return None
    focal = labels == focal_label
    x = np.asarray(covariate, dtype=float)
    if x.shape != labels.shape or not np.isfinite(x).all():
        raise SpatialBatteryError("covariate must be finite and align with cells")
    x_focal = x[focal]
    if float(np.std(x_focal)) <= np.finfo(float).eps:
        return raw.value
    x_focal = (x_focal - x_focal.mean()) / x_focal.std()
    design = np.column_stack([np.ones(int(focal.sum())), exposure[focal].astype(float), x_focal])
    coefficient, *_ = np.linalg.lstsq(design, values[focal], rcond=None)
    return float(coefficient[1])


def _retention_score(baseline: Optional[float], effects: Sequence[Optional[float]]) -> Optional[float]:
    if baseline is None or abs(baseline) <= np.finfo(float).eps or not effects or any(v is None for v in effects):
        return None
    concrete = [float(v) for v in effects if v is not None]
    if any(np.sign(v) != np.sign(baseline) for v in concrete):
        return 0.0
    return float(np.clip(min(abs(v) / abs(baseline) for v in concrete), 0.0, 1.0))


def _row_normalized(graph: sparse.csr_matrix) -> sparse.csr_matrix:
    degree = np.asarray(graph.sum(axis=1)).ravel()
    inv = np.zeros_like(degree, dtype=float)
    nonzero = degree > 0
    inv[nonzero] = 1.0 / degree[nonzero]
    return sparse.diags(inv) @ graph


def _calibrated_diagnostic(
    *,
    control_name: str,
    baseline: Optional[float],
    effects: Mapping[str, Optional[float]],
    score: Optional[float],
    note: str,
    registry: CalibrationRegistry,
    context: CalibrationContext,
    gold_runtime_evidence: Optional[SpatialGoldRuntimeEvidence],
) -> BatteryDiagnostic:
    metric = SPATIAL_CONTROL_METRICS[control_name]
    if score is None:
        return BatteryDiagnostic(
            control_name=control_name,
            metric=metric,
            state=DiagnosticState.UNTESTED,
            score=None,
            baseline_effect=baseline,
            perturbed_effects=dict(effects),
            note=note,
        )
    assessment: MetricAssessment = registry.assess(metric, score, context)
    in_gold_scope = is_spatial_gold_platform(context.platform)
    authorization = None
    if in_gold_scope and assessment.resolution.resolved:
        selected = next(
            (
                profile
                for profile in registry.profiles
                if profile.profile_id == assessment.resolution.profile_id
                and profile.version == assessment.resolution.profile_version
            ),
            None,
        )
        if selected is not None and gold_runtime_evidence is not None:
            authorization = gold_runtime_evidence.authorize(selected)
    authorized = authorization is not None and authorization.authorized
    if not in_gold_scope or not authorized:
        state = DiagnosticState.UNTESTED
    elif assessment.passed is True:
        state = DiagnosticState.CONTROLLED
    elif assessment.passed is False:
        state = DiagnosticState.FAILED
    else:
        state = DiagnosticState.UNTESTED
    if not in_gold_scope:
        scope_note = (
            "Empirical-gold calibration is restricted to Xenium, CosMx, and MERSCOPE; this platform is out of scope."
        )
    elif assessment.resolution.resolved and not authorized:
        scope_note = (
            "Resolved generic calibration was ignored because Gold Program membership, real-study bytes, "
            "trusted approval signature, and revocation state were not all verified."
        )
    else:
        scope_note = ""
    resolution_note = f"{assessment.resolution.reason} {scope_note}".strip()
    calibration = assessment.to_dict()
    if not in_gold_scope or (assessment.resolution.resolved and not authorized):
        calibration["profile_comparison_ignored"] = calibration["passed"]
        calibration["passed"] = None
        calibration["effective_resolution_status"] = (
            "OUT_OF_GOLD_PROGRAM_SCOPE" if not in_gold_scope else "GOLD_PROGRAM_AUTHORIZATION_REQUIRED"
        )
    if authorization is not None:
        calibration["spatial_gold_authorization"] = authorization.to_dict()
    calibration["spatial_empirical_gold_scope"] = {
        "program_version": (
            gold_runtime_evidence.program.program_version
            if gold_runtime_evidence is not None
            else SPATIAL_GOLD_PROGRAM_VERSION
        ),
        "program_sha256": (gold_runtime_evidence.program.program_sha256 if gold_runtime_evidence is not None else None),
        "supported_platforms": list(SPATIAL_GOLD_PLATFORMS),
        "platform_in_scope": in_gold_scope,
        "profile_authorized": authorized,
    }
    return BatteryDiagnostic(
        control_name=control_name,
        metric=metric,
        state=state,
        score=score,
        baseline_effect=baseline,
        perturbed_effects=dict(effects),
        note=f"{note} {resolution_note}".strip(),
        calibration=calibration,
    )


def _structural_control(control_name: str, note: str) -> BatteryDiagnostic:
    return BatteryDiagnostic(
        control_name=control_name,
        metric=f"structural_applicability.{control_name}",
        state=DiagnosticState.CONTROLLED,
        score=1.0,
        baseline_effect=None,
        note=note,
        calibration={"structural_applicability": True, "numeric_threshold_used": False},
    )


def _untested(control_name: str, note: str) -> BatteryDiagnostic:
    return BatteryDiagnostic(
        control_name=control_name,
        metric=SPATIAL_CONTROL_METRICS.get(control_name, f"spatial.{control_name}"),
        state=DiagnosticState.UNTESTED,
        score=None,
        baseline_effect=None,
        note=note,
    )


def run_spatial_alternative_battery(
    observation: SpatialObservation,
    data: SpatialBatteryData,
    plan: SpatialBatteryPlan,
    *,
    calibration_context: Optional[CalibrationContext] = None,
    calibration_registry: Optional[CalibrationRegistry] = None,
    spatial_gold_runtime_evidence: Optional[SpatialGoldRuntimeEvidence] = None,
) -> SpatialBatteryResult:
    """Execute the bounded alternative-explanation battery for one claim."""

    if spatial_gold_runtime_evidence is not None and not isinstance(
        spatial_gold_runtime_evidence,
        SpatialGoldRuntimeEvidence,
    ):
        raise SpatialBatteryError("spatial_gold_runtime_evidence must be a verified-materials contract")
    coordinates, labels, genes, contact_graph = _validate_data(data)
    if not observation.observation_id or not observation.statement or not observation.target_gene:
        raise SpatialBatteryError("observation_id, statement, and target_gene are required")
    if observation.focal_cell_label not in set(labels) or observation.neighbor_cell_label not in set(labels):
        raise SpatialBatteryError("focal_cell_label and neighbor_cell_label must both occur in cell_labels")
    if observation.claim_kind == SpatialClaimKind.LIGAND_RECEPTOR_INTERACTION:
        if observation.ligand_receptor_pair is None or len(observation.ligand_receptor_pair) != 2:
            raise SpatialBatteryError("ligand_receptor_pair is required for a ligand-receptor interaction claim")
    if int(contact_graph.nnz // 2) > plan.max_graph_edges:
        raise SpatialBatteryError(
            "exact contact_graph exceeds max_graph_edges; supply a bounded graph or increase the predeclared limit"
        )
    values = _gene_vector(data, genes, observation.target_gene)
    registry = calibration_registry or default_calibration_registry()
    context = calibration_context or CalibrationContext()
    radius_graph = _radius_graph(coordinates, plan.primary_radius, plan.max_graph_edges)

    contact_required = observation.claim_kind in {
        SpatialClaimKind.CONTACT_EXPRESSION_ENRICHMENT,
        SpatialClaimKind.LIGAND_RECEPTOR_INTERACTION,
    }
    exact_contact_available = contact_graph.nnz > 0 and data.resolution == "cell"
    if contact_required and exact_contact_available:
        baseline_graph = contact_graph
    elif contact_required:
        baseline_graph = radius_graph
    else:
        baseline_graph = radius_graph
    baseline_exposure = _neighbor_exposure(baseline_graph, labels, observation.neighbor_cell_label)
    baseline = _effect(values, labels, baseline_exposure, observation.focal_cell_label, plan.minimum_group_cells)

    diagnostics: Dict[str, BatteryDiagnostic] = {}

    # 1. Segmentation perturbation: caller must supply independently generated
    # alternative segmentations/reassignments. The engine never fabricates one.
    segmentation_effects: Dict[str, Optional[float]] = {}
    segmentation_variant_ids = sorted(
        set(data.segmentation_expression_variants) | set(data.segmentation_contact_variants)
    )
    for name in segmentation_variant_ids:
        matrix = data.segmentation_expression_variants.get(name, data.expression)
        variant_values = _gene_vector(data, genes, observation.target_gene, matrix)
        variant_graph = baseline_graph
        if name in data.segmentation_contact_variants:
            candidate = _validated_variant_graph(
                data.segmentation_contact_variants[name], labels.size, plan.max_graph_edges, name
            )
            if contact_required:
                variant_graph = candidate
        variant_exposure = _neighbor_exposure(variant_graph, labels, observation.neighbor_cell_label)
        segmentation_effects[name] = _effect(
            variant_values,
            labels,
            variant_exposure,
            observation.focal_cell_label,
            plan.minimum_group_cells,
        ).value
    diagnostics["segmentation_uncertainty"] = _calibrated_diagnostic(
        control_name="segmentation_uncertainty",
        baseline=baseline.value,
        effects=segmentation_effects,
        score=_retention_score(baseline.value, list(segmentation_effects.values())),
        note=(
            "Effect retention across supplied anchored-cell segmentation expression/contact revisions."
            if segmentation_effects
            else "No alternate segmentation assignment/expression matrices were supplied."
        ),
        registry=registry,
        context=context,
        gold_runtime_evidence=spatial_gold_runtime_evidence,
    )

    # 2. Transcript leakage: prefer outputs from explicit leakage models. If
    # absent, run a declared neighbor-mixture sensitivity grid; this is not
    # represented as estimated or corrected leakage.
    leakage_effects: Dict[str, Optional[float]] = {}
    for name, matrix in data.leakage_expression_variants.items():
        variant_values = _gene_vector(data, genes, observation.target_gene, matrix)
        leakage_effects[f"model:{name}"] = _effect(
            variant_values,
            labels,
            baseline_exposure,
            observation.focal_cell_label,
            plan.minimum_group_cells,
        ).value
    leakage_note = "Effect retention across supplied leakage-model outputs."
    if not leakage_effects and plan.assumed_leakage_fractions:
        mixing = _row_normalized(radius_graph)
        neighbor_signal = np.asarray(mixing @ values).ravel()
        for fraction in plan.assumed_leakage_fractions:
            sensitivity_values = np.clip(values - fraction * neighbor_signal, 0.0, None)
            leakage_effects[f"assumed_fraction:{fraction:g}"] = _effect(
                sensitivity_values,
                labels,
                baseline_exposure,
                observation.focal_cell_label,
                plan.minimum_group_cells,
            ).value
        leakage_note = (
            "Neighbor-mixture sensitivity under predeclared assumed leakage fractions; "
            "these are perturbations, not estimates of the true leakage process."
        )
    diagnostics["transcript_leakage"] = _calibrated_diagnostic(
        control_name="transcript_leakage",
        baseline=baseline.value,
        effects=leakage_effects,
        score=_retention_score(baseline.value, list(leakage_effects.values())),
        note=leakage_note if leakage_effects else "No leakage model output or sensitivity grid was supplied.",
        registry=registry,
        context=context,
        gold_runtime_evidence=spatial_gold_runtime_evidence,
    )

    # 3-6. Covariate and geometry controls.
    covariate_specs = (
        ("cell_size", data.cell_size, "Effect after adjustment for cell size."),
        ("nuclear_eccentricity", data.nuclear_eccentricity, "Effect after adjustment for nuclear eccentricity."),
        (
            "transcript_density",
            data.total_transcript_counts,
            "Effect after adjustment for local transcript density.",
        ),
    )
    for control_name, covariate, note in covariate_specs:
        if covariate is None:
            diagnostics[control_name] = _untested(control_name, f"{note} Required covariate was not supplied.")
            continue
        if control_name == "transcript_density":
            transcript_counts = np.asarray(covariate, dtype=float)
            if transcript_counts.shape != labels.shape or not np.isfinite(transcript_counts).all():
                raise SpatialBatteryError("total_transcript_counts must be finite and align with cells")
            local_covariate = np.asarray(_row_normalized(radius_graph) @ transcript_counts).ravel()
        else:
            local_covariate = covariate
        adjusted = _adjusted_effect(
            values,
            labels,
            baseline_exposure,
            observation.focal_cell_label,
            local_covariate,
            plan.minimum_group_cells,
        )
        diagnostics[control_name] = _calibrated_diagnostic(
            control_name=control_name,
            baseline=baseline.value,
            effects={"adjusted": adjusted},
            score=_retention_score(baseline.value, [adjusted]),
            note=note,
            registry=registry,
            context=context,
            gold_runtime_evidence=spatial_gold_runtime_evidence,
        )

    local_density = np.asarray(radius_graph.sum(axis=1)).ravel()
    density_adjusted = _adjusted_effect(
        values,
        labels,
        baseline_exposure,
        observation.focal_cell_label,
        local_density,
        plan.minimum_group_cells,
    )
    diagnostics["local_cell_density"] = _calibrated_diagnostic(
        control_name="local_cell_density",
        baseline=baseline.value,
        effects={"adjusted": density_adjusted},
        score=_retention_score(baseline.value, [density_adjusted]),
        note="Effect after adjustment for local cell-neighbor count.",
        registry=registry,
        context=context,
        gold_runtime_evidence=spatial_gold_runtime_evidence,
    )

    radius_exposure = _neighbor_exposure(radius_graph, labels, observation.neighbor_cell_label)
    radius_baseline = _effect(
        values, labels, radius_exposure, observation.focal_cell_label, plan.minimum_group_cells
    ).value
    if contact_required and not exact_contact_available:
        diagnostics["contact_geometry"] = _untested(
            "contact_geometry",
            "Exact segmentation-derived contact graph is required for a contact claim; radius proximity was not substituted.",
        )
    else:
        neighbor_mask = (labels == observation.neighbor_cell_label).astype(float)
        contact_surface = np.asarray(contact_graph @ neighbor_mask).ravel()
        surface_adjusted = _adjusted_effect(
            values,
            labels,
            baseline_exposure,
            observation.focal_cell_label,
            contact_surface,
            plan.minimum_group_cells,
        )
        geometry_effects = {
            "radius_proxy": radius_baseline,
            "contact_surface_adjusted": surface_adjusted,
        }
        diagnostics["contact_geometry"] = _calibrated_diagnostic(
            control_name="contact_geometry",
            baseline=baseline.value,
            effects=geometry_effects,
            score=_retention_score(baseline.value, list(geometry_effects.values())),
            note=(
                "Exact segmentation contact was challenged by radius proximity and adjustment for supplied "
                "contact-edge weight (surface length/area when encoded by the input graph)."
            ),
            registry=registry,
            context=context,
            gold_runtime_evidence=spatial_gold_runtime_evidence,
        )

    # 7. Field/batch effect stability.
    batch_effects: Dict[str, Optional[float]] = {}
    if data.fov_or_batch is not None:
        groups = np.asarray(data.fov_or_batch, dtype=str)
        if groups.shape != labels.shape:
            raise SpatialBatteryError("fov_or_batch must align with cells")
        for group in sorted(set(groups)):
            in_group = groups == group
            group_selector = sparse.diags(in_group.astype(float))
            group_graph = (group_selector @ baseline_graph @ group_selector).tocsr()
            group_exposure = _neighbor_exposure(group_graph, labels, observation.neighbor_cell_label)
            subset_labels = labels.copy()
            subset_labels[~in_group] = "__outside_fov__"
            batch_effects[group] = _effect(
                values,
                subset_labels,
                group_exposure,
                observation.focal_cell_label,
                plan.minimum_group_cells,
            ).value
    batch_score = _retention_score(baseline.value, list(batch_effects.values())) if len(batch_effects) >= 2 else None
    diagnostics["batch_fov"] = _calibrated_diagnostic(
        control_name="batch_fov",
        baseline=baseline.value,
        effects=batch_effects,
        score=batch_score,
        note=(
            "Effect retention within each supplied FOV/batch."
            if len(batch_effects) >= 2
            else "At least two FOV/batch groups with both exposure classes are required."
        ),
        registry=registry,
        context=context,
        gold_runtime_evidence=spatial_gold_runtime_evidence,
    )

    # 8. Neighborhood-radius sensitivity.
    radius_effects: Dict[str, Optional[float]] = {}
    for radius in plan.radius_grid:
        graph = _radius_graph(coordinates, radius, plan.max_graph_edges)
        exposure = _neighbor_exposure(graph, labels, observation.neighbor_cell_label)
        radius_effects[f"radius:{radius:g}"] = _effect(
            values, labels, exposure, observation.focal_cell_label, plan.minimum_group_cells
        ).value
    radius_reference = radius_baseline if radius_baseline is not None else baseline.value
    diagnostics["neighborhood_radius"] = _calibrated_diagnostic(
        control_name="neighborhood_radius",
        baseline=radius_reference,
        effects=radius_effects,
        score=_retention_score(radius_reference, list(radius_effects.values())),
        note="Effect retention across the predeclared physical-radius grid.",
        registry=registry,
        context=context,
        gold_runtime_evidence=spatial_gold_runtime_evidence,
    )

    # 9. Coordinate permutation null. Coordinates are permuted relative to the
    # fixed expression/label rows and a new bounded radius graph is constructed.
    rng = np.random.default_rng(plan.random_seed)
    null_effects: Dict[str, Optional[float]] = {}
    for index in range(plan.coordinate_permutations):
        permuted = coordinates[rng.permutation(coordinates.shape[0])]
        graph = _radius_graph(permuted, plan.primary_radius, plan.max_graph_edges)
        exposure = _neighbor_exposure(graph, labels, observation.neighbor_cell_label)
        null_effects[f"permutation:{index + 1}"] = _effect(
            values, labels, exposure, observation.focal_cell_label, plan.minimum_group_cells
        ).value
    valid_nulls = [value for value in null_effects.values() if value is not None]
    if radius_baseline is None or len(valid_nulls) != plan.coordinate_permutations:
        permutation_p = None
    else:
        exceedances = sum(abs(value) >= abs(radius_baseline) for value in valid_nulls)
        permutation_p = float((1 + exceedances) / (1 + len(valid_nulls)))
    diagnostics["permutation_null"] = _calibrated_diagnostic(
        control_name="permutation_null",
        baseline=radius_baseline,
        effects=null_effects,
        score=permutation_p,
        note="Empirical two-sided coordinate-permutation p-value with +1 correction.",
        registry=registry,
        context=context,
        gold_runtime_evidence=spatial_gold_runtime_evidence,
    )
    diagnostics["spatial_autocorrelation"] = _calibrated_diagnostic(
        control_name="spatial_autocorrelation",
        baseline=radius_baseline,
        effects=null_effects,
        score=permutation_p,
        note="Spatial structure tested against the same coordinate-permutation null; separately calibrated.",
        registry=registry,
        context=context,
        gold_runtime_evidence=spatial_gold_runtime_evidence,
    )

    # 10. Cell-label perturbation with preserved global label counts.
    label_effects: Dict[str, Optional[float]] = {}
    for variant_id, supplied_labels in data.cell_label_variants.items():
        variant = np.asarray(supplied_labels, dtype=str)
        if variant.shape != labels.shape or np.any(np.char.str_len(variant) == 0):
            raise SpatialBatteryError(f"cell label variant '{variant_id}' must be non-empty and align with cells")
        exposure = _neighbor_exposure(baseline_graph, variant, observation.neighbor_cell_label)
        label_effects[f"supplied:{variant_id}"] = _effect(
            values, variant, exposure, observation.focal_cell_label, plan.minimum_group_cells
        ).value
    perturb_n = max(2, int(round(labels.size * plan.label_flip_fraction)))
    perturb_n = min(perturb_n, labels.size)
    for index in range(plan.label_perturbations):
        variant = labels.copy()
        selected = rng.choice(labels.size, size=perturb_n, replace=False)
        variant[selected] = variant[selected][rng.permutation(perturb_n)]
        graph = baseline_graph
        exposure = _neighbor_exposure(graph, variant, observation.neighbor_cell_label)
        label_effects[f"label_perturbation:{index + 1}"] = _effect(
            values, variant, exposure, observation.focal_cell_label, plan.minimum_group_cells
        ).value
    diagnostics["cell_label_perturbation"] = _calibrated_diagnostic(
        control_name="cell_label_perturbation",
        baseline=baseline.value,
        effects=label_effects,
        score=_retention_score(baseline.value, list(label_effects.values())),
        note=(
            "Effect retention across supplied label revisions plus predeclared partial label permutations "
            "preserving global label counts."
        ),
        registry=registry,
        context=context,
        gold_runtime_evidence=spatial_gold_runtime_evidence,
    )

    # Canonical controls whose applicability depends on resolution/claim class.
    if data.resolution == "cell" and exact_contact_available:
        diagnostics["spot_composition"] = _structural_control(
            "spot_composition",
            "Cell-resolved input with an exact segmentation contact graph; spot-mixture composition is not applicable.",
        )
    else:
        diagnostics["spot_composition"] = _untested(
            "spot_composition", "Spot composition/deconvolution uncertainty remains unresolved."
        )

    if observation.claim_kind == SpatialClaimKind.LIGAND_RECEPTOR_INTERACTION:
        diagnostics["ligand_receptor_abundance"] = _untested(
            "ligand_receptor_abundance",
            "Ligand/receptor abundance symmetry requires an explicit pair-specific model and was not inferred from a single target gene.",
        )
    else:
        diagnostics["ligand_receptor_abundance"] = _structural_control(
            "ligand_receptor_abundance",
            "Observation is expression enrichment rather than a ligand-receptor interaction claim; LR abundance is not applicable.",
        )

    controls = [ControlResult(name=name, status=item.state.value, note=item.note) for name, item in diagnostics.items()]
    verdict = assess_spatial_inference(observation.statement, controls)
    if baseline.value is None:
        verdict = SpatialInferenceVerdict(
            observation=observation.statement,
            verdict="ABSTAIN",
            controlled=verdict.controlled,
            untested=sorted(set(verdict.untested) | {"baseline_effect"}),
            failed=verdict.failed,
            notes=verdict.notes
            + [
                "The baseline effect was not estimable with the predeclared minimum group size; "
                "no spatial support verdict can be issued."
            ],
        )

    provenance_payload = {
        "dataset_id": data.dataset_id,
        "state_revision_id": data.state_revision_id,
        "segmentation_revision_id": data.segmentation_revision_id,
        "label_revision_id": data.label_revision_id,
        "coordinate_system_id": data.coordinate_system_id,
        "coordinate_unit": data.coordinate_unit,
        "expression_scale": data.expression_scale,
        "resolution": data.resolution,
        "baseline_graph_kind": (
            "exact_segmentation_contact" if contact_required and exact_contact_available else "physical_radius"
        ),
        "exact_contact_available": exact_contact_available,
        "target_gene_sha256": _array_sha256(values),
        "coordinates_sha256": _array_sha256(coordinates),
        "labels_sha256": _array_sha256(labels),
        "contact_graph_sha256": _canonical_sha256(
            {
                "shape": contact_graph.shape,
                "indptr": contact_graph.indptr.tolist(),
                "indices": contact_graph.indices.tolist(),
                "data": contact_graph.data.tolist(),
            }
        ),
        "plan": plan.to_dict(),
        "segmentation_variant_ids": segmentation_variant_ids,
        "segmentation_target_gene_sha256": {
            name: _array_sha256(
                _gene_vector(
                    data,
                    genes,
                    observation.target_gene,
                    data.segmentation_expression_variants.get(name, data.expression),
                )
            )
            for name in segmentation_variant_ids
        },
        "leakage_variant_ids": sorted(data.leakage_expression_variants),
        "leakage_target_gene_sha256": {
            name: _array_sha256(_gene_vector(data, genes, observation.target_gene, matrix))
            for name, matrix in sorted(data.leakage_expression_variants.items())
        },
        "supplied_label_variant_sha256": {
            name: _array_sha256(variant) for name, variant in sorted(data.cell_label_variants.items())
        },
        "calibration_registry_version": registry.registry_version,
        "calibration_registry_sha256": registry.registry_sha256,
        "spatial_empirical_gold": {
            "program_version": (
                spatial_gold_runtime_evidence.program.program_version
                if spatial_gold_runtime_evidence is not None
                else SPATIAL_GOLD_PROGRAM_VERSION
            ),
            "program_sha256": (
                spatial_gold_runtime_evidence.program.program_sha256
                if spatial_gold_runtime_evidence is not None
                else None
            ),
            "program_status": (
                spatial_gold_runtime_evidence.program.status
                if spatial_gold_runtime_evidence is not None
                else "not_supplied"
            ),
            "supported_platforms": list(SPATIAL_GOLD_PLATFORMS),
            "declared_platform": context.platform,
            "platform_in_scope": is_spatial_gold_platform(context.platform),
            "platform_pooling": False,
            "runtime_authorization_required": True,
        },
        "fallback_used": False,
    }
    provenance_payload["battery_run_sha256"] = _canonical_sha256(provenance_payload)
    result = SpatialBatteryResult(
        observation=observation,
        baseline_effect=baseline.value,
        baseline_exposed_cells=baseline.exposed_cells,
        baseline_unexposed_cells=baseline.unexposed_cells,
        diagnostics=diagnostics,
        verdict=verdict,
        provenance=provenance_payload,
    )
    from bionexus.scientific_semantics import spatial_battery_semantic_envelope

    result.semantic_envelope = spatial_battery_semantic_envelope(result, data).to_dict()
    return result
