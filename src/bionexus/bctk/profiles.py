"""Fail-closed BNS protocol profile projections for BCTK diagnostics.

Profiles are adoption units, not certification tiers.  They answer which parts
of the public BNS contract have target-bound evidence and deliberately avoid an
overall score that could hide an unassessed mandatory dimension.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from bionexus.bctk.spec import ConformanceDimension, DimensionResult, DimensionStatus


class ProfileStatus(str, Enum):
    PASS = "PASS"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    FAIL = "FAIL"
    NOT_ASSESSED = "NOT_ASSESSED"


@dataclass(frozen=True)
class ProtocolProfile:
    profile_id: str
    title: str
    required_dimensions: tuple[ConformanceDimension, ...]


@dataclass(frozen=True)
class ProfileResult:
    profile_id: str
    status: ProfileStatus
    dimension_statuses: Mapping[str, str]
    reasons: tuple[str, ...]
    certification_effect: str = "NONE"

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "status": self.status.value,
            "dimension_statuses": dict(self.dimension_statuses),
            "reasons": list(self.reasons),
            "certification_effect": self.certification_effect,
        }


PROFILE_CATALOG: Mapping[str, ProtocolProfile] = {
    "BNS-Core": ProtocolProfile(
        "BNS-Core",
        "Scientific ABI and input invariants",
        (
            ConformanceDimension.BIOLOGICAL_SEMANTICS,
            ConformanceDimension.INPUT_STATE_HONESTY,
            ConformanceDimension.BACKEND_IDENTITY,
            ConformanceDimension.ABSTENTION,
        ),
    ),
    "BNS-Warrant": ProtocolProfile(
        "BNS-Warrant",
        "Evidence ceilings, claims, abstention, and remediation",
        (
            ConformanceDimension.CLAIM_WARRANT,
            ConformanceDimension.ABSTENTION,
            ConformanceDimension.FAILURE_HANDLING,
        ),
    ),
    "BNS-Provenance": ProtocolProfile(
        "BNS-Provenance",
        "Artifact binding, backend identity, and provenance interoperability",
        (ConformanceDimension.PROVENANCE, ConformanceDimension.BACKEND_IDENTITY),
    ),
    "BNS-Agent": ProtocolProfile(
        "BNS-Agent",
        "Host behavior and host-invariant warrant semantics",
        (
            ConformanceDimension.CROSS_HOST_CONSISTENCY,
            ConformanceDimension.CLAIM_WARRANT,
            ConformanceDimension.ABSTENTION,
        ),
    ),
    "BNS-Validation": ProtocolProfile(
        "BNS-Validation",
        "Failure challenge, validation, and evidence transport",
        (
            ConformanceDimension.FAILURE_HANDLING,
            ConformanceDimension.CROSS_HOST_CONSISTENCY,
            ConformanceDimension.PROVENANCE,
        ),
    ),
}


def _status_for(profile: ProtocolProfile, dimensions: Mapping[str, DimensionResult]) -> ProfileResult:
    observed: dict[str, str] = {}
    reasons: list[str] = []
    statuses: list[DimensionStatus] = []
    for dimension in profile.required_dimensions:
        result = dimensions.get(dimension.value)
        if result is None:
            observed[dimension.value] = ProfileStatus.NOT_ASSESSED.value
            reasons.append(f"missing mandatory dimension: {dimension.value}")
            continue
        observed[dimension.value] = result.status.value
        statuses.append(result.status)
        if result.status in {DimensionStatus.NOT_ASSESSED, DimensionStatus.SKIP}:
            reasons.append(f"mandatory dimension not assessed: {dimension.value}")
        elif result.status == DimensionStatus.NOT_APPLICABLE:
            reasons.append(f"mandatory dimension cannot be N/A: {dimension.value}")
        elif result.status == DimensionStatus.FAIL:
            reasons.append(f"mandatory dimension failed: {dimension.value}")

    if len(statuses) != len(profile.required_dimensions) or any(
        status in {DimensionStatus.NOT_ASSESSED, DimensionStatus.SKIP, DimensionStatus.NOT_APPLICABLE}
        for status in statuses
    ):
        status = ProfileStatus.NOT_ASSESSED
    elif any(item == DimensionStatus.FAIL for item in statuses):
        status = ProfileStatus.FAIL
    elif any(item == DimensionStatus.WARN for item in statuses):
        status = ProfileStatus.PASS_WITH_WARNINGS
    else:
        status = ProfileStatus.PASS
    return ProfileResult(profile.profile_id, status, observed, tuple(reasons))


def evaluate_protocol_profiles(
    dimensions: Mapping[str, DimensionResult],
    profile_ids: Sequence[str] | None = None,
) -> dict[str, ProfileResult]:
    """Project dimension evidence into independently adoptable BNS profiles."""
    requested = tuple(profile_ids or PROFILE_CATALOG.keys())
    unknown = sorted(set(requested) - set(PROFILE_CATALOG))
    if unknown:
        raise ValueError("unknown BNS profiles: " + ", ".join(unknown))

    results = {profile_id: _status_for(PROFILE_CATALOG[profile_id], dimensions) for profile_id in requested}
    if profile_ids is None:
        child_statuses = [result.status for result in results.values()]
        if any(status == ProfileStatus.NOT_ASSESSED for status in child_statuses):
            full_status = ProfileStatus.NOT_ASSESSED
        elif any(status == ProfileStatus.FAIL for status in child_statuses):
            full_status = ProfileStatus.FAIL
        elif any(status == ProfileStatus.PASS_WITH_WARNINGS for status in child_statuses):
            full_status = ProfileStatus.PASS_WITH_WARNINGS
        else:
            full_status = ProfileStatus.PASS
        results["BNS-Full"] = ProfileResult(
            "BNS-Full",
            full_status,
            {profile_id: result.status.value for profile_id, result in results.items()},
            tuple(
                f"child profile {profile_id}: {result.status.value}"
                for profile_id, result in results.items()
                if result.status != ProfileStatus.PASS
            ),
        )
    return results
