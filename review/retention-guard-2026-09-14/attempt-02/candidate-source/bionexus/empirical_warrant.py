"""Profile-conditioned empirical calibration for scientific warrants.

This module deliberately separates three operations that a static rule engine
usually conflates:

1. identify the empirical regime in which a score is being interpreted;
2. resolve a reviewed calibration profile for that exact regime; and
3. compare the observed score with the resolved, provenance-bound threshold.

There is no permissive global-threshold fallback.  Missing context, pending
profiles, reference-domain mismatch, and ambiguous matches are first-class
resolution outcomes and therefore cannot silently produce positive warrants.

Calibration fitting produces CANDIDATE profiles only.  Activation is a human
review action represented by an APPROVED profile with independent validation
evidence and a reviewer attestation.  SHA-256 fields provide reproducibility
and tamper-evident identifiers; they are not electronic signatures or GxP
records.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from pathlib import Path
from statistics import NormalDist
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

DEFAULT_REGISTRY_PATH = Path(__file__).parent / "data" / "empirical_calibration_registry.json"
_SHA256_RE_LENGTH = 64


class CalibrationError(ValueError):
    """Raised when calibration data or a requested fit is invalid."""


class ComparisonDirection(str, Enum):
    """How a score must compare with its calibrated threshold."""

    AT_LEAST = "AT_LEAST"
    AT_MOST = "AT_MOST"


class CalibrationReviewStatus(str, Enum):
    """Governance state of a calibration profile."""

    LEGACY_UNCALIBRATED = "LEGACY_UNCALIBRATED"
    CANDIDATE = "CANDIDATE"
    APPROVED = "APPROVED"
    RETIRED = "RETIRED"


class CalibrationResolutionStatus(str, Enum):
    """Whether a threshold was resolved for the declared empirical regime."""

    RESOLVED = "RESOLVED"
    INSUFFICIENT_CONTEXT = "INSUFFICIENT_CONTEXT"
    NO_MATCH = "NO_MATCH"
    PROFILE_NOT_APPROVED = "PROFILE_NOT_APPROVED"
    DOMAIN_MISMATCH = "DOMAIN_MISMATCH"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID_SCORE = "INVALID_SCORE"


@dataclass(frozen=True)
class CalibrationContext:
    """Declared empirical regime for one annotation warrant evaluation.

    ``evidence_sources`` is keyed by metric name because reference mapping,
    marker panels, doublet detection, and cross-method agreement commonly come
    from different scorers.  ``default_evidence_source`` is only a convenience
    for workflows where one versioned pipeline owns every metric.
    """

    tissue: Optional[str] = None
    platform: Optional[str] = None
    reference: Optional[str] = None
    task: Optional[str] = None
    evidence_sources: Mapping[str, str] = field(default_factory=dict)
    default_evidence_source: Optional[str] = None
    reference_domain_match: Optional[bool] = None
    state_geometry: str = "discrete"  # discrete | continuous | unknown
    population_scope: str = "closed_set"  # closed_set | rare | open_set | unknown

    def evidence_source_for(self, metric: str) -> Optional[str]:
        return self.evidence_sources.get(metric) or self.default_evidence_source

    def to_dict(self, metric: Optional[str] = None) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "tissue": self.tissue,
            "platform": self.platform,
            "reference": self.reference,
            "task": self.task,
            "evidence_sources": dict(self.evidence_sources),
            "default_evidence_source": self.default_evidence_source,
            "reference_domain_match": self.reference_domain_match,
            "state_geometry": self.state_geometry,
            "population_scope": self.population_scope,
        }
        if metric is not None:
            data["resolved_evidence_source"] = self.evidence_source_for(metric)
        return data


@dataclass(frozen=True)
class EmpiricalEvidence:
    """Benchmark evidence supporting one profile and one decision rule."""

    evidence_id: str
    dataset_id: str
    source_uri: str
    source_sha256: str
    sample_size: int
    positive_outcomes: int
    negative_outcomes: int
    outcome_definition: str
    estimator: str
    validation_partition: str
    independent_validation: bool
    observed_precision: float
    precision_interval: Tuple[float, float]
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["precision_interval"] = list(self.precision_interval)
        return data


@dataclass(frozen=True)
class ReviewerApproval:
    """Human approval required before a profile may issue positive warrants."""

    reviewer_id: str
    reviewed_at: str
    decision: str
    scope: str
    attestation_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationProfile:
    """A versioned threshold tied to an explicit empirical regime."""

    profile_id: str
    version: str
    metric: str
    direction: ComparisonDirection
    threshold: float
    tissues: Tuple[str, ...]
    platforms: Tuple[str, ...]
    references: Tuple[str, ...]
    tasks: Tuple[str, ...]
    evidence_sources: Tuple[str, ...]
    review_status: CalibrationReviewStatus
    evidence: Tuple[EmpiricalEvidence, ...] = ()
    approvals: Tuple[ReviewerApproval, ...] = ()
    applicability_notes: str = ""
    known_failures: Tuple[str, ...] = ()
    supersedes: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "metric": self.metric,
            "direction": self.direction.value,
            "threshold": self.threshold,
            "regime": {
                "tissues": list(self.tissues),
                "platforms": list(self.platforms),
                "references": list(self.references),
                "tasks": list(self.tasks),
                "evidence_sources": list(self.evidence_sources),
            },
            "review_status": self.review_status.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "approvals": [item.to_dict() for item in self.approvals],
            "applicability_notes": self.applicability_notes,
            "known_failures": list(self.known_failures),
            "supersedes": self.supersedes,
            "metadata": dict(self.metadata),
        }

    @property
    def fingerprint_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    @property
    def specificity(self) -> int:
        dimensions = (
            self.tissues,
            self.platforms,
            self.references,
            self.tasks,
            self.evidence_sources,
        )
        return sum(1 for values in dimensions if "*" not in {_norm(v) for v in values})

    def validation_issues(self) -> List[str]:
        issues: List[str] = []
        if not self.profile_id or not self.version or not self.metric:
            issues.append("profile_id, version, and metric are required")
        if not math.isfinite(self.threshold) or not 0.0 <= self.threshold <= 1.0:
            issues.append("threshold must be finite and within [0, 1]")
        for name, values in (
            ("tissues", self.tissues),
            ("platforms", self.platforms),
            ("references", self.references),
            ("tasks", self.tasks),
            ("evidence_sources", self.evidence_sources),
        ):
            if not values:
                issues.append(f"{name} must declare at least one value or '*'")
        if self.review_status == CalibrationReviewStatus.APPROVED:
            independent = [item for item in self.evidence if item.independent_validation]
            if not independent:
                issues.append("APPROVED profile requires independent validation evidence")
            if not self.approvals:
                issues.append("APPROVED profile requires at least one reviewer approval")
            for item in independent:
                if not _looks_like_sha256(item.source_sha256):
                    issues.append(f"evidence {item.evidence_id} has invalid source_sha256")
                lo, hi = item.precision_interval
                if not (0.0 <= lo <= item.observed_precision <= hi <= 1.0):
                    issues.append(f"evidence {item.evidence_id} has invalid precision interval")
                if item.sample_size <= 0 or item.positive_outcomes < 0 or item.negative_outcomes < 0:
                    issues.append(f"evidence {item.evidence_id} has invalid outcome counts")
            for approval in self.approvals:
                if approval.decision != "APPROVE" or not _looks_like_sha256(approval.attestation_sha256):
                    issues.append(f"approval by {approval.reviewer_id} is invalid")
        return issues


@dataclass(frozen=True)
class CalibrationResolution:
    """Audit-friendly result of resolving one metric's threshold."""

    metric: str
    status: CalibrationResolutionStatus
    context: Mapping[str, Any]
    reason: str
    registry_version: str
    registry_sha256: str
    profile_id: Optional[str] = None
    profile_version: Optional[str] = None
    profile_sha256: Optional[str] = None
    threshold: Optional[float] = None
    direction: Optional[ComparisonDirection] = None
    candidate_profile_ids: Tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.status == CalibrationResolutionStatus.RESOLVED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "status": self.status.value,
            "context": dict(self.context),
            "reason": self.reason,
            "registry_version": self.registry_version,
            "registry_sha256": self.registry_sha256,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_sha256": self.profile_sha256,
            "threshold": self.threshold,
            "direction": self.direction.value if self.direction else None,
            "candidate_profile_ids": list(self.candidate_profile_ids),
        }


@dataclass(frozen=True)
class MetricAssessment:
    """Result of applying a resolved empirical threshold to one score."""

    metric: str
    score: Optional[float]
    passed: Optional[bool]
    resolution: CalibrationResolution

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric,
            "score": self.score,
            "passed": self.passed,
            "resolution": self.resolution.to_dict(),
        }


@dataclass(frozen=True)
class CalibrationObservation:
    """One labelled calibration or held-out validation observation."""

    score: float
    outcome_supported: bool
    partition: str  # calibration | validation
    cohort_id: str


@dataclass(frozen=True)
class CalibrationFitReceipt:
    """Reproducible receipt for a candidate threshold fit."""

    method: str
    target_precision_lower_bound: float
    confidence_level: float
    minimum_selected: int
    calibration_selected: int
    calibration_precision: float
    calibration_precision_lower_bound: float
    validation_selected: int
    validation_precision: float
    validation_precision_lower_bound: float
    observations_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _norm(value: Any) -> str:
    return str(value).strip().casefold().replace("-", "_").replace(" ", "_")


def _looks_like_sha256(value: str) -> bool:
    return len(value) == _SHA256_RE_LENGTH and all(c in "0123456789abcdefABCDEF" for c in value)


def _canonical_sha256(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _matches(declared: Sequence[str], observed: Optional[str]) -> bool:
    normalized = {_norm(value) for value in declared}
    return "*" in normalized or (observed is not None and _norm(observed) in normalized)


def _profile_from_dict(data: Mapping[str, Any]) -> CalibrationProfile:
    regime = data.get("regime", {})
    evidence = tuple(
        EmpiricalEvidence(
            evidence_id=item["evidence_id"],
            dataset_id=item["dataset_id"],
            source_uri=item["source_uri"],
            source_sha256=item["source_sha256"],
            sample_size=int(item["sample_size"]),
            positive_outcomes=int(item["positive_outcomes"]),
            negative_outcomes=int(item["negative_outcomes"]),
            outcome_definition=item["outcome_definition"],
            estimator=item["estimator"],
            validation_partition=item["validation_partition"],
            independent_validation=bool(item["independent_validation"]),
            observed_precision=float(item["observed_precision"]),
            precision_interval=tuple(float(v) for v in item["precision_interval"]),
            generated_at=item.get("generated_at", ""),
        )
        for item in data.get("evidence", [])
    )
    approvals = tuple(ReviewerApproval(**item) for item in data.get("approvals", []))
    return CalibrationProfile(
        profile_id=data["profile_id"],
        version=data["version"],
        metric=data["metric"],
        direction=ComparisonDirection(data["direction"]),
        threshold=float(data["threshold"]),
        tissues=tuple(regime.get("tissues", ())),
        platforms=tuple(regime.get("platforms", ())),
        references=tuple(regime.get("references", ())),
        tasks=tuple(regime.get("tasks", ())),
        evidence_sources=tuple(regime.get("evidence_sources", ())),
        review_status=CalibrationReviewStatus(data["review_status"]),
        evidence=evidence,
        approvals=approvals,
        applicability_notes=data.get("applicability_notes", ""),
        known_failures=tuple(data.get("known_failures", ())),
        supersedes=data.get("supersedes"),
        metadata=data.get("metadata", {}),
    )


class CalibrationRegistry:
    """Resolve only reviewed profiles; never fall back to a global constant."""

    def __init__(
        self,
        profiles: Sequence[CalibrationProfile] = (),
        *,
        registry_version: str = "in-memory",
        registry_metadata: Optional[Mapping[str, Any]] = None,
        registry_sha256: Optional[str] = None,
    ) -> None:
        self.profiles = tuple(profiles)
        self.registry_version = registry_version
        self.registry_metadata = dict(registry_metadata or {})
        self.registry_sha256 = registry_sha256 or _canonical_sha256(
            {
                "registry_version": registry_version,
                "profiles": [profile.to_dict() for profile in self.profiles],
                "metadata": self.registry_metadata,
            }
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CalibrationRegistry":
        profiles = tuple(_profile_from_dict(item) for item in data.get("profiles", []))
        return cls(
            profiles,
            registry_version=str(data.get("registry_version", "unknown")),
            registry_metadata=data.get("metadata", {}),
            registry_sha256=_canonical_sha256(data),
        )

    @classmethod
    def load(cls, path: Union[str, Path] = DEFAULT_REGISTRY_PATH) -> "CalibrationRegistry":
        registry_path = Path(path)
        data = json.loads(registry_path.read_text(encoding="utf-8"))
        return cls.from_dict(data)

    def inventory(self) -> Dict[str, Any]:
        counts = {status.value: 0 for status in CalibrationReviewStatus}
        invalid: Dict[str, List[str]] = {}
        for profile in self.profiles:
            counts[profile.review_status.value] += 1
            issues = profile.validation_issues()
            if issues:
                invalid[profile.profile_id] = issues
        return {
            "registry_version": self.registry_version,
            "registry_sha256": self.registry_sha256,
            "profile_count": len(self.profiles),
            "status_counts": counts,
            "invalid_profiles": invalid,
            "metadata": dict(self.registry_metadata),
        }

    def resolve(self, metric: str, context: CalibrationContext) -> CalibrationResolution:
        context_dict = context.to_dict(metric)
        evidence_source = context.evidence_source_for(metric)
        missing = [
            name
            for name, value in (
                ("tissue", context.tissue),
                ("platform", context.platform),
                ("reference", context.reference),
                ("task", context.task),
                ("evidence_source", evidence_source),
            )
            if not value
        ]
        if missing:
            return self._unresolved(
                metric,
                CalibrationResolutionStatus.INSUFFICIENT_CONTEXT,
                context_dict,
                f"Missing calibration context: {', '.join(missing)}.",
            )

        if metric == "reference_mapping" and context.reference_domain_match is False:
            return self._unresolved(
                metric,
                CalibrationResolutionStatus.DOMAIN_MISMATCH,
                context_dict,
                "Reference mapping score is not interpretable as identity support because the target and reference domains mismatch.",
            )

        matches = [
            profile
            for profile in self.profiles
            if profile.metric == metric
            and _matches(profile.tissues, context.tissue)
            and _matches(profile.platforms, context.platform)
            and _matches(profile.references, context.reference)
            and _matches(profile.tasks, context.task)
            and _matches(profile.evidence_sources, evidence_source)
            and profile.review_status != CalibrationReviewStatus.RETIRED
        ]
        if not matches:
            return self._unresolved(
                metric,
                CalibrationResolutionStatus.NO_MATCH,
                context_dict,
                "No calibration profile covers the declared empirical regime; no threshold was applied.",
            )

        approved = [profile for profile in matches if profile.review_status == CalibrationReviewStatus.APPROVED]
        valid_approved = [profile for profile in approved if not profile.validation_issues()]
        if not valid_approved:
            return self._unresolved(
                metric,
                CalibrationResolutionStatus.PROFILE_NOT_APPROVED,
                context_dict,
                "Matching profiles exist, but none has valid APPROVED evidence and reviewer attestation.",
                tuple(sorted(profile.profile_id for profile in matches)),
            )

        top_specificity = max(profile.specificity for profile in valid_approved)
        finalists = [profile for profile in valid_approved if profile.specificity == top_specificity]
        distinct_rules = {(profile.threshold, profile.direction.value) for profile in finalists}
        if len(distinct_rules) != 1:
            return self._unresolved(
                metric,
                CalibrationResolutionStatus.AMBIGUOUS,
                context_dict,
                "Equally specific approved profiles prescribe conflicting decision rules; resolution failed closed.",
                tuple(sorted(profile.profile_id for profile in finalists)),
            )

        # Equivalent duplicate rules are deterministic; choose the stable ID.
        selected = sorted(finalists, key=lambda profile: (profile.profile_id, profile.version))[-1]
        return CalibrationResolution(
            metric=metric,
            status=CalibrationResolutionStatus.RESOLVED,
            context=context_dict,
            reason=(
                f"Resolved approved empirical profile {selected.profile_id}@{selected.version} "
                f"at specificity {selected.specificity}/5."
            ),
            registry_version=self.registry_version,
            registry_sha256=self.registry_sha256,
            profile_id=selected.profile_id,
            profile_version=selected.version,
            profile_sha256=selected.fingerprint_sha256,
            threshold=selected.threshold,
            direction=selected.direction,
            candidate_profile_ids=tuple(sorted(profile.profile_id for profile in finalists)),
        )

    def assess(self, metric: str, score: Optional[float], context: CalibrationContext) -> MetricAssessment:
        resolution = self.resolve(metric, context)
        if score is None:
            return MetricAssessment(metric=metric, score=None, passed=None, resolution=resolution)
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(float(score)) or not 0 <= float(score) <= 1:
            invalid = replace(
                resolution,
                status=CalibrationResolutionStatus.INVALID_SCORE,
                reason="Score must be a finite number within [0, 1]; no warrant comparison was made.",
                threshold=None,
                direction=None,
                profile_id=None,
                profile_version=None,
                profile_sha256=None,
            )
            return MetricAssessment(metric=metric, score=None, passed=None, resolution=invalid)
        if not resolution.resolved:
            return MetricAssessment(metric=metric, score=float(score), passed=None, resolution=resolution)
        assert resolution.threshold is not None and resolution.direction is not None
        if resolution.direction == ComparisonDirection.AT_LEAST:
            passed = float(score) >= resolution.threshold
        else:
            passed = float(score) <= resolution.threshold
        return MetricAssessment(metric=metric, score=float(score), passed=passed, resolution=resolution)

    def _unresolved(
        self,
        metric: str,
        status: CalibrationResolutionStatus,
        context: Mapping[str, Any],
        reason: str,
        candidate_profile_ids: Tuple[str, ...] = (),
    ) -> CalibrationResolution:
        return CalibrationResolution(
            metric=metric,
            status=status,
            context=context,
            reason=reason,
            registry_version=self.registry_version,
            registry_sha256=self.registry_sha256,
            candidate_profile_ids=candidate_profile_ids,
        )


_DEFAULT_REGISTRY: Optional[CalibrationRegistry] = None


def default_calibration_registry() -> CalibrationRegistry:
    """Load the packaged registry once for runtime warrant decisions."""

    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = CalibrationRegistry.load()
    return _DEFAULT_REGISTRY


def _wilson_lower_bound(successes: int, total: int, confidence_level: float) -> float:
    if total <= 0:
        return 0.0
    z = NormalDist().inv_cdf(confidence_level)
    p = successes / total
    z2 = z * z
    centre = p + z2 / (2 * total)
    spread = z * math.sqrt((p * (1 - p) + z2 / (4 * total)) / total)
    return max(0.0, (centre - spread) / (1 + z2 / total))


def _selected(
    observations: Iterable[CalibrationObservation], threshold: float, direction: ComparisonDirection
) -> List[CalibrationObservation]:
    if direction == ComparisonDirection.AT_LEAST:
        return [item for item in observations if item.score >= threshold]
    return [item for item in observations if item.score <= threshold]


def fit_candidate_profile(
    *,
    profile_template: CalibrationProfile,
    observations: Sequence[CalibrationObservation],
    target_precision_lower_bound: float,
    confidence_level: float,
    minimum_selected: int,
    source_uri: str,
    generated_at: str = "",
) -> Tuple[CalibrationProfile, CalibrationFitReceipt]:
    """Fit a deterministic precision-controlled threshold on calibration data.

    The least stringent threshold meeting the caller-declared lower-bound
    criterion is selected, which maximizes coverage subject to that criterion.
    A held-out validation partition is mandatory.  The returned profile remains
    CANDIDATE even when validation clears the target; human review is a separate
    governance action.
    """

    if not 0 < target_precision_lower_bound <= 1:
        raise CalibrationError("target_precision_lower_bound must be within (0, 1]")
    if not 0.5 < confidence_level < 1:
        raise CalibrationError("confidence_level must be within (0.5, 1)")
    if minimum_selected <= 0:
        raise CalibrationError("minimum_selected must be positive")
    if profile_template.review_status == CalibrationReviewStatus.APPROVED:
        raise CalibrationError("an APPROVED profile cannot be overwritten by automatic fitting")

    calibration = [item for item in observations if item.partition == "calibration"]
    validation = [item for item in observations if item.partition == "validation"]
    if not calibration or not validation:
        raise CalibrationError("both calibration and held-out validation partitions are required")
    for item in observations:
        if not math.isfinite(item.score) or not 0 <= item.score <= 1:
            raise CalibrationError("all observation scores must be finite and within [0, 1]")
        if item.partition not in {"calibration", "validation"}:
            raise CalibrationError("partition must be 'calibration' or 'validation'")

    thresholds = sorted({item.score for item in calibration})
    if profile_template.direction == ComparisonDirection.AT_MOST:
        thresholds.reverse()

    eligible: List[Tuple[int, float, float, int]] = []
    for threshold in thresholds:
        selected = _selected(calibration, threshold, profile_template.direction)
        if len(selected) < minimum_selected:
            continue
        successes = sum(item.outcome_supported for item in selected)
        precision = successes / len(selected)
        lower = _wilson_lower_bound(successes, len(selected), confidence_level)
        if lower >= target_precision_lower_bound:
            eligible.append((len(selected), threshold, precision, successes))
    if not eligible:
        raise CalibrationError("no candidate threshold met the declared precision lower-bound criterion")

    # Maximize coverage. Threshold ordering is only a deterministic tie break.
    eligible.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    cal_n, threshold, cal_precision, cal_successes = eligible[0]
    val_selected = _selected(validation, threshold, profile_template.direction)
    val_n = len(val_selected)
    val_successes = sum(item.outcome_supported for item in val_selected)
    val_precision = val_successes / val_n if val_n else 0.0
    val_lower = _wilson_lower_bound(val_successes, val_n, confidence_level)

    observation_payload = [asdict(item) for item in observations]
    observations_sha256 = _canonical_sha256(observation_payload)
    evidence = EmpiricalEvidence(
        evidence_id=f"{profile_template.profile_id}:{profile_template.version}:held_out",
        dataset_id="+".join(sorted({item.cohort_id for item in validation})),
        source_uri=source_uri,
        source_sha256=observations_sha256,
        sample_size=len(validation),
        positive_outcomes=val_successes,
        negative_outcomes=val_n - val_successes,
        outcome_definition="independently adjudicated support outcome supplied to fit_candidate_profile",
        estimator="precision with one-sided Wilson lower confidence bound",
        validation_partition="validation",
        independent_validation=True,
        observed_precision=val_precision,
        precision_interval=(val_lower, 1.0),
        generated_at=generated_at,
    )
    candidate = replace(
        profile_template,
        threshold=threshold,
        review_status=CalibrationReviewStatus.CANDIDATE,
        evidence=(evidence,),
        approvals=(),
        metadata={
            **dict(profile_template.metadata),
            "fit_target_precision_lower_bound": target_precision_lower_bound,
            "fit_confidence_level": confidence_level,
            "fit_minimum_selected": minimum_selected,
            "held_out_validation_clears_target": val_n >= minimum_selected and val_lower >= target_precision_lower_bound,
        },
    )
    receipt = CalibrationFitReceipt(
        method="coverage-maximizing threshold subject to one-sided Wilson precision lower bound",
        target_precision_lower_bound=target_precision_lower_bound,
        confidence_level=confidence_level,
        minimum_selected=minimum_selected,
        calibration_selected=cal_n,
        calibration_precision=cal_precision,
        calibration_precision_lower_bound=_wilson_lower_bound(cal_successes, cal_n, confidence_level),
        validation_selected=val_n,
        validation_precision=val_precision,
        validation_precision_lower_bound=val_lower,
        observations_sha256=observations_sha256,
    )
    return candidate, receipt

