"""
BioNexus Spatial Inference Validity Assessment (flagship capability C, BNS-013).

Not a reimplementation of Squidpy. The question answered here is:

    **Can this spatial biology conclusion survive its alternative explanations?**

A spatial observation (e.g. "gene X enriches toward macrophage-facing
membrane") is compatible with several non-biological explanations: cell size,
transcript density, segmentation uncertainty, transcript leakage, nuclear
eccentricity, local cell density, label uncertainty, spot composition, spatial
autocorrelation, batch/FOV artifacts, ligand/receptor abundance, contact
geometry, neighborhood-radius choice, and the absence of a permutation null.
This module evaluates a declared control-status matrix and returns:

    ROBUST      every canonical control TESTED-and-passing + permutation null
    SUPPORTED   all provided controls pass; canonical set complete
    FRAGILE     at least one alternative left UNTESTED (the honest default)
    CONFLICTED  at least one tested alternative explains or overturns the effect
    ABSTAIN     no controls were provided or the executable baseline is not estimable

Deterministic; the canonical alternative registry below is part of the
capability contract and may only change with a contract version bump.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
    "neighborhood_radius",
    "permutation_null",
    "cell_label_perturbation",
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
    "edge_effects": "contact_geometry",
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
)

CONTROL_STATUSES = ("TESTED", "CONTROLLED", "UNTESTED", "FAILED")

VALIDITY_LADDER = ("ROBUST", "SUPPORTED", "FRAGILE", "CONFLICTED", "ABSTAIN")


@dataclass
class ControlResult:
    """Status of one alternative-explanation control."""

    name: str
    status: str  # CONTROL_STATUSES
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in CONTROL_STATUSES:
            raise ValueError(f"Control status '{self.status}' not in {CONTROL_STATUSES}")
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

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation": self.observation,
            "verdict": self.verdict,
            "controlled": list(self.controlled),
            "untested": list(self.untested),
            "failed": list(self.failed),
            "notes": list(self.notes),
        }


def _normalize_controls(
    controls: Optional[List[ControlResult] | Dict[str, str]],
) -> List[ControlResult]:
    if controls is None:
        return []
    raw_list: List[ControlResult] = []
    if isinstance(controls, dict):
        raw_list = [ControlResult(name=k, status=v) for k, v in controls.items()]
    else:
        raw_list = list(controls)

    # Resolve aliases and merge status (FAILED takes precedence over TESTED/CONTROLLED)
    status_map: Dict[str, str] = {}
    notes_map: Dict[str, str] = {}
    for c in raw_list:
        canon_name = ALTERNATIVE_ALIASES.get(c.name, c.name)
        curr_status = status_map.get(canon_name)
        if curr_status == "FAILED" or c.status == "FAILED":
            status_map[canon_name] = "FAILED"
        elif curr_status == "UNTESTED" or c.status == "UNTESTED":
            status_map[canon_name] = "UNTESTED"
        else:
            status_map[canon_name] = c.status
        if c.note:
            notes_map[canon_name] = c.note

    return [ControlResult(name=k, status=v, note=notes_map.get(k, "")) for k, v in status_map.items()]


def assess_spatial_inference(
    observation: str,
    controls: Optional[List[ControlResult] | Dict[str, str]] = None,
) -> SpatialInferenceVerdict:
    """
    Assess whether a spatial conclusion survives its alternative explanations.

    Fail-closed semantics:
    - no controls at all              -> ABSTAIN (nothing was actually tested)
    - any FAILED control              -> CONFLICTED (an alternative explains it)
    - any canonical alternative left UNTESTED -> FRAGILE (names the gaps)
    - core controls addressed + permutation null -> ROBUST; without the null
      the verdict tops out at SUPPORTED.
    """
    results = _normalize_controls(controls)
    if not results:
        return SpatialInferenceVerdict(
            observation=observation,
            verdict="ABSTAIN",
            notes=[
                "No alternative-explanation controls were provided; the observation cannot be "
                "certified or refuted (request the core confound controls first)."
            ],
        )

    status_by_name = {c.name: c.status for c in results}
    notes = [c.note for c in results if c.note]

    failed = sorted(n for n, s in status_by_name.items() if s == "FAILED")
    if failed:
        return SpatialInferenceVerdict(
            observation=observation,
            verdict="CONFLICTED",
            controlled=sorted(n for n, s in status_by_name.items() if s in ("TESTED", "CONTROLLED")),
            untested=sorted(n for n, s in status_by_name.items() if s == "UNTESTED"),
            failed=failed,
            notes=notes
            + [
                "A tested alternative explanation explains or overturns the observation: evidence is "
                "CONFLICTED until the confound is resolved or the claim is restated."
            ],
        )

    controlled = sorted(n for n, s in status_by_name.items() if s in ("TESTED", "CONTROLLED"))
    untested_declared = sorted(n for n, s in status_by_name.items() if s == "UNTESTED")
    # Canonical base alternatives that were never declared count as untested, with
    # one exception: an absent permutation_null is a cap (SUPPORTED at most),
    # not a FRAGILE gap — only an explicitly UNTESTED null forces FRAGILE.
    untested_canonical = sorted(
        n for n in CANONICAL_BASE_ALTERNATIVES if n not in status_by_name and n != "permutation_null"
    )
    untested = sorted(set(untested_declared) | set(untested_canonical))

    core_missing = [c for c in CORE_CONTROLS if c in untested]
    if untested:
        return SpatialInferenceVerdict(
            observation=observation,
            verdict="FRAGILE",
            controlled=controlled,
            untested=untested,
            notes=notes
            + (
                [
                    "Core confound controls not yet addressed: "
                    + ", ".join(core_missing)
                    + ". The observation may reflect measurement geometry rather than biology."
                ]
                if core_missing
                else []
            ),
        )

    has_null = status_by_name.get("permutation_null") in ("TESTED", "CONTROLLED")
    return SpatialInferenceVerdict(
        observation=observation,
        verdict="ROBUST" if has_null else "SUPPORTED",
        controlled=controlled,
        notes=notes
        + (
            []
            if has_null
            else ["No permutation null recorded: significance language stays capped at SUPPORTED."]
        ),
    )
