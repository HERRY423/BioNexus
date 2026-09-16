"""Empirical-gold contracts for the Spatial Alternative Explanation Battery.

The program is intentionally limited to Xenium, CosMx, and MERSCOPE. It binds
real platform exports, preregistered donor/FOV-disjoint partitions, executed
battery receipts, and independent adjudication records before a generic
calibration profile may even become CANDIDATE. It never auto-approves a profile
and it contains no platform threshold defaults.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from jsonschema import Draft202012Validator

from bionexus.empirical_warrant import (
    CalibrationContext,
    CalibrationFitReceipt,
    CalibrationObservation,
    CalibrationProfile,
    CalibrationReviewStatus,
    ComparisonDirection,
    fit_candidate_profile,
)
from bionexus.trust_evidence import (
    EvidenceAttestation,
    TrustDecision,
    TrustRegistry,
    verify_attestation,
)

SPATIAL_GOLD_ROOT_ENV = "BIONEXUS_SPATIAL_GOLD_ROOT"
SPATIAL_GOLD_PROGRAM_VERSION = "0.1.0"
DEFAULT_SPATIAL_GOLD_ROOT = Path(__file__).resolve().parents[2] / "calibration" / "spatial-empirical-gold-standard"
SPATIAL_GOLD_PLATFORMS: Tuple[str, ...] = ("xenium", "cosmx", "merscope")
SPATIAL_CONTROL_METRICS: Dict[str, str] = {
    "segmentation_uncertainty": "spatial.segmentation_effect_retention",
    "transcript_leakage": "spatial.leakage_effect_retention",
    "cell_size": "spatial.cell_size_adjusted_retention",
    "nuclear_eccentricity": "spatial.nuclear_eccentricity_adjusted_retention",
    "transcript_density": "spatial.transcript_density_adjusted_retention",
    "local_cell_density": "spatial.local_density_adjusted_retention",
    "contact_geometry": "spatial.contact_geometry_retention",
    "batch_fov": "spatial.batch_fov_stability",
    "neighborhood_radius": "spatial.radius_stability",
    "permutation_null": "spatial.permutation_p_value",
    "cell_label_perturbation": "spatial.cell_label_stability",
    "spatial_autocorrelation": "spatial.spatial_autocorrelation_null_p_value",
}
SPATIAL_METRIC_DIRECTIONS: Dict[str, ComparisonDirection] = {
    metric: (
        ComparisonDirection.AT_MOST
        if control in {"permutation_null", "spatial_autocorrelation"}
        else ComparisonDirection.AT_LEAST
    )
    for control, metric in SPATIAL_CONTROL_METRICS.items()
}
_SHA256_LENGTH = 64


class SpatialGoldError(ValueError):
    """Raised when a spatial empirical-gold contract fails closed."""


class ImagingSpatialPlatform(str, Enum):
    """Only platforms admitted to the empirical-gold program."""

    XENIUM = "xenium"
    COSMX = "cosmx"
    MERSCOPE = "merscope"


class SpatialGoldPartition(str, Enum):
    CALIBRATION = "calibration"
    VALIDATION = "validation"


@dataclass(frozen=True)
class ArtifactBinding:
    """Immutable external artifact declaration."""

    uri: str
    sha256: str
    media_type: str

    def validation_issues(self) -> Tuple[str, ...]:
        issues: list[str] = []
        if not self.uri or not self.media_type:
            issues.append("artifact uri and media_type are required")
        if not _looks_like_sha256(self.sha256):
            issues.append(f"artifact {self.uri!r} has invalid sha256")
        return tuple(issues)


@dataclass(frozen=True)
class SpatialGoldStudyManifest:
    """Preregistered, platform-specific study and held-out split contract."""

    study_id: str
    platform: ImagingSpatialPlatform
    platform_release: str
    tissue: str
    species: str
    panel_id: str
    task: str
    reference: str
    data_provenance: str
    dataset_artifacts: Tuple[ArtifactBinding, ...]
    calibration_donor_ids: Tuple[str, ...]
    validation_donor_ids: Tuple[str, ...]
    calibration_fov_ids: Tuple[str, ...]
    validation_fov_ids: Tuple[str, ...]
    segmentation_revision_ids: Tuple[str, ...]
    leakage_model_ids: Tuple[str, ...]
    metrics: Tuple[str, ...]
    evidence_sources: Mapping[str, str]
    preregistration_artifact: ArtifactBinding
    adjudication_protocol_artifact: ArtifactBinding
    independent_adjudicator_ids: Tuple[str, ...]
    outcome_definition: str
    schema_version: str = "bionexus.spatial-empirical-gold-study.v1"
    source_uri: str = ""
    source_sha256: str = ""

    @classmethod
    def load(
        cls,
        path: Path | str,
        *,
        program_root: Optional[Path | str] = None,
    ) -> "SpatialGoldStudyManifest":
        manifest_path = Path(path).resolve()
        raw = manifest_path.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SpatialGoldError(f"invalid study manifest JSON: {exc}") from exc
        root = resolve_spatial_gold_root(program_root)
        _validate_json(data, root / "schemas" / "study-manifest.schema.json", "study manifest")
        manifest = cls.from_dict(
            data,
            source_uri=str(manifest_path),
            source_sha256=hashlib.sha256(raw).hexdigest(),
        )
        manifest.require_valid()
        return manifest

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        source_uri: str = "",
        source_sha256: str = "",
    ) -> "SpatialGoldStudyManifest":
        return cls(
            schema_version=str(data.get("schema_version", "")),
            study_id=str(data.get("study_id", "")),
            platform=ImagingSpatialPlatform(str(data.get("platform", ""))),
            platform_release=str(data.get("platform_release", "")),
            tissue=str(data.get("tissue", "")),
            species=str(data.get("species", "")),
            panel_id=str(data.get("panel_id", "")),
            task=str(data.get("task", "")),
            reference=str(data.get("reference", "")),
            data_provenance=str(data.get("data_provenance", "")),
            dataset_artifacts=tuple(ArtifactBinding(**item) for item in data.get("dataset_artifacts", [])),
            calibration_donor_ids=tuple(data.get("calibration_donor_ids", [])),
            validation_donor_ids=tuple(data.get("validation_donor_ids", [])),
            calibration_fov_ids=tuple(data.get("calibration_fov_ids", [])),
            validation_fov_ids=tuple(data.get("validation_fov_ids", [])),
            segmentation_revision_ids=tuple(data.get("segmentation_revision_ids", [])),
            leakage_model_ids=tuple(data.get("leakage_model_ids", [])),
            metrics=tuple(data.get("metrics", [])),
            evidence_sources=dict(data.get("evidence_sources", {})),
            preregistration_artifact=ArtifactBinding(**data.get("preregistration_artifact", {})),
            adjudication_protocol_artifact=ArtifactBinding(**data.get("adjudication_protocol_artifact", {})),
            independent_adjudicator_ids=tuple(data.get("independent_adjudicator_ids", [])),
            outcome_definition=str(data.get("outcome_definition", "")),
            source_uri=source_uri,
            source_sha256=source_sha256,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "study_id": self.study_id,
            "platform": self.platform.value,
            "platform_release": self.platform_release,
            "tissue": self.tissue,
            "species": self.species,
            "panel_id": self.panel_id,
            "task": self.task,
            "reference": self.reference,
            "data_provenance": self.data_provenance,
            "dataset_artifacts": [asdict(item) for item in self.dataset_artifacts],
            "calibration_donor_ids": list(self.calibration_donor_ids),
            "validation_donor_ids": list(self.validation_donor_ids),
            "calibration_fov_ids": list(self.calibration_fov_ids),
            "validation_fov_ids": list(self.validation_fov_ids),
            "segmentation_revision_ids": list(self.segmentation_revision_ids),
            "leakage_model_ids": list(self.leakage_model_ids),
            "metrics": list(self.metrics),
            "evidence_sources": dict(self.evidence_sources),
            "preregistration_artifact": asdict(self.preregistration_artifact),
            "adjudication_protocol_artifact": asdict(self.adjudication_protocol_artifact),
            "independent_adjudicator_ids": list(self.independent_adjudicator_ids),
            "outcome_definition": self.outcome_definition,
        }

    @property
    def fingerprint_sha256(self) -> str:
        return _canonical_sha256(self.to_dict())

    def context_for(self, metric: str) -> CalibrationContext:
        if metric not in self.metrics:
            raise SpatialGoldError(f"metric is not preregistered for study {self.study_id}: {metric}")
        return CalibrationContext(
            tissue=self.tissue,
            platform=self.platform.value,
            reference=self.reference,
            task=self.task,
            evidence_sources={metric: self.evidence_sources[metric]},
        )

    def validation_issues(self) -> Tuple[str, ...]:
        issues: list[str] = []
        required_text = {
            "study_id": self.study_id,
            "platform_release": self.platform_release,
            "tissue": self.tissue,
            "species": self.species,
            "panel_id": self.panel_id,
            "task": self.task,
            "reference": self.reference,
            "outcome_definition": self.outcome_definition,
        }
        for name, value in required_text.items():
            if not value or value == "*":
                issues.append(f"{name} must be explicit and non-wildcard")
        if self.data_provenance != "REAL_PLATFORM_EXPORT":
            issues.append("data_provenance must be REAL_PLATFORM_EXPORT; synthetic or simulated evidence is forbidden")
        for name, values in (
            ("dataset_artifacts", self.dataset_artifacts),
            ("calibration_donor_ids", self.calibration_donor_ids),
            ("validation_donor_ids", self.validation_donor_ids),
            ("calibration_fov_ids", self.calibration_fov_ids),
            ("validation_fov_ids", self.validation_fov_ids),
            ("metrics", self.metrics),
            ("independent_adjudicator_ids", self.independent_adjudicator_ids),
        ):
            if not values:
                issues.append(f"{name} must not be empty")
            if len(values) != len(set(values)):
                issues.append(f"{name} must not contain duplicates")
        donor_overlap = sorted(set(self.calibration_donor_ids) & set(self.validation_donor_ids))
        if donor_overlap:
            issues.append(f"calibration and validation donors overlap: {donor_overlap}")
        fov_overlap = sorted(set(self.calibration_fov_ids) & set(self.validation_fov_ids))
        if fov_overlap:
            issues.append(f"calibration and validation FOVs overlap: {fov_overlap}")
        unknown_metrics = sorted(set(self.metrics) - set(SPATIAL_METRIC_DIRECTIONS))
        if unknown_metrics:
            issues.append(f"metrics are outside the Spatial Alternative Explanation Battery: {unknown_metrics}")
        missing_sources = sorted(set(self.metrics) - set(self.evidence_sources))
        extra_sources = sorted(set(self.evidence_sources) - set(self.metrics))
        if missing_sources or extra_sources:
            issues.append(f"evidence_sources mismatch; missing={missing_sources}, extra={extra_sources}")
        if any(not value or value == "*" for value in self.evidence_sources.values()):
            issues.append("evidence_sources must be explicit and versioned")
        if SPATIAL_CONTROL_METRICS["segmentation_uncertainty"] in self.metrics:
            if len(self.segmentation_revision_ids) < 2:
                issues.append("segmentation calibration requires at least two declared segmentation revisions")
        if SPATIAL_CONTROL_METRICS["transcript_leakage"] in self.metrics and not self.leakage_model_ids:
            issues.append("transcript-leakage calibration requires at least one versioned leakage model")
        for artifact in (*self.dataset_artifacts, self.preregistration_artifact, self.adjudication_protocol_artifact):
            issues.extend(artifact.validation_issues())
        if not self.source_uri or not _looks_like_sha256(self.source_sha256):
            issues.append("study manifest must be loaded from immutable bytes before fitting")
        return tuple(issues)

    def require_valid(self) -> None:
        issues = self.validation_issues()
        if issues:
            raise SpatialGoldError("; ".join(issues))


@dataclass(frozen=True)
class SpatialGoldObservation:
    """One adjudicated battery metric from one donor/FOV partition."""

    record_id: str
    study_id: str
    platform: ImagingSpatialPlatform
    metric: str
    score: float
    outcome_supported: bool
    partition: SpatialGoldPartition
    donor_id: str
    fov_id: str
    battery_run_sha256: str
    adjudication_record_sha256: str

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SpatialGoldObservation":
        return cls(
            record_id=str(data.get("record_id", "")),
            study_id=str(data.get("study_id", "")),
            platform=ImagingSpatialPlatform(str(data.get("platform", ""))),
            metric=str(data.get("metric", "")),
            score=float(data.get("score")),
            outcome_supported=bool(data.get("outcome_supported")),
            partition=SpatialGoldPartition(str(data.get("partition", ""))),
            donor_id=str(data.get("donor_id", "")),
            fov_id=str(data.get("fov_id", "")),
            battery_run_sha256=str(data.get("battery_run_sha256", "")),
            adjudication_record_sha256=str(data.get("adjudication_record_sha256", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["platform"] = self.platform.value
        data["partition"] = self.partition.value
        return data


@dataclass(frozen=True)
class SpatialGoldObservationSet:
    """Immutable observation artifact verified against a study manifest."""

    study_manifest_sha256: str
    records: Tuple[SpatialGoldObservation, ...]
    source_uri: str
    source_sha256: str
    schema_version: str = "bionexus.spatial-empirical-gold-observations.v1"

    @classmethod
    def load(
        cls,
        path: Path | str,
        manifest: SpatialGoldStudyManifest,
        *,
        program_root: Optional[Path | str] = None,
    ) -> "SpatialGoldObservationSet":
        manifest.require_valid()
        source_path = Path(path).resolve()
        raw = source_path.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SpatialGoldError(f"invalid observation-set JSON: {exc}") from exc
        root = resolve_spatial_gold_root(program_root)
        _validate_json(data, root / "schemas" / "observations.schema.json", "observation set")
        observation_set = cls(
            schema_version=str(data.get("schema_version", "")),
            study_manifest_sha256=str(data.get("study_manifest_sha256", "")),
            records=tuple(SpatialGoldObservation.from_dict(item) for item in data.get("records", [])),
            source_uri=str(source_path),
            source_sha256=hashlib.sha256(raw).hexdigest(),
        )
        observation_set.require_valid(manifest)
        return observation_set

    @property
    def fingerprint_sha256(self) -> str:
        return _canonical_sha256([record.to_dict() for record in self.records])

    def validation_issues(self, manifest: SpatialGoldStudyManifest) -> Tuple[str, ...]:
        issues: list[str] = []
        if self.study_manifest_sha256 != manifest.source_sha256:
            issues.append("observation set is not bound to the exact study manifest bytes")
        if not self.records:
            issues.append("observation set must contain records")
        if not self.source_uri or not _looks_like_sha256(self.source_sha256):
            issues.append("observation set must be loaded from immutable bytes")
        record_ids: set[str] = set()
        covered: set[tuple[str, str]] = set()
        for record in self.records:
            if not record.record_id or record.record_id in record_ids:
                issues.append(f"record_id must be non-empty and unique: {record.record_id!r}")
            record_ids.add(record.record_id)
            if record.study_id != manifest.study_id or record.platform != manifest.platform:
                issues.append(f"record {record.record_id} study/platform does not match manifest")
            if record.metric not in manifest.metrics:
                issues.append(f"record {record.record_id} metric was not preregistered")
            if not math.isfinite(record.score) or not 0 <= record.score <= 1:
                issues.append(f"record {record.record_id} score must be finite within [0, 1]")
            if not _looks_like_sha256(record.battery_run_sha256):
                issues.append(f"record {record.record_id} has invalid battery_run_sha256")
            if not _looks_like_sha256(record.adjudication_record_sha256):
                issues.append(f"record {record.record_id} has invalid adjudication_record_sha256")
            if record.partition == SpatialGoldPartition.CALIBRATION:
                if record.donor_id not in manifest.calibration_donor_ids:
                    issues.append(f"record {record.record_id} donor is outside calibration partition")
                if record.fov_id not in manifest.calibration_fov_ids:
                    issues.append(f"record {record.record_id} FOV is outside calibration partition")
            else:
                if record.donor_id not in manifest.validation_donor_ids:
                    issues.append(f"record {record.record_id} donor is outside validation partition")
                if record.fov_id not in manifest.validation_fov_ids:
                    issues.append(f"record {record.record_id} FOV is outside validation partition")
            covered.add((record.metric, record.partition.value))
        expected = {
            (metric, partition.value)
            for metric in manifest.metrics
            for partition in (SpatialGoldPartition.CALIBRATION, SpatialGoldPartition.VALIDATION)
        }
        missing = sorted(expected - covered)
        if missing:
            issues.append(f"every metric requires calibration and held-out validation records; missing={missing}")
        return tuple(issues)

    def require_valid(self, manifest: SpatialGoldStudyManifest) -> None:
        issues = self.validation_issues(manifest)
        if issues:
            raise SpatialGoldError("; ".join(issues))


@dataclass(frozen=True)
class SpatialArtifactVerificationReceipt:
    """Byte-level verification of every study evidence artifact."""

    study_id: str
    study_manifest_sha256: str
    artifact_sha256_by_uri: Mapping[str, str]
    observation_artifact_sha256: str = ""
    record_artifact_sha256_by_key: Mapping[str, str] = field(default_factory=dict)
    verified: bool = True

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(
            {
                "study_id": self.study_id,
                "study_manifest_sha256": self.study_manifest_sha256,
                "artifact_sha256_by_uri": dict(sorted(self.artifact_sha256_by_uri.items())),
                "observation_artifact_sha256": self.observation_artifact_sha256,
                "record_artifact_sha256_by_key": dict(sorted(self.record_artifact_sha256_by_key.items())),
                "verified": self.verified,
            }
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "study_id": self.study_id,
            "study_manifest_sha256": self.study_manifest_sha256,
            "artifact_sha256_by_uri": dict(sorted(self.artifact_sha256_by_uri.items())),
            "observation_artifact_sha256": self.observation_artifact_sha256,
            "record_artifact_sha256_by_key": dict(sorted(self.record_artifact_sha256_by_key.items())),
            "verified": self.verified,
            "receipt_sha256": self.receipt_sha256,
        }


@dataclass(frozen=True)
class SpatialGoldFitReceipt:
    """Gold-program bindings around a generic candidate fit receipt."""

    study_id: str
    platform: str
    metric: str
    study_manifest_sha256: str
    observation_artifact_sha256: str
    observation_records_sha256: str
    artifact_verification_receipt_sha256: str
    calibration_donor_ids: Tuple[str, ...]
    validation_donor_ids: Tuple[str, ...]
    calibration_fov_ids: Tuple[str, ...]
    validation_fov_ids: Tuple[str, ...]
    generic_fit: CalibrationFitReceipt
    review_status: str = "CANDIDATE"
    approval_eligible: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["generic_fit"] = self.generic_fit.to_dict()
        return data


class SpatialGoldProgram:
    """Zero-threshold coverage registry for the three-platform program."""

    def __init__(
        self,
        document: Mapping[str, Any],
        *,
        root: Path,
        source_uri: str = "",
        source_sha256: str = "",
    ) -> None:
        self.document = dict(document)
        self.root = root
        self.source_uri = source_uri
        self.source_sha256 = source_sha256
        self.program_version = str(self.document.get("program_version", ""))
        self.status = str(self.document.get("status", ""))
        self.program_sha256 = _canonical_sha256(self.document)
        self._validate()

    @classmethod
    def load(cls, root: Optional[Path | str] = None) -> "SpatialGoldProgram":
        program_root = resolve_spatial_gold_root(root)
        program_path = program_root / "program.json"
        try:
            raw = program_path.read_bytes()
            document = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SpatialGoldError(f"cannot read spatial empirical-gold program: {exc}") from exc
        _validate_json(document, program_root / "schemas" / "program.schema.json", "program registry")
        return cls(
            document,
            root=program_root,
            source_uri=str(program_path.resolve()),
            source_sha256=hashlib.sha256(raw).hexdigest(),
        )

    def _validate(self) -> None:
        platforms = tuple(self.document.get("supported_platforms", []))
        if platforms != SPATIAL_GOLD_PLATFORMS:
            raise SpatialGoldError("spatial empirical-gold platform scope must be exactly Xenium, CosMx, MERSCOPE")
        platform_programs = self.document.get("platform_programs", {})
        if set(platform_programs) != set(SPATIAL_GOLD_PLATFORMS):
            raise SpatialGoldError("platform_programs must cover exactly the three admitted platforms")
        alternatives = self.document.get("alternative_explanations", {})
        actual_metrics = {name: item.get("metric") for name, item in alternatives.items()}
        if actual_metrics != SPATIAL_CONTROL_METRICS:
            raise SpatialGoldError("program alternative-explanation metrics do not match the executable battery")
        for control, metric in SPATIAL_CONTROL_METRICS.items():
            expected_direction = SPATIAL_METRIC_DIRECTIONS[metric].value
            if alternatives[control].get("direction") != expected_direction:
                raise SpatialGoldError(f"program direction mismatch for {control}")
            if not alternatives[control].get("required_empirical_anchor"):
                raise SpatialGoldError(f"program empirical anchor is missing for {control}")
        if _contains_key(self.document, "threshold"):
            raise SpatialGoldError("the empirical-gold program registry must not contain threshold defaults")
        if self.document.get("approved_profiles") and self.status == "incomplete_not_claim_ready":
            raise SpatialGoldError("an incomplete program cannot list approved profiles")
        studies = tuple(self.document.get("studies", ()))
        study_ids = [str(item.get("study_id", "")) for item in studies]
        if len(study_ids) != len(set(study_ids)):
            raise SpatialGoldError("spatial empirical-gold study IDs must be unique")
        approved_profiles = tuple(self.document.get("approved_profiles", ()))
        profile_keys = [(str(item.get("profile_id", "")), str(item.get("version", ""))) for item in approved_profiles]
        if len(profile_keys) != len(set(profile_keys)):
            raise SpatialGoldError("spatial empirical-gold profile ID/version pairs must be unique")
        registered_studies = set(study_ids)
        for item in approved_profiles:
            if item.get("metric") not in SPATIAL_METRIC_DIRECTIONS:
                raise SpatialGoldError("approved profile metric is outside the executable spatial battery")
            binding_ids = {str(binding.get("study_id", "")) for binding in item.get("study_bindings", ())}
            if not binding_ids or not binding_ids <= registered_studies:
                raise SpatialGoldError("approved profile study bindings must reference registered studies")
            if any(
                study.get("platform") != item.get("platform")
                for study in studies
                if study.get("study_id") in binding_ids
            ):
                raise SpatialGoldError("approved profile and bound study platforms must match")
        for platform in SPATIAL_GOLD_PLATFORMS:
            declared = set(platform_programs[platform].get("approved_profile_ids", ()))
            active = {
                str(item.get("profile_id", ""))
                for item in approved_profiles
                if item.get("platform") == platform and item.get("status") == "ACTIVE"
            }
            if declared != active:
                raise SpatialGoldError(f"platform program approved_profile_ids mismatch for {platform}")

    def inventory(self) -> Dict[str, Any]:
        approved_pairs = {
            (str(item.get("platform", "")), str(item.get("metric", "")))
            for item in self.document.get("approved_profiles", ())
            if item.get("status") == "ACTIVE"
        }
        gaps = [
            {"platform": platform, "alternative_explanation": control, "metric": metric}
            for platform in SPATIAL_GOLD_PLATFORMS
            for control, metric in SPATIAL_CONTROL_METRICS.items()
            if (platform, metric) not in approved_pairs
        ]
        return {
            "program_version": self.program_version,
            "program_sha256": self.program_sha256,
            "status": self.status,
            "supported_platforms": list(SPATIAL_GOLD_PLATFORMS),
            "study_count": len(self.document.get("studies", [])),
            "approved_profile_count": len(self.document.get("approved_profiles", [])),
            "coverage_gap_count": len(gaps),
            "coverage_gaps": gaps,
            "claim_ready": self.status == "externally_validated" and not gaps,
        }


@dataclass(frozen=True)
class SpatialGoldProfileAuthorization:
    """Runtime decision for one exact Gold Program calibration profile."""

    authorized: bool
    status: str
    reasons: Tuple[str, ...]
    program_version: str
    program_sha256: str
    profile_id: str
    profile_version: str
    profile_sha256: str
    attestation_id: str = ""
    trust_decision: str = TrustDecision.NOT_ASSESSED.value
    study_ids: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "authorized": self.authorized,
            "status": self.status,
            "reasons": list(self.reasons),
            "program_version": self.program_version,
            "program_sha256": self.program_sha256,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_sha256": self.profile_sha256,
            "attestation_id": self.attestation_id,
            "trust_decision": self.trust_decision,
            "study_ids": list(self.study_ids),
        }


@dataclass(frozen=True)
class SpatialGoldRuntimeEvidence:
    """Host-owned materials verified before using a threshold.

    ``profile_artifact_paths`` is keyed by ``<profile_id>@<version>`` so an
    older artifact cannot satisfy a newer program membership entry.
    """

    program: SpatialGoldProgram
    trust_registry: TrustRegistry
    profile_artifact_paths: Mapping[str, Path | str]
    approval_attestations: Mapping[str, EvidenceAttestation]
    study_manifest_paths: Mapping[str, Path | str]
    at_time: Optional[datetime] = None

    def authorize(self, profile: CalibrationProfile) -> SpatialGoldProfileAuthorization:
        return verify_spatial_gold_profile_authorization(profile, self)


def verify_spatial_gold_profile_authorization(
    profile: CalibrationProfile,
    runtime_evidence: SpatialGoldRuntimeEvidence,
) -> SpatialGoldProfileAuthorization:
    """Verify program membership, real-study binding, signature, and revocation.

    The caller cannot promote a generic ``APPROVED`` profile by declaration.
    Authorization requires the exact profile artifact bytes, an active Gold
    Program entry, byte-bound real study manifests, and a trusted unrevoked
    ``spatial-gold-profile-approval`` attestation.
    """

    program = runtime_evidence.program
    profile_sha256 = profile.fingerprint_sha256
    base = {
        "program_version": program.program_version,
        "program_sha256": program.program_sha256,
        "profile_id": profile.profile_id,
        "profile_version": profile.version,
        "profile_sha256": profile_sha256,
    }

    def refused(
        status: str,
        *reasons: str,
        attestation_id: str = "",
        trust_decision: str = TrustDecision.NOT_ASSESSED.value,
        study_ids: Tuple[str, ...] = (),
    ) -> SpatialGoldProfileAuthorization:
        return SpatialGoldProfileAuthorization(
            authorized=False,
            status=status,
            reasons=tuple(reasons),
            attestation_id=attestation_id,
            trust_decision=trust_decision,
            study_ids=study_ids,
            **base,
        )

    if not program.source_uri or not _looks_like_sha256(program.source_sha256):
        return refused(
            "GOLD_PROGRAM_BYTES_REQUIRED",
            "Gold Program registry must be loaded from immutable bytes",
        )
    try:
        raw_program = Path(program.source_uri).read_bytes()
        program_document = json.loads(raw_program.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return refused(
            "GOLD_PROGRAM_VERIFICATION_FAILED",
            f"cannot re-read Gold Program registry bytes: {exc}",
        )
    if (
        hashlib.sha256(raw_program).hexdigest() != program.source_sha256
        or program_document != program.document
        or _canonical_sha256(program_document) != program.program_sha256
    ):
        return refused(
            "GOLD_PROGRAM_BINDING_MISMATCH",
            "Gold Program registry bytes no longer match the authorized program object",
        )
    if profile.review_status != CalibrationReviewStatus.APPROVED or profile.validation_issues():
        return refused(
            "PROFILE_NOT_VALID_APPROVED",
            "profile is not a structurally valid APPROVED calibration profile",
        )
    if len(profile.platforms) != 1 or profile.platforms[0] not in SPATIAL_GOLD_PLATFORMS:
        return refused(
            "PROFILE_OUT_OF_GOLD_SCOPE",
            "profile must bind exactly one admitted imaging-spatial platform",
        )
    platform_program = program.document.get("platform_programs", {}).get(profile.platforms[0], {})
    if program.status != "externally_validated" or platform_program.get("status") != "EXTERNALLY_VALIDATED":
        return refused(
            "GOLD_PROGRAM_NOT_EXTERNALLY_VALIDATED",
            "positive runtime warrant requires externally validated program and platform status",
        )

    matches = [
        item
        for item in program.document.get("approved_profiles", [])
        if item.get("profile_id") == profile.profile_id and item.get("version") == profile.version
    ]
    if len(matches) != 1:
        return refused(
            "PROFILE_NOT_IN_GOLD_PROGRAM",
            "exactly one active Gold Program membership record is required",
        )
    entry = matches[0]
    study_bindings = tuple(entry.get("study_bindings", ()))
    study_ids = tuple(str(item.get("study_id", "")) for item in study_bindings)
    expected_entry = {
        "status": "ACTIVE",
        "profile_sha256": profile_sha256,
        "platform": profile.platforms[0],
        "metric": profile.metric,
    }
    mismatches = [name for name, expected in expected_entry.items() if entry.get(name) != expected]
    if mismatches or not study_bindings or any(not study_id for study_id in study_ids):
        return refused(
            "GOLD_PROGRAM_MEMBERSHIP_MISMATCH",
            "Gold Program entry is inactive, mismatched, or lacks study bindings: " + ", ".join(mismatches),
            study_ids=study_ids,
        )
    if profile.metadata.get("spatial_gold_study_bindings") != list(study_bindings):
        return refused(
            "PROFILE_STUDY_BINDING_MISMATCH",
            "profile metadata is not bound to the exact Gold Program study receipts",
            study_ids=study_ids,
        )

    registered_studies = {str(item.get("study_id", "")): item for item in program.document.get("studies", [])}
    for binding in study_bindings:
        study_id = str(binding.get("study_id", ""))
        study_entry = registered_studies.get(study_id)
        if (
            study_entry is None
            or study_entry.get("status") != "BYTE_VERIFIED"
            or study_entry.get("platform") != profile.platforms[0]
            or study_entry.get("manifest_sha256") != binding.get("study_manifest_sha256")
        ):
            return refused(
                "STUDY_NOT_ACTIVE_BYTE_VERIFIED",
                f"study {study_id!r} is absent, inactive, or not bound to the exact manifest digest",
                study_ids=study_ids,
            )
        manifest_path = runtime_evidence.study_manifest_paths.get(study_id)
        if manifest_path is None:
            return refused(
                "STUDY_MANIFEST_BYTES_REQUIRED",
                f"study manifest bytes were not supplied for {study_id!r}",
                study_ids=study_ids,
            )
        try:
            manifest = SpatialGoldStudyManifest.load(manifest_path, program_root=program.root)
        except (OSError, SpatialGoldError, ValueError) as exc:
            return refused(
                "STUDY_MANIFEST_VERIFICATION_FAILED",
                f"study {study_id!r} manifest failed verification: {exc}",
                study_ids=study_ids,
            )
        if (
            manifest.study_id != study_id
            or manifest.platform.value != profile.platforms[0]
            or manifest.source_sha256 != binding.get("study_manifest_sha256")
            or manifest.data_provenance != "REAL_PLATFORM_EXPORT"
            or profile.metric not in manifest.metrics
            or profile.direction != SPATIAL_METRIC_DIRECTIONS[profile.metric]
            or profile.tissues != (manifest.tissue,)
            or profile.references != (manifest.reference,)
            or profile.tasks != (manifest.task,)
            or profile.evidence_sources != (manifest.evidence_sources[profile.metric],)
            or profile.metadata.get("platform_release") != manifest.platform_release
            or profile.metadata.get("panel_id") != manifest.panel_id
            or profile.metadata.get("species") != manifest.species
        ):
            return refused(
                "STUDY_MANIFEST_BINDING_MISMATCH",
                f"study {study_id!r} does not bind the profile regime and real-data contract",
                study_ids=study_ids,
            )

    profile_runtime_key = f"{profile.profile_id}@{profile.version}"
    profile_path = runtime_evidence.profile_artifact_paths.get(profile_runtime_key)
    if profile_path is None:
        return refused(
            "PROFILE_ARTIFACT_BYTES_REQUIRED",
            f"the exact approved profile artifact bytes were not supplied under {profile_runtime_key!r}",
            study_ids=study_ids,
        )
    try:
        raw_profile = Path(profile_path).read_bytes()
        profile_document = json.loads(raw_profile.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return refused(
            "PROFILE_ARTIFACT_VERIFICATION_FAILED",
            f"cannot read the approved profile artifact: {exc}",
            study_ids=study_ids,
        )
    profile_artifact_sha256 = hashlib.sha256(raw_profile).hexdigest()
    if (
        profile_artifact_sha256 != entry.get("profile_artifact_sha256")
        or str(entry.get("profile_artifact_uri", "")) == ""
        or _canonical_sha256(profile_document) != profile_sha256
        or profile_document != profile.to_dict()
    ):
        return refused(
            "PROFILE_ARTIFACT_BINDING_MISMATCH",
            "profile bytes, canonical profile content, and Gold Program membership do not agree",
            study_ids=study_ids,
        )

    attestation_id = str(entry.get("approval_attestation_id", ""))
    attestation = runtime_evidence.approval_attestations.get(attestation_id)
    if attestation is None:
        return refused(
            "APPROVAL_ATTESTATION_REQUIRED",
            "the Gold Program approval attestation was not supplied",
            attestation_id=attestation_id,
            study_ids=study_ids,
        )
    expected_scope = {
        "program_version": program.program_version,
        "program_sha256": program.program_sha256,
        "platform": profile.platforms[0],
        "metric": profile.metric,
    }
    expected_claims = {
        "review_status": "APPROVED",
        "profile_sha256": profile_sha256,
        "study_bindings": list(study_bindings),
        "record_artifact_bytes_verified": True,
    }
    attestation_mismatch = (
        attestation.predicate_type != "spatial-gold-profile-approval"
        or attestation.subject.subject_type != "spatial-calibration-profile"
        or attestation.subject.subject_id != profile.profile_id
        or attestation.subject.version != profile.version
        or attestation.subject.artifact_uri != entry.get("profile_artifact_uri")
        or attestation.subject.artifact_sha256 != profile_artifact_sha256
        or dict(attestation.scope) != expected_scope
        or dict(attestation.claims) != expected_claims
    )
    if attestation_mismatch:
        return refused(
            "APPROVAL_ATTESTATION_BINDING_MISMATCH",
            "approval attestation does not bind the exact program, profile, studies, and byte-verified records",
            attestation_id=attestation_id,
            study_ids=study_ids,
        )
    try:
        verification = verify_attestation(
            attestation,
            runtime_evidence.trust_registry,
            artifact_path=profile_path,
            at_time=runtime_evidence.at_time,
        )
    except OSError as exc:
        return refused(
            "APPROVAL_ATTESTATION_ARTIFACT_UNREADABLE",
            f"approved profile artifact could not be re-read during signature verification: {exc}",
            attestation_id=attestation_id,
            study_ids=study_ids,
        )
    if not verification.accepted:
        return refused(
            "APPROVAL_ATTESTATION_NOT_TRUSTED",
            *verification.reasons,
            attestation_id=attestation_id,
            trust_decision=verification.decision.value,
            study_ids=study_ids,
        )
    return SpatialGoldProfileAuthorization(
        authorized=True,
        status="AUTHORIZED",
        reasons=(
            "Gold Program membership, real-study manifests, profile bytes, trusted signature, and revocation state verified",
        ),
        attestation_id=attestation_id,
        trust_decision=verification.decision.value,
        study_ids=study_ids,
        **base,
    )


def resolve_spatial_gold_root(root: Optional[Path | str] = None) -> Path:
    candidate = (
        Path(root) if root is not None else Path(os.environ.get(SPATIAL_GOLD_ROOT_ENV, DEFAULT_SPATIAL_GOLD_ROOT))
    )
    resolved = candidate.expanduser().resolve()
    if not resolved.is_dir():
        raise SpatialGoldError(
            f"spatial empirical-gold program not found at {resolved}; set {SPATIAL_GOLD_ROOT_ENV} explicitly"
        )
    return resolved


def is_spatial_gold_platform(platform: Optional[str]) -> bool:
    return platform is not None and _norm(platform) in SPATIAL_GOLD_PLATFORMS


def fit_spatial_candidate_profile(
    *,
    manifest: SpatialGoldStudyManifest,
    observation_set: SpatialGoldObservationSet,
    artifact_verification: SpatialArtifactVerificationReceipt,
    metric: str,
    profile_template: CalibrationProfile,
    target_precision_lower_bound: float,
    confidence_level: float,
    minimum_selected: int,
    generated_at: str = "",
) -> Tuple[CalibrationProfile, SpatialGoldFitReceipt]:
    """Fit one platform-specific CANDIDATE after all gold-program gates pass."""

    manifest.require_valid()
    try:
        reloaded_manifest = SpatialGoldStudyManifest.load(manifest.source_uri)
    except (OSError, SpatialGoldError, ValueError) as exc:
        raise SpatialGoldError(f"cannot re-read study manifest bytes: {exc}") from exc
    if reloaded_manifest.source_sha256 != manifest.source_sha256 or reloaded_manifest.to_dict() != manifest.to_dict():
        raise SpatialGoldError("study manifest bytes no longer match the supplied manifest object")
    observation_set.require_valid(manifest)
    try:
        reloaded_observations = SpatialGoldObservationSet.load(observation_set.source_uri, manifest)
    except (OSError, SpatialGoldError, ValueError) as exc:
        raise SpatialGoldError(f"cannot re-read observation-set bytes: {exc}") from exc
    if (
        reloaded_observations.source_sha256 != observation_set.source_sha256
        or reloaded_observations.study_manifest_sha256 != observation_set.study_manifest_sha256
        or reloaded_observations.records != observation_set.records
    ):
        raise SpatialGoldError("observation-set bytes no longer match the supplied observation object")
    _require_artifact_verification(manifest, observation_set, artifact_verification)
    if metric not in manifest.metrics:
        raise SpatialGoldError(f"metric is not preregistered: {metric}")
    expected_profile = {
        "metric": metric,
        "direction": SPATIAL_METRIC_DIRECTIONS[metric],
        "tissues": (manifest.tissue,),
        "platforms": (manifest.platform.value,),
        "references": (manifest.reference,),
        "tasks": (manifest.task,),
        "evidence_sources": (manifest.evidence_sources[metric],),
    }
    for name, expected in expected_profile.items():
        if getattr(profile_template, name) != expected:
            raise SpatialGoldError(f"profile template {name} must exactly match the preregistered study regime")
    if profile_template.review_status == CalibrationReviewStatus.APPROVED:
        raise SpatialGoldError("the gold-program fitter cannot accept an APPROVED template")
    records = [record for record in observation_set.records if record.metric == metric]
    generic_observations = [
        CalibrationObservation(
            score=record.score,
            outcome_supported=record.outcome_supported,
            partition=record.partition.value,
            cohort_id=f"{manifest.study_id}:{record.donor_id}:{record.fov_id}",
        )
        for record in records
    ]
    candidate, generic_receipt = fit_candidate_profile(
        profile_template=profile_template,
        observations=generic_observations,
        target_precision_lower_bound=target_precision_lower_bound,
        confidence_level=confidence_level,
        minimum_selected=minimum_selected,
        source_uri=observation_set.source_uri,
        generated_at=generated_at,
    )
    study_binding = {
        "study_id": manifest.study_id,
        "study_manifest_sha256": manifest.source_sha256,
        "observation_artifact_sha256": observation_set.source_sha256,
        "observation_records_sha256": observation_set.fingerprint_sha256,
        "artifact_verification_receipt_sha256": artifact_verification.receipt_sha256,
    }
    candidate = replace(
        candidate,
        metadata={
            **dict(candidate.metadata),
            "spatial_empirical_gold_program": SPATIAL_GOLD_PROGRAM_VERSION,
            "study_id": manifest.study_id,
            "platform_release": manifest.platform_release,
            "panel_id": manifest.panel_id,
            "species": manifest.species,
            "study_manifest_sha256": manifest.source_sha256,
            "observation_artifact_sha256": observation_set.source_sha256,
            "artifact_verification_receipt_sha256": artifact_verification.receipt_sha256,
            "spatial_gold_study_bindings": [study_binding],
            "battery_receipts_bound": True,
            "record_artifact_bytes_verified": True,
            "donor_holdout_disjoint": True,
            "fov_holdout_disjoint": True,
            "platform_pooling": False,
            "approval_eligible": False,
            "claim_status": "candidate_not_approved",
        },
    )
    receipt = SpatialGoldFitReceipt(
        study_id=manifest.study_id,
        platform=manifest.platform.value,
        metric=metric,
        study_manifest_sha256=manifest.source_sha256,
        observation_artifact_sha256=observation_set.source_sha256,
        observation_records_sha256=observation_set.fingerprint_sha256,
        artifact_verification_receipt_sha256=artifact_verification.receipt_sha256,
        calibration_donor_ids=manifest.calibration_donor_ids,
        validation_donor_ids=manifest.validation_donor_ids,
        calibration_fov_ids=manifest.calibration_fov_ids,
        validation_fov_ids=manifest.validation_fov_ids,
        generic_fit=generic_receipt,
    )
    return candidate, receipt


def verify_spatial_gold_artifacts(
    manifest: SpatialGoldStudyManifest,
    artifact_paths: Mapping[str, Path | str],
    *,
    observation_set: Optional[SpatialGoldObservationSet] = None,
    record_artifact_paths: Optional[Mapping[str, Path | str]] = None,
) -> SpatialArtifactVerificationReceipt:
    """Read and hash study plus per-record battery/adjudication artifacts.

    A study-only receipt is useful for inspection but is deliberately marked
    incomplete. Candidate fitting requires an observation set and exact bytes
    for every ``<record_id>:battery_run`` and
    ``<record_id>:adjudication_record`` binding.
    """

    manifest.require_valid()
    try:
        reloaded_manifest = SpatialGoldStudyManifest.load(manifest.source_uri)
    except (OSError, SpatialGoldError, ValueError) as exc:
        raise SpatialGoldError(f"cannot re-read study manifest bytes: {exc}") from exc
    if reloaded_manifest.source_sha256 != manifest.source_sha256 or reloaded_manifest.to_dict() != manifest.to_dict():
        raise SpatialGoldError("study manifest bytes no longer match the supplied manifest object")
    artifacts = (
        *manifest.dataset_artifacts,
        manifest.preregistration_artifact,
        manifest.adjudication_protocol_artifact,
    )
    expected_by_uri = {artifact.uri: artifact.sha256 for artifact in artifacts}
    if len(expected_by_uri) != len(artifacts):
        raise SpatialGoldError("study artifact URIs must be unique")
    supplied_uris = set(artifact_paths)
    expected_uris = set(expected_by_uri)
    if supplied_uris != expected_uris:
        raise SpatialGoldError(
            f"artifact path inventory mismatch; missing={sorted(expected_uris - supplied_uris)}, "
            f"extra={sorted(supplied_uris - expected_uris)}"
        )
    verified: Dict[str, str] = {}
    for uri in sorted(expected_by_uri):
        path = Path(artifact_paths[uri]).resolve()
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            raise SpatialGoldError(f"cannot read study artifact {uri}: {exc}") from exc
        if digest != expected_by_uri[uri]:
            raise SpatialGoldError(f"study artifact SHA-256 mismatch: {uri}")
        verified[uri] = digest
    if observation_set is None:
        if record_artifact_paths:
            raise SpatialGoldError("record artifact paths require an observation set")
        return SpatialArtifactVerificationReceipt(
            study_id=manifest.study_id,
            study_manifest_sha256=manifest.source_sha256,
            artifact_sha256_by_uri=verified,
            verified=False,
        )

    observation_set.require_valid(manifest)
    try:
        reloaded_observations = SpatialGoldObservationSet.load(observation_set.source_uri, manifest)
    except (OSError, SpatialGoldError, ValueError) as exc:
        raise SpatialGoldError(f"cannot re-read observation-set bytes: {exc}") from exc
    if (
        reloaded_observations.source_sha256 != observation_set.source_sha256
        or reloaded_observations.study_manifest_sha256 != observation_set.study_manifest_sha256
        or reloaded_observations.records != observation_set.records
    ):
        raise SpatialGoldError("observation-set bytes no longer match the supplied observation object")
    expected_record_digests = {
        f"{record.record_id}:battery_run": record.battery_run_sha256 for record in observation_set.records
    }
    expected_record_digests.update(
        {
            f"{record.record_id}:adjudication_record": record.adjudication_record_sha256
            for record in observation_set.records
        }
    )
    supplied_record_paths = dict(record_artifact_paths or {})
    supplied_keys = set(supplied_record_paths)
    expected_keys = set(expected_record_digests)
    if supplied_keys != expected_keys:
        raise SpatialGoldError(
            f"record artifact path inventory mismatch; missing={sorted(expected_keys - supplied_keys)}, "
            f"extra={sorted(supplied_keys - expected_keys)}"
        )
    records_by_id = {record.record_id: record for record in observation_set.records}
    verified_records: Dict[str, str] = {}
    for key in sorted(expected_record_digests):
        path = Path(supplied_record_paths[key]).resolve()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise SpatialGoldError(f"cannot read record artifact {key}: {exc}") from exc
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_record_digests[key]:
            raise SpatialGoldError(f"record artifact SHA-256 mismatch: {key}")
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SpatialGoldError(f"record artifact is not valid JSON: {key}: {exc}") from exc
        record_id, artifact_kind = key.rsplit(":", 1)
        _verify_record_artifact_semantics(
            document,
            artifact_kind=artifact_kind,
            record=records_by_id[record_id],
            manifest=manifest,
        )
        verified_records[key] = digest

    return SpatialArtifactVerificationReceipt(
        study_id=manifest.study_id,
        study_manifest_sha256=manifest.source_sha256,
        artifact_sha256_by_uri=verified,
        observation_artifact_sha256=observation_set.source_sha256,
        record_artifact_sha256_by_key=verified_records,
    )


def _verify_record_artifact_semantics(
    document: Any,
    *,
    artifact_kind: str,
    record: SpatialGoldObservation,
    manifest: SpatialGoldStudyManifest,
) -> None:
    """Bind verified record bytes to their declared scientific record."""

    if not isinstance(document, Mapping):
        raise SpatialGoldError(f"record artifact must be a JSON object: {record.record_id}:{artifact_kind}")
    common_expected: Dict[str, Any] = {
        "record_id": record.record_id,
        "study_id": record.study_id,
        "platform": record.platform.value,
        "metric": record.metric,
        "donor_id": record.donor_id,
        "fov_id": record.fov_id,
        "partition": record.partition.value,
    }
    if artifact_kind == "battery_run":
        expected = {
            "schema_version": "bionexus.spatial-gold-battery-record.v1",
            **common_expected,
            "score": record.score,
        }
    elif artifact_kind == "adjudication_record":
        expected = {
            "schema_version": "bionexus.spatial-gold-adjudication-record.v1",
            **common_expected,
            "outcome_supported": record.outcome_supported,
            "protocol_sha256": manifest.adjudication_protocol_artifact.sha256,
        }
        adjudicator_id = document.get("adjudicator_id")
        if adjudicator_id not in manifest.independent_adjudicator_ids:
            raise SpatialGoldError(
                f"record artifact semantic mismatch: {record.record_id}:{artifact_kind}:adjudicator_id"
            )
    else:  # pragma: no cover - inventory construction makes this unreachable
        raise SpatialGoldError(f"unsupported record artifact kind: {artifact_kind}")
    mismatches = [name for name, value in expected.items() if document.get(name) != value]
    if mismatches:
        raise SpatialGoldError(
            f"record artifact semantic mismatch: {record.record_id}:{artifact_kind}:" + ",".join(mismatches)
        )


def _require_artifact_verification(
    manifest: SpatialGoldStudyManifest,
    observation_set: SpatialGoldObservationSet,
    receipt: SpatialArtifactVerificationReceipt,
) -> None:
    expected = {
        artifact.uri: artifact.sha256
        for artifact in (
            *manifest.dataset_artifacts,
            manifest.preregistration_artifact,
            manifest.adjudication_protocol_artifact,
        )
    }
    expected_records = {
        f"{record.record_id}:battery_run": record.battery_run_sha256 for record in observation_set.records
    }
    expected_records.update(
        {
            f"{record.record_id}:adjudication_record": record.adjudication_record_sha256
            for record in observation_set.records
        }
    )
    if (
        not receipt.verified
        or receipt.study_id != manifest.study_id
        or receipt.study_manifest_sha256 != manifest.source_sha256
        or dict(receipt.artifact_sha256_by_uri) != expected
        or receipt.observation_artifact_sha256 != observation_set.source_sha256
        or dict(receipt.record_artifact_sha256_by_key) != expected_records
    ):
        raise SpatialGoldError(
            "candidate fitting requires matching byte-verified study, observation, battery-run, and adjudication artifacts"
        )


def _validate_json(value: Any, schema_path: Path, label: str) -> None:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpatialGoldError(f"cannot read {label} schema: {exc}") from exc
    errors = sorted(Draft202012Validator(schema).iter_errors(value), key=lambda error: list(error.path))
    if errors:
        raise SpatialGoldError(f"{label} schema violation: " + "; ".join(error.message for error in errors))


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, Mapping):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_key(item, key) for item in value)
    return False


def _looks_like_sha256(value: str) -> bool:
    return len(value) == _SHA256_LENGTH and all(character in "0123456789abcdef" for character in value)


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _norm(value: Any) -> str:
    return str(value).strip().casefold().replace("-", "_").replace(" ", "_")
