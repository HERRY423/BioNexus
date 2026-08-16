"""
BioNexus Spatial Inference Validity Assessment (flagship capability C, BNS-013).

Not a reimplementation of Squidpy. The question answered here is:

    **Can this spatial biology conclusion survive its alternative explanations?**

A spatial observation (e.g. "gene X enriches toward macrophage-facing
membrane") is compatible with several non-biological explanations: cell size,
transcript density, segmentation leakage, nuclear eccentricity, local cell
density, spot composition, spatial autocorrelation, batch/FOV artifacts,
ligand/receptor abundance, contact geometry, neighborhood-radius choice, and
the absence of a permutation null. This module evaluates a declared
control-status matrix and returns:

    ROBUST      every canonical control TESTED-and-passing + permutation null
    SUPPORTED   all provided controls pass; canonical set complete
    FRAGILE     at least one alternative left UNTESTED (the honest default)
    ABSTAIN     a control FAILED or no controls were provided at all

Deterministic; the canonical alternative registry below is part of the
capability contract and may only change with a contract version bump.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# The canonical alternative-explanation registry (contract-visible).
CANONICAL_ALTERNATIVES: tuple = (
    "cell_size",
    "transcript_density",
    "segmentation_uncertainty",
    "nuclear_eccentricity",
    "local_cell_density",
    "spot_composition",
    "spatial_autocorrelation",
    "batch_fov",
    "ligand_receptor_abundance",
    "contact_geometry",
    "neighborhood_radius",
    "permutation_null",
)

# Controls that MUST be addressed (TESTED / CONTROLLED / FAILED) before a
# conclusion can be called anything better than FRAGILE.
CORE_CONTROLS: tuple = ("cell_size", "transcript_density", "segmentation_uncertainty")

CONTROL_STATUSES = ("TESTED", "CONTROLLED", "UNTESTED", "FAILED")

VALIDITY_LADDER = ("ROBUST", "SUPPORTED", "FRAGILE", "ABSTAIN")


@dataclass
class ControlResult:
    """Status of one alternative-explanation control."""

    name: str
    status: str  # CONTROL_STATUSES
    note: str = ""

    def __post_init__(self) -> None:
        if self.status not in CONTROL_STATUSES:
            raise ValueError(f"Control status '{self.status}' not in {CONTROL_STATUSES}")
        if self.name not in CANONICAL_ALTERNATIVES:
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
    if isinstance(controls, dict):
        return [ControlResult(name=k, status=v) for k, v in controls.items()]
    return list(controls)


def assess_spatial_inference(
    observation: str,
    controls: Optional[List[ControlResult] | Dict[str, str]] = None,
) -> SpatialInferenceVerdict:
    """
    Assess whether a spatial conclusion survives its alternative explanations.

    Fail-closed semantics:
    - no controls at all              -> ABSTAIN (nothing was actually tested)
    - any FAILED control              -> ABSTAIN (an alternative explains it)
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
            verdict="ABSTAIN",
            controlled=sorted(n for n, s in status_by_name.items() if s in ("TESTED", "CONTROLLED")),
            untested=sorted(n for n, s in status_by_name.items() if s == "UNTESTED"),
            failed=failed,
            notes=notes
            + [
                "A declared alternative explanation FAILED its control: the conclusion is not "
                "interpretable as stated until the confound is resolved."
            ],
        )

    controlled = sorted(n for n, s in status_by_name.items() if s in ("TESTED", "CONTROLLED"))
    untested_declared = sorted(n for n, s in status_by_name.items() if s == "UNTESTED")
    # Canonical alternatives that were never declared count as untested, with
    # one exception: an absent permutation_null is a cap (SUPPORTED at most),
    # not a FRAGILE gap — only an explicitly UNTESTED null forces FRAGILE.
    untested_canonical = sorted(
        n for n in CANONICAL_ALTERNATIVES if n not in status_by_name and n != "permutation_null"
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
