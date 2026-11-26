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
import re
import sys
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

SPATIAL_CONTROL_SCHEMA = "bionexus.spatial-control-result.v1"
SECTION_PROVENANCE_SCHEMA = "bionexus.spatial-section-origins.v1"
MIN_NULL_PERMUTATIONS = 999
BATTERY_PRODUCER = "bionexus.spatial-alternative-battery.v3"

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
    producer: str = "external_declaration"
    baseline_effect_sign: Optional[int] = None
    section_provenance_sha256: Optional[str] = None

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
    input_sha256: Optional[str] = None

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


def _verified_json(digest: Optional[str], artifacts: Mapping[str, bytes]) -> dict:
    if not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
        return {}
    raw = artifacts.get(digest.lower())
    if not isinstance(raw, bytes) or hashlib.sha256(raw).hexdigest() != digest.lower():
        return {}
    try:
        doc = json.loads(raw)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _finite_number(value: Any) -> bool:
    # JSON booleans are integers in Python, but cannot be effect estimates.
    return type(value) in (int, float) and abs(value) <= sys.float_info.max


def _valid_null(doc: dict) -> bool:
    n = doc.get("n_permutations")
    summary = doc.get("null_distribution_summary")
    if type(n) is not int or n < MIN_NULL_PERMUTATIONS or type(doc.get("random_seed")) is not int:
        return False
    if not isinstance(summary, dict):
        return False
    extrema = [summary.get(k) for k in ("min", "mean", "max")]
    return all(_finite_number(v) for v in extrema) and extrema[0] <= extrema[1] <= extrema[2]


def _external_control(
    name: str, item: ControlResult, artifacts: Mapping[str, bytes], input_sha256: Optional[str],
) -> ControlResult:
    doc = _verified_json(item.artifact_sha256, artifacts)
    fallback = ControlResult(
        name, "UNTESTED" if item.status == "UNTESTED" and not doc else "DECLARED",
        "A structured result bound to this input is required.", artifact_sha256=item.artifact_sha256,
    )
    if (not isinstance(input_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", input_sha256)
            or doc.get("schema") != SPATIAL_CONTROL_SCHEMA or doc.get("input_sha256") != input_sha256
            or not isinstance(doc.get("control"), str) or _canonical(doc["control"]) != name):
        return fallback
    interval = doc.get("adjusted_effect_interval")
    sign = doc.get("baseline_effect_sign")
    if (type(sign) is not int or sign not in (-1, 1)
            or not isinstance(interval, list) or len(interval) != 2 or not all(_finite_number(v) for v in interval)
            or interval[0] > interval[1]):
        fallback.note = "The adjusted effect interval or baseline direction is invalid for this observation."
        return fallback
    if name == "permutation_null" and not _valid_null(doc):
        fallback.note = "The permutation null requires at least 999 permutations, a seed and a finite null summary."
        return fallback
    low, high = interval
    survives = low > 0 if sign == 1 else high < 0
    statistic = doc.get("statistic")
    if statistic is not None and not _finite_number(statistic):
        return fallback
    return ControlResult(
        name, "TESTED" if survives else "FAILED", f"Adjusted interval [{low:g}, {high:g}], baseline sign {sign:+d}.",
        statistic, (low, high), item.artifact_sha256, "external_structured", sign,
    )


def _normalize_controls(
    controls: Optional[List[ControlResult] | Dict[str, str]], artifacts: Mapping[str, bytes],
    input_sha256: Optional[str], expected_sign: Optional[int],
) -> Dict[str, ControlResult]:
    if isinstance(controls, dict):
        controls = [ControlResult(name=k, status=v) for k, v in controls.items()]
    checked = []
    for item in controls or ():
        name = _canonical(item.name)
        if name != "sample_level_replication":
            checked.append(_external_control(name, item, artifacts, input_sha256))

    signs = {r.baseline_effect_sign for r in checked if r.baseline_effect_sign is not None}
    if expected_sign is None and len(signs) == 1:
        expected_sign = signs.pop()
    normalized: Dict[str, ControlResult] = {}
    priority = ("TESTED", "CONTROLLED", "DECLARED", "UNTESTED", "FAILED")
    for result in checked:
        interval = result.p_or_interval
        if isinstance(interval, tuple) and result.baseline_effect_sign != expected_sign:
            # An interval that includes zero fails for either orientation.
            if not interval[0] <= 0 <= interval[1]:
                result = replace(result, status="DECLARED", note="The baseline direction is unresolved for this control.")
        name = result.name
        if name not in normalized or priority.index(result.status) > priority.index(normalized[name].status):
            normalized[name] = result
    return normalized


def _sample_replication(
    obs: Optional[DataFrame], donor_col: Optional[str], section_col: Optional[str], group_col: Optional[str],
    sections_are_independent: bool, section_provenance_sha256: Optional[str], artifacts: Mapping[str, bytes],
) -> tuple[ControlResult, Dict[str, int]]:
    name = "sample_level_replication"
    if obs is None or obs.empty:
        return ControlResult(name, "UNTESTED", "Sample-level observations are missing.", producer="observed_metadata"), {}
    # Prefer the independent donor when sections are nested within donors.
    donors = (donor_col,) if donor_col is not None else ("donor", "donor_id")
    sections = (section_col,) if section_col is not None else ("section", "section_id", "slice", "slice_id")
    candidates = donors + sections
    unit = next((col for col in candidates if col in obs), None)
    if unit is None:
        return ControlResult(name, "UNTESTED", "Supply donor or tissue-section identifiers in obs.", producer="observed_metadata"), {}

    import pandas as pd

    units = obs[unit].astype("string").str.strip().replace("", pd.NA)
    grouped = group_col is not None and group_col in obs
    groups = obs[group_col].astype("string").str.strip().replace("", pd.NA) if grouped else "all"
    pairs = pd.DataFrame({"group": groups, "unit": units}).drop_duplicates()
    counts = {str(k): int(v) for k, v in pairs.groupby("group", observed=True)["unit"].nunique().items()}
    records = pairs.dropna().sort_values(["group", "unit"]).values.tolist()
    digest = hashlib.sha256(json.dumps([unit, group_col, records], ensure_ascii=False).encode()).hexdigest()
    if not counts or pairs.isna().any().any():
        return ControlResult(name, "UNTESTED", "Group or sample identifiers are incomplete.", producer="observed_metadata"), counts
    minimum = min(counts.values())
    if minimum < 2:
        status = "FAILED"
        note = f"Fewer than two {unit} units in a group. Limit the observation to a single-section or donor description."
    elif group_col is not None and not grouped:
        status = "UNTESTED"
        note = f"Group column {group_col!r} is missing. Group-specific replication could not be assessed."
    elif unit not in donors:
        provenance = _verified_json(section_provenance_sha256, artifacts)
        origins = provenance.get("section_to_donor")
        section_ids = set(units.dropna())
        mapped = [origins.get(section) for section in section_ids] if isinstance(origins, dict) else []
        independent = (
            sections_are_independent is True and provenance.get("schema") == SECTION_PROVENANCE_SCHEMA
            and len(mapped) == len(section_ids) and all(isinstance(v, str) and v.strip() for v in mapped)
            and len({v.strip() for v in mapped}) == len(section_ids)
        )
        status = "CONTROLLED" if independent else "DECLARED"
        note = ("Distinct donor origins verified for every observed section." if independent
                else "Sections may be nested in one donor. Independent donor origins have not been established.")
        if independent:
            digest = hashlib.sha256(f"{digest}{section_provenance_sha256}".encode()).hexdigest()
    else:
        status = "CONTROLLED"
        note = f"Observed at least two distinct {unit} units per group."
    return ControlResult(
        name, status, note, statistic=minimum, artifact_sha256=digest, producer="observed_metadata",
        section_provenance_sha256=section_provenance_sha256 if unit not in donors else None,
    ), counts


def assess_spatial_inference(
    observation: str,
    controls: Optional[List[ControlResult] | Dict[str, str]] = None,
    *,
    obs: Optional[DataFrame] = None,
    donor_col: Optional[str] = None,
    section_col: Optional[str] = None,
    group_col: Optional[str] = "condition",
    artifacts: Optional[Mapping[str, bytes]] = None,
    input_sha256: Optional[str] = None,
    baseline_effect_sign: Optional[int] = None,
    sections_are_independent: bool = False,
    section_provenance_sha256: Optional[str] = None,
) -> SpatialInferenceVerdict:
    """Derive each external control from its structured, input-bound effect interval.

    Supply original artifacts keyed by digest and the independently obtained SHA-256
    of the audited inputs. Supply claim-scoped rows (group_col=None for one cohort).
    """
    if baseline_effect_sign is not None and (type(baseline_effect_sign) is not int or baseline_effect_sign not in (-1, 1)):
        raise ValueError("baseline_effect_sign must be -1 or 1")
    results = _normalize_controls(controls, artifacts or {}, input_sha256, baseline_effect_sign)
    replication, counts = _sample_replication(
        obs, donor_col, section_col, group_col, sections_are_independent, section_provenance_sha256, artifacts or {},
    )
    return _spatial_verdict(observation, results, replication, counts, input_sha256)


def _spatial_verdict(
    observation: str, results: Dict[str, ControlResult], replication: ControlResult, counts: Dict[str, int],
    input_sha256: Optional[str],
) -> SpatialInferenceVerdict:
    has_controls = bool(results)
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
        input_sha256=input_sha256,
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
            verdict.notes.append("Some controls lack input-bound measurements or independent sample origins.")
        core_missing = [name for name in CORE_CONTROLS if name not in verdict.controlled]
        if core_missing:
            verdict.notes.append("Core confound controls outstanding: " + ", ".join(core_missing))
    elif "permutation_null" in verdict.controlled:
        verdict.verdict = "ROBUST"
    else:
        verdict.verdict = "SUPPORTED"
        verdict.notes.append("No permutation null recorded. Significance language stays capped at SUPPORTED.")
    return verdict
