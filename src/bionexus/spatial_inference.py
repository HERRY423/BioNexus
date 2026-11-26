"""
BioNexus Spatial Inference Validity Assessment (flagship capability C, BNS-013).

The spatial verdict describes survival of alternative explanations for one
observation. ROBUST requires measured sample replication and evidence-bound
controls including a permutation null. Without the null the upper bound is
SUPPORTED. Untested or declaration-only controls cap the verdict at FRAGILE.
A failed alternative yields CONFLICTED. Insufficient observed sample units,
an absent control matrix or an unestimable baseline yields ABSTAIN.

The canonical alternatives are part of the versioned capability contract.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional

if TYPE_CHECKING:
    from pandas import DataFrame

# The canonical alternative-explanation base registry (contract-visible).
CANONICAL_BASE_ALTERNATIVES: tuple = (
    "cell_size",
    "transcript_density",
    "segmentation_uncertainty",
    "transcript_leakage",
    "nuclear_eccentricity",
    "local_cell_density",
    "spot_composition",
    "spatial_autocorrelation",
    "batch_fov",
    "ligand_receptor_abundance",
    "contact_geometry",
    "edge_effects",
    "neighborhood_radius",
    "permutation_null",
    "cell_label_perturbation",
    "sample_level_replication",
)

# Canonical alias mapping for robust resolution
ALTERNATIVE_ALIASES: Dict[str, str] = {
    "segmentation_leakage": "segmentation_uncertainty",
    "segmentation_specificity": "segmentation_uncertainty",
    "segmentation_perturbation": "segmentation_uncertainty",
    "neighborhood_radius_sensitivity": "neighborhood_radius",
    "morphology_confounding": "cell_size",
    "cell_density_confounding": "local_cell_density",
    "edge_effect": "edge_effects",
    "local_transcript_density": "transcript_density",
    "transcript_spillover": "transcript_leakage",
    "leakage_sensitivity": "transcript_leakage",
    "label_uncertainty": "cell_label_perturbation",
    "cell_label_sensitivity": "cell_label_perturbation",
    "contact_surface_geometry": "contact_geometry",
    "fov_batch_effect": "batch_fov",
    "coordinate_permutation_null": "permutation_null",
}

CANONICAL_ALTERNATIVES: tuple = tuple(CANONICAL_BASE_ALTERNATIVES)

# Controls that MUST be addressed (TESTED / CONTROLLED / FAILED) before a
# conclusion can be called anything better than FRAGILE.
CORE_CONTROLS: tuple = (
    "cell_size",
    "transcript_density",
    "segmentation_uncertainty",
    "transcript_leakage",
    "contact_geometry",
    "sample_level_replication",
)

CONTROL_STATUSES = ("TESTED", "CONTROLLED", "DECLARED", "UNTESTED", "FAILED")

VALIDITY_LADDER = ("ROBUST", "SUPPORTED", "FRAGILE", "CONFLICTED", "ABSTAIN")


@dataclass
class ControlResult:
    """Status of one alternative-explanation control."""

    name: str
    status: str  # CONTROL_STATUSES
    note: str = ""
    statistic: Optional[float] = None
    p_or_interval: Optional[float | tuple[float, float]] = None
    artifact_sha256: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in CONTROL_STATUSES:
            raise ValueError(f"Control status '{self.status}' not in {CONTROL_STATUSES}")
        if self.status in ("TESTED", "CONTROLLED") and not self.artifact_sha256:
            self.status = "DECLARED"
        if self.name not in CANONICAL_ALTERNATIVES and self.name not in ALTERNATIVE_ALIASES:
            raise ValueError(
                f"Unknown alternative-explanation control '{self.name}'. Canonical: {list(CANONICAL_ALTERNATIVES)}"
            )


@dataclass
class SpatialInferenceVerdict:
    """Verdict for one spatial observation under its alternative explanations."""

    observation: str
    verdict: str  # VALIDITY_LADDER
    controlled: List[str] = field(default_factory=list)
    untested: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    declared: List[str] = field(default_factory=list)
    control_evidence: Dict[str, ControlResult] = field(default_factory=dict)
    samples_per_group: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _canonical(name: str) -> str:
    seen = set()
    while name in ALTERNATIVE_ALIASES:
        if name in seen:
            raise ValueError(f"Cyclic spatial control alias at {name!r}")
        seen.add(name)
        name = ALTERNATIVE_ALIASES[name]
    return name


def _normalize_controls(
    controls: Optional[List[ControlResult] | Dict[str, str]],
    artifacts: Mapping[str, bytes],
) -> Dict[str, ControlResult]:
    if isinstance(controls, dict):
        controls = [ControlResult(name=k, status=v) for k, v in controls.items()]
    normalized: Dict[str, ControlResult] = {}
    # If aliases give conflicting results, retain the weaker status and its evidence.
    priority = ("TESTED", "CONTROLLED", "DECLARED", "UNTESTED", "FAILED")
    for item in controls or ():
        name = _canonical(item.name)
        if name == "sample_level_replication":
            continue  # Always measured directly from observations.
        status = item.status
        if status in ("TESTED", "CONTROLLED"):
            digest = (item.artifact_sha256 or "").lower()
            artifact = artifacts.get(digest)
            if not artifact or hashlib.sha256(artifact).hexdigest() != digest:
                status = "DECLARED"
        if name not in normalized or priority.index(status) > priority.index(normalized[name].status):
            normalized[name] = replace(item, name=name, status=status)
    return normalized


def _sample_replication(
    obs: Optional[DataFrame], donor_col: Optional[str], section_col: Optional[str], group_col: Optional[str]
) -> tuple[ControlResult, Dict[str, int]]:
    name = "sample_level_replication"
    if obs is None or obs.empty:
        return ControlResult(name, "UNTESTED", "Sample-level observations are missing."), {}
    # Prefer the independent donor when sections are nested within donors.
    candidates = (donor_col,) if donor_col is not None else ("donor", "donor_id")
    candidates += (section_col,) if section_col is not None else ("section", "section_id", "slice", "slice_id")
    unit = next((col for col in candidates if col in obs), None)
    if unit is None:
        return ControlResult(name, "UNTESTED", "Supply donor or tissue-section identifiers in obs."), {}

    import pandas as pd

    units = obs[unit].astype("string").str.strip().replace("", pd.NA)
    grouped = group_col is not None and group_col in obs
    groups = obs[group_col].astype("string").str.strip().replace("", pd.NA) if grouped else "all"
    pairs = pd.DataFrame({"group": groups, "unit": units}).drop_duplicates()
    counts = {str(k): int(v) for k, v in pairs.groupby("group", observed=True)["unit"].nunique().items()}
    records = pairs.dropna().sort_values(["group", "unit"]).values.tolist()
    digest = hashlib.sha256(json.dumps([unit, group_col, records], ensure_ascii=False).encode()).hexdigest()
    if not counts or pairs.isna().any().any():
        return ControlResult(name, "UNTESTED", "Group or sample identifiers are incomplete."), counts
    minimum = min(counts.values())
    if minimum < 2:
        status = "FAILED"
        note = f"Fewer than two {unit} units in a group. Limit the observation to a single-section or donor description."
    elif group_col is not None and not grouped:
        status = "UNTESTED"
        note = f"Group column {group_col!r} is missing. Group-specific replication could not be assessed."
    else:
        status = "CONTROLLED"
        note = f"Observed at least two distinct {unit} units per group."
    return ControlResult(name, status, note, statistic=minimum, artifact_sha256=digest), counts


def assess_spatial_inference(
    observation: str,
    controls: Optional[List[ControlResult] | Dict[str, str]] = None,
    *,
    obs: Optional[DataFrame] = None,
    donor_col: Optional[str] = None,
    section_col: Optional[str] = None,
    group_col: Optional[str] = "condition",
    artifacts: Optional[Mapping[str, bytes]] = None,
) -> SpatialInferenceVerdict:
    """Assess one observation using control artifacts and sample-level replication.

    Supply original artifact bytes keyed by their SHA-256 digest. The digest
    identifies what was measured; interpretation of an external result remains
    the responsibility of its reviewer. Supply claim-scoped obs rows, with
    group_col=None for a single cohort. Cells, spots and FOVs are subsamples.
    """
    results = _normalize_controls(controls, artifacts or {})
    has_controls = bool(results)
    replication, counts = _sample_replication(obs, donor_col, section_col, group_col)
    results[replication.name] = replication

    verdict = SpatialInferenceVerdict(
        observation=observation,
        verdict="FRAGILE",
        controlled=sorted(n for n, r in results.items() if r.status in ("TESTED", "CONTROLLED")),
        untested=sorted(
            n for n in CANONICAL_ALTERNATIVES
            if (n not in results and n != "permutation_null") or (n in results and results[n].status == "UNTESTED")
        ),
        failed=sorted(n for n, r in results.items() if r.status == "FAILED"),
        declared=sorted(n for n, r in results.items() if r.status == "DECLARED"),
        control_evidence=results,
        samples_per_group=counts,
        notes=[r.note for r in results.values() if r.note],
    )
    if replication.status == "FAILED" or not has_controls:
        verdict.verdict = "ABSTAIN"
        if not has_controls:
            verdict.notes.append("No alternative-explanation controls were provided.")
    elif verdict.failed:
        verdict.verdict = "CONFLICTED"
        verdict.notes.append("A reported alternative explanation overturns the observation.")
    elif verdict.untested or verdict.declared:
        if verdict.declared:
            verdict.notes.append("Control evidence bytes were absent or did not match the recorded SHA-256.")
        core_missing = [name for name in CORE_CONTROLS if name not in verdict.controlled]
        if core_missing:
            verdict.notes.append("Core confound controls outstanding: " + ", ".join(core_missing))
    elif "permutation_null" in verdict.controlled:
        verdict.verdict = "ROBUST"
    else:
        verdict.verdict = "SUPPORTED"
        verdict.notes.append("No permutation null recorded. Significance language stays capped at SUPPORTED.")
    return verdict
