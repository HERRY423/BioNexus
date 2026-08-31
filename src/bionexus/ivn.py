"""Independent Validation Network (BNS-023).

Deterministic accounting layer for the external-validation quotas that bound
what the three flagship capabilities may claim:

    >= 3 independent datasets  x  >= 2 external labs  x  >= 1 non-author reviewer

per flagship capability, plus capability-specific depth requirements:

* ``scrna.annotation_evidence`` — the counted datasets must collectively span
  cross-disease, cross-tissue, and cross-technology contexts.
* ``spatial.inference_validity`` — every counted dataset must carry an
  independent pathology-annotation or segmentation truth produced by a
  provider independent of BioNexus and blinded to system outputs.

The network is strictly fail-closed and honest by construction:

* datasets produced or authored by BioNexus authors never count;
* registered frameworks, lab slots, and reviewer slots never count — only
  entities whose status is ``VERIFIED`` with on-disk artifacts whose SHA-256
  matches the registry count toward a quota;
* reviews only count for reviewers absent from the author roster, and an
  empty/unreadable roster means non-authorship cannot be established, so no
  review counts;
* the packaged calibration registries start with zero APPROVED profiles and
  zero frozen profiles, so the calibration blocker stays open until real
  approved-and-frozen evidence exists (see :mod:`bionexus.calibration_freeze`).

This module computes assessments only.  It can never flip a quota to
satisfied without verifiable artifacts on disk, and it never marks the
``docs/context/OPEN_QUESTIONS.md`` blockers resolved: those remain open until
governance actions recorded by humans change the underlying evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from bionexus.provenance import sha256_file

__all__ = [
    "IVN_SCHEMA_VERSION",
    "IVNError",
    "EntityStatus",
    "ReviewVerdict",
    "INDEPENDENT_TRUTH_KINDS",
    "DatasetTruthProvenance",
    "IndependenceDeclaration",
    "IVNDataset",
    "ExternalLabStudy",
    "NonAuthorReview",
    "CapabilityRequirements",
    "RequirementCheck",
    "CapabilityNetworkAssessment",
    "IVNRegistry",
    "DEFAULT_REQUIREMENTS",
    "default_registry_path",
    "load_registry",
    "evaluate_capability",
    "evaluate_network",
    "open_questions_alignment",
    "verify_registry_integrity",
    "generate_merkle_root",
    "render_public_ledger_html",
]

IVN_SCHEMA_VERSION = "bionexus.ivn.registry.v1"

#: Must stay in lockstep with ``bionexus.certification.FLAGSHIP_CAPABILITIES``
#: and ``bionexus.validation_verifier.FLAGSHIP_CAPABILITIES`` (test-enforced).
FLAGSHIP_CAPABILITIES = (
    "scrna.pseudobulk_de",
    "scrna.annotation_evidence",
    "spatial.inference_validity",
)

#: Truth kinds that satisfy the spatial independent-truth requirement.  A
#: truth derived from the same pipeline under test (``pipeline_derived``) or
#: absent (``none``) never qualifies.
INDEPENDENT_TRUTH_KINDS = ("pathology_annotation", "segmentation_truth")

#: Coverage axes enforced for the annotation flagship.
COVERAGE_AXES = ("disease", "tissue", "technology")

_HEX64 = set("0123456789abcdef")


class IVNError(ValueError):
    """Raised when an IVN registry or entity violates the fail-closed schema."""


class EntityStatus(str, Enum):
    """Lifecycle of an IVN entity.  Only VERIFIED counts toward any quota."""

    REGISTERED = "REGISTERED"
    EVIDENCE_SUBMITTED = "EVIDENCE_SUBMITTED"
    VERIFIED = "VERIFIED"
    RETRACTED = "RETRACTED"


class ReviewVerdict(str, Enum):
    ENDORSED = "ENDORSED"
    ENDORSED_WITH_LIMITS = "ENDORSED_WITH_LIMITS"
    CHALLENGED = "CHALLENGED"


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _is_sha256(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value.lower()) <= _HEX64


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _required_str(entity: str, key: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IVNError(f"{entity}: field '{key}' must be a non-empty string")
    return value


def _entity_status(value: Any, entity: str) -> EntityStatus:
    try:
        return EntityStatus(str(value))
    except ValueError as exc:
        raise IVNError(f"{entity}: unknown entity status '{value}'") from exc


# ------------------------------------------------------------------------------
# Entities
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetTruthProvenance:
    """Who produced the ground truth used to score a spatial dataset.

    A dataset counts toward the spatial quota only when ``kind`` is one of
    :data:`INDEPENDENT_TRUTH_KINDS` (pathology annotation or segmentation
    truth), the provider is independent of the BioNexus author team, and the
    truth was produced blinded to BioNexus outputs.
    """

    kind: str
    provider: str
    independent_of_authors: bool
    blinded_to_system_outputs: bool
    artifact: str = ""
    artifact_sha256: str = ""

    def __post_init__(self) -> None:
        _required_str("truth_provenance", "kind", self.kind)
        _required_str("truth_provenance", "provider", self.provider)
        if self.artifact_sha256 and not _is_sha256(self.artifact_sha256):
            raise IVNError("truth_provenance: artifact_sha256 must be 64 hex characters")

    @property
    def is_independent_truth(self) -> bool:
        return (
            self.kind in INDEPENDENT_TRUTH_KINDS
            and self.independent_of_authors
            and self.blinded_to_system_outputs
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "provider": self.provider,
            "independent_of_authors": self.independent_of_authors,
            "blinded_to_system_outputs": self.blinded_to_system_outputs,
            "artifact": self.artifact,
            "artifact_sha256": self.artifact_sha256,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DatasetTruthProvenance":
        return cls(
            kind=payload.get("kind", ""),
            provider=payload.get("provider", ""),
            independent_of_authors=bool(payload.get("independent_of_authors", False)),
            blinded_to_system_outputs=bool(payload.get("blinded_to_system_outputs", False)),
            artifact=payload.get("artifact", ""),
            artifact_sha256=payload.get("artifact_sha256", ""),
        )


@dataclass(frozen=True)
class IndependenceDeclaration:
    """A lab's signed declaration that it is independent of the BioNexus authors."""

    declares_independent: bool
    signed_by: str
    conflict_disclosure: str = ""

    def __post_init__(self) -> None:
        if self.declares_independent:
            _required_str("independence", "signed_by", self.signed_by)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "declares_independent": self.declares_independent,
            "signed_by": self.signed_by,
            "conflict_disclosure": self.conflict_disclosure,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IndependenceDeclaration":
        return cls(
            declares_independent=bool(payload.get("declares_independent", False)),
            signed_by=payload.get("signed_by", ""),
            conflict_disclosure=payload.get("conflict_disclosure", ""),
        )


@dataclass(frozen=True)
class IVNDataset:
    """One independent dataset executed against a flagship capability.

    ``author_associated`` marks datasets collected, produced, or authored by
    the BioNexus author team; those never count toward the independent-dataset
    quota.  ``preregistration_path`` / ``report_path`` are repo-relative and
    their SHA-256 values are re-verified on every assessment.
    """

    dataset_id: str
    capability_id: str
    title: str
    source_uri: str
    disease: str
    tissue: str
    technology: str
    author_associated: bool
    donor_aware: bool
    outcome: str = "not_recorded"
    accession: str = ""
    truth_provenance: Optional[DatasetTruthProvenance] = None
    preregistration_path: str = ""
    preregistration_sha256: str = ""
    report_path: str = ""
    report_sha256: str = ""
    status: str = EntityStatus.REGISTERED.value
    notes: str = ""

    def __post_init__(self) -> None:
        prefix = f"dataset[{self.dataset_id or '?'}]"
        _required_str(prefix, "dataset_id", self.dataset_id)
        _required_str(prefix, "title", self.title)
        if self.capability_id not in FLAGSHIP_CAPABILITIES:
            raise IVNError(f"{prefix}: capability_id must be one of {FLAGSHIP_CAPABILITIES}")
        for axis in COVERAGE_AXES:
            _required_str(prefix, axis, getattr(self, axis))
        if self.preregistration_sha256 and not _is_sha256(self.preregistration_sha256):
            raise IVNError(f"{prefix}: preregistration_sha256 must be 64 hex characters")
        if self.report_sha256 and not _is_sha256(self.report_sha256):
            raise IVNError(f"{prefix}: report_sha256 must be 64 hex characters")
        _entity_status(self.status, prefix)

    def artifacts_present(self, repo_root: Path) -> bool:
        """True when preregistration and report files exist (hash drift is
        reported separately by :func:`verify_registry_integrity`)."""
        for rel in (self.preregistration_path, self.report_path):
            if not rel or not (repo_root / rel).is_file():
                return False
        return True

    def artifacts_match(self, repo_root: Path) -> bool:
        """True when both recorded SHA-256 digests match the on-disk files."""
        pairs = (
            (self.preregistration_path, self.preregistration_sha256),
            (self.report_path, self.report_sha256),
        )
        for rel, digest in pairs:
            if not digest:
                return False
            path = repo_root / rel
            if not path.is_file() or sha256_file(path).lower() != digest.lower():
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "capability_id": self.capability_id,
            "title": self.title,
            "source_uri": self.source_uri,
            "accession": self.accession,
            "disease": self.disease,
            "tissue": self.tissue,
            "technology": self.technology,
            "author_associated": self.author_associated,
            "donor_aware": self.donor_aware,
            "outcome": self.outcome,
            "truth_provenance": self.truth_provenance.to_dict() if self.truth_provenance else None,
            "preregistration_path": self.preregistration_path,
            "preregistration_sha256": self.preregistration_sha256,
            "report_path": self.report_path,
            "report_sha256": self.report_sha256,
            "status": self.status,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IVNDataset":
        truth = payload.get("truth_provenance")
        return cls(
            dataset_id=payload.get("dataset_id", ""),
            capability_id=payload.get("capability_id", ""),
            title=payload.get("title", ""),
            source_uri=payload.get("source_uri", ""),
            accession=payload.get("accession", ""),
            disease=payload.get("disease", ""),
            tissue=payload.get("tissue", ""),
            technology=payload.get("technology", ""),
            author_associated=bool(payload.get("author_associated", False)),
            donor_aware=bool(payload.get("donor_aware", False)),
            outcome=payload.get("outcome", "not_recorded"),
            truth_provenance=DatasetTruthProvenance.from_dict(truth) if truth else None,
            preregistration_path=payload.get("preregistration_path", ""),
            preregistration_sha256=payload.get("preregistration_sha256", ""),
            report_path=payload.get("report_path", ""),
            report_sha256=payload.get("report_sha256", ""),
            status=payload.get("status", EntityStatus.REGISTERED.value),
            notes=payload.get("notes", ""),
        )


@dataclass(frozen=True)
class ExternalLabStudy:
    """An execution of a flagship capability performed by an external lab.

    A study counts toward the external-lab quota only when it is ``VERIFIED``,
    its independence declaration is signed, its capsule/report artifact exists
    with a matching SHA-256, and it references a dataset that itself counts
    toward the independent-dataset quota.  Registered frameworks and empty
    slots never count.
    """

    study_id: str
    lab_id: str
    lab_name: str
    institution: str
    country: str
    capability_id: str
    dataset_id: str
    host: str
    independence: IndependenceDeclaration
    capsule_path: str = ""
    capsule_sha256: str = ""
    completed_at: str = ""
    status: str = EntityStatus.REGISTERED.value
    notes: str = ""

    def __post_init__(self) -> None:
        prefix = f"lab_study[{self.study_id or '?'}]"
        for key in ("study_id", "lab_id", "lab_name", "institution", "country"):
            _required_str(prefix, key, getattr(self, key))
        if self.capability_id not in FLAGSHIP_CAPABILITIES:
            raise IVNError(f"{prefix}: capability_id must be one of {FLAGSHIP_CAPABILITIES}")
        _required_str(prefix, "dataset_id", self.dataset_id)
        _required_str(prefix, "host", self.host)
        if self.capsule_sha256 and not _is_sha256(self.capsule_sha256):
            raise IVNError(f"{prefix}: capsule_sha256 must be 64 hex characters")
        _entity_status(self.status, prefix)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "study_id": self.study_id,
            "lab_id": self.lab_id,
            "lab_name": self.lab_name,
            "institution": self.institution,
            "country": self.country,
            "capability_id": self.capability_id,
            "dataset_id": self.dataset_id,
            "host": self.host,
            "independence": self.independence.to_dict(),
            "capsule_path": self.capsule_path,
            "capsule_sha256": self.capsule_sha256,
            "completed_at": self.completed_at,
            "status": self.status,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ExternalLabStudy":
        return cls(
            study_id=payload.get("study_id", ""),
            lab_id=payload.get("lab_id", ""),
            lab_name=payload.get("lab_name", ""),
            institution=payload.get("institution", ""),
            country=payload.get("country", ""),
            capability_id=payload.get("capability_id", ""),
            dataset_id=payload.get("dataset_id", ""),
            host=payload.get("host", ""),
            independence=IndependenceDeclaration.from_dict(payload.get("independence", {})),
            capsule_path=payload.get("capsule_path", ""),
            capsule_sha256=payload.get("capsule_sha256", ""),
            completed_at=payload.get("completed_at", ""),
            status=payload.get("status", EntityStatus.REGISTERED.value),
            notes=payload.get("notes", ""),
        )


@dataclass(frozen=True)
class NonAuthorReview:
    """An independent scientific review by a reviewer who is not an author.

    The review counts toward the reviewer quota only when the reviewer is
    absent from the registry's author roster (an empty roster means
    non-authorship cannot be established and the review never counts), the
    review was blinded, an attestation id is recorded, and the review
    artifact exists with a matching SHA-256.
    """

    review_id: str
    capability_id: str
    subject_id: str
    reviewer_id: str
    reviewer_name: str
    affiliation: str
    verdict: str
    blinded: bool
    declared_non_author: bool
    attestation_id: str = ""
    review_path: str = ""
    review_sha256: str = ""
    reviewed_at: str = ""
    status: str = EntityStatus.REGISTERED.value
    notes: str = ""

    def __post_init__(self) -> None:
        prefix = f"review[{self.review_id or '?'}]"
        for key in ("review_id", "subject_id", "reviewer_id", "reviewer_name", "affiliation"):
            _required_str(prefix, key, getattr(self, key))
        if self.capability_id not in FLAGSHIP_CAPABILITIES:
            raise IVNError(f"{prefix}: capability_id must be one of {FLAGSHIP_CAPABILITIES}")
        try:
            ReviewVerdict(self.verdict)
        except ValueError as exc:
            valid = ", ".join(v.value for v in ReviewVerdict)
            raise IVNError(f"{prefix}: verdict must be one of {valid}") from exc
        if self.review_sha256 and not _is_sha256(self.review_sha256):
            raise IVNError(f"{prefix}: review_sha256 must be 64 hex characters")
        _entity_status(self.status, prefix)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "review_id": self.review_id,
            "capability_id": self.capability_id,
            "subject_id": self.subject_id,
            "reviewer_id": self.reviewer_id,
            "reviewer_name": self.reviewer_name,
            "affiliation": self.affiliation,
            "verdict": self.verdict,
            "blinded": self.blinded,
            "declared_non_author": self.declared_non_author,
            "attestation_id": self.attestation_id,
            "review_path": self.review_path,
            "review_sha256": self.review_sha256,
            "reviewed_at": self.reviewed_at,
            "status": self.status,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "NonAuthorReview":
        return cls(
            review_id=payload.get("review_id", ""),
            capability_id=payload.get("capability_id", ""),
            subject_id=payload.get("subject_id", ""),
            reviewer_id=payload.get("reviewer_id", ""),
            reviewer_name=payload.get("reviewer_name", ""),
            affiliation=payload.get("affiliation", ""),
            verdict=payload.get("verdict", ""),
            blinded=bool(payload.get("blinded", False)),
            declared_non_author=bool(payload.get("declared_non_author", False)),
            attestation_id=payload.get("attestation_id", ""),
            review_path=payload.get("review_path", ""),
            review_sha256=payload.get("review_sha256", ""),
            reviewed_at=payload.get("reviewed_at", ""),
            status=payload.get("status", EntityStatus.REGISTERED.value),
            notes=payload.get("notes", ""),
        )


# ------------------------------------------------------------------------------
# Requirements & assessment
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityRequirements:
    """Per-capability IVN quotas and depth requirements.

    ``require_donor_aware`` is set for capabilities whose unit of inference is
    the biological donor (pseudobulk DE); cell-level capabilities
    (annotation evidence, spatial validity) do not carry it.
    """

    min_independent_datasets: int = 3
    min_external_labs: int = 2
    min_non_author_reviewers: int = 1
    min_distinct_diseases: int = 0
    min_distinct_tissues: int = 0
    min_distinct_technologies: int = 0
    require_independent_truth: bool = False
    require_donor_aware: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "min_independent_datasets": self.min_independent_datasets,
            "min_external_labs": self.min_external_labs,
            "min_non_author_reviewers": self.min_non_author_reviewers,
            "min_distinct_diseases": self.min_distinct_diseases,
            "min_distinct_tissues": self.min_distinct_tissues,
            "min_distinct_technologies": self.min_distinct_technologies,
            "require_independent_truth": self.require_independent_truth,
            "require_donor_aware": self.require_donor_aware,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CapabilityRequirements":
        return cls(
            min_independent_datasets=int(payload.get("min_independent_datasets", 3)),
            min_external_labs=int(payload.get("min_external_labs", 2)),
            min_non_author_reviewers=int(payload.get("min_non_author_reviewers", 1)),
            min_distinct_diseases=int(payload.get("min_distinct_diseases", 0)),
            min_distinct_tissues=int(payload.get("min_distinct_tissues", 0)),
            min_distinct_technologies=int(payload.get("min_distinct_technologies", 0)),
            require_independent_truth=bool(payload.get("require_independent_truth", False)),
            require_donor_aware=bool(payload.get("require_donor_aware", False)),
        )


#: Network-wide minimum quotas with capability-specific depth requirements.
DEFAULT_REQUIREMENTS: Dict[str, CapabilityRequirements] = {
    "scrna.pseudobulk_de": CapabilityRequirements(require_donor_aware=True),
    "scrna.annotation_evidence": CapabilityRequirements(
        min_distinct_diseases=2,
        min_distinct_tissues=2,
        min_distinct_technologies=2,
    ),
    "spatial.inference_validity": CapabilityRequirements(require_independent_truth=True),
}


@dataclass(frozen=True)
class RequirementCheck:
    """One assessed quota for one capability."""

    requirement: str
    required: str
    observed: str
    satisfied: bool
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement": self.requirement,
            "required": self.required,
            "observed": self.observed,
            "satisfied": self.satisfied,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class CapabilityNetworkAssessment:
    """Result of evaluating one capability against its IVN requirements."""

    capability_id: str
    complete: bool
    counted_datasets: Tuple[str, ...]
    excluded_datasets: Tuple[Dict[str, str], ...]
    counted_lab_studies: Tuple[str, ...]
    excluded_lab_studies: Tuple[Dict[str, str], ...]
    counted_reviews: Tuple[str, ...]
    excluded_reviews: Tuple[Dict[str, str], ...]
    checks: Tuple[RequirementCheck, ...]
    blocking_gaps: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "complete": self.complete,
            "counted_datasets": list(self.counted_datasets),
            "excluded_datasets": list(self.excluded_datasets),
            "counted_lab_studies": list(self.counted_lab_studies),
            "excluded_lab_studies": list(self.excluded_lab_studies),
            "counted_reviews": list(self.counted_reviews),
            "excluded_reviews": list(self.excluded_reviews),
            "checks": [check.to_dict() for check in self.checks],
            "blocking_gaps": list(self.blocking_gaps),
        }


@dataclass
class IVNRegistry:
    """The Independent Validation Network registry.

    Persisted at ``validation/ivn/REGISTRY.json``.  ``author_roster`` drives
    the non-author check for reviews; an empty roster fails closed (no review
    can be proven non-author, so none counts).
    """

    schema_version: str = IVN_SCHEMA_VERSION
    generated_at: str = ""
    requirements: Dict[str, CapabilityRequirements] = field(default_factory=dict)
    author_roster: Tuple[Dict[str, Any], ...] = ()
    datasets: Tuple[IVNDataset, ...] = ()
    lab_studies: Tuple[ExternalLabStudy, ...] = ()
    reviews: Tuple[NonAuthorReview, ...] = ()
    calibration_freezes: Tuple[Dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != IVN_SCHEMA_VERSION:
            raise IVNError(f"registry schema_version must be {IVN_SCHEMA_VERSION}")
        ids: set[str] = set()
        for dataset in self.datasets:
            if dataset.dataset_id in ids:
                raise IVNError(f"duplicate entity id '{dataset.dataset_id}'")
            ids.add(dataset.dataset_id)
        study_ids: set[str] = set()
        for study in self.lab_studies:
            if study.study_id in study_ids:
                raise IVNError(f"duplicate entity id '{study.study_id}'")
            study_ids.add(study.study_id)
        review_ids: set[str] = set()
        for review in self.reviews:
            if review.review_id in review_ids:
                raise IVNError(f"duplicate entity id '{review.review_id}'")
            review_ids.add(review.review_id)
        for capability_id in self.requirements:
            if capability_id not in FLAGSHIP_CAPABILITIES:
                raise IVNError(
                    f"requirements override for non-flagship capability '{capability_id}'"
                )
        for freeze in self.calibration_freezes:
            if not isinstance(freeze, dict) or not freeze.get("freeze_id"):
                raise IVNError("calibration_freezes entries must carry a freeze_id")

    def requirements_for(self, capability_id: str) -> CapabilityRequirements:
        return self.requirements.get(capability_id, DEFAULT_REQUIREMENTS[capability_id])

    def reviewer_is_author(self, review: NonAuthorReview) -> bool:
        """Fail-closed non-author check against the author roster.

        With an empty roster, non-authorship cannot be established, so the
        reviewer is treated as potentially an author (review never counts).
        """
        if not self.author_roster:
            return True
        identity = {
            str(review.reviewer_id).strip().casefold(),
            str(review.reviewer_name).strip().casefold(),
        }
        for entry in self.author_roster:
            roster_ids = {str(entry.get("name", "")).strip().casefold()}
            roster_ids.update(
                str(value).strip().casefold() for value in entry.get("identifiers", [])
            )
            if identity & roster_ids:
                return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "requirements": {cap: req.to_dict() for cap, req in self.requirements.items()},
            "author_roster": [dict(entry) for entry in self.author_roster],
            "datasets": [dataset.to_dict() for dataset in self.datasets],
            "lab_studies": [study.to_dict() for study in self.lab_studies],
            "reviews": [review.to_dict() for review in self.reviews],
            "calibration_freezes": [dict(freeze) for freeze in self.calibration_freezes],
        }

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IVNRegistry":
        if payload.get("schema_version") != IVN_SCHEMA_VERSION:
            raise IVNError(f"registry schema_version must be {IVN_SCHEMA_VERSION}")
        return cls(
            schema_version=payload["schema_version"],
            generated_at=payload.get("generated_at", ""),
            requirements={
                cap: CapabilityRequirements.from_dict(req)
                for cap, req in payload.get("requirements", {}).items()
            },
            author_roster=tuple(payload.get("author_roster", ())),
            datasets=tuple(IVNDataset.from_dict(item) for item in payload.get("datasets", ())),
            lab_studies=tuple(
                ExternalLabStudy.from_dict(item) for item in payload.get("lab_studies", ())
            ),
            reviews=tuple(NonAuthorReview.from_dict(item) for item in payload.get("reviews", ())),
            calibration_freezes=tuple(payload.get("calibration_freezes", ())),
        )


def default_registry_path(repo_root: Optional[Path] = None) -> Path:
    root = Path(repo_root) if repo_root else Path.cwd()
    return root / "validation" / "ivn" / "REGISTRY.json"


def load_registry(path: Optional[Path] = None) -> IVNRegistry:
    path = Path(path) if path else default_registry_path()
    if not path.is_file():
        raise IVNError(f"IVN registry not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IVNError(f"IVN registry is not valid JSON: {path}: {exc}") from exc
    registry = IVNRegistry.from_dict(payload)
    registry.generated_at = payload.get("generated_at", "")
    return registry


# ------------------------------------------------------------------------------
# Counting rules (fail-closed)
# ------------------------------------------------------------------------------


def _dataset_exclusion_reason(dataset: IVNDataset, registry: IVNRegistry, repo_root: Path) -> str:
    if dataset.status == EntityStatus.RETRACTED.value:
        return "retracted"
    if dataset.author_associated:
        return "author_associated datasets never count as independent"
    if dataset.status != EntityStatus.VERIFIED.value:
        return f"status {dataset.status} is not VERIFIED"
    if registry.requirements_for(dataset.capability_id).require_donor_aware and not dataset.donor_aware:
        return "capability requires a donor-aware design and the dataset is not donor-aware"
    if not dataset.preregistration_path or not dataset.preregistration_sha256:
        return "missing hash-locked preregistration"
    if not dataset.report_path or not dataset.report_sha256:
        return "missing hash-bound report"
    if not dataset.artifacts_present(repo_root):
        return "preregistration/report artifacts missing on disk"
    if not dataset.artifacts_match(repo_root):
        return "recorded SHA-256 does not match artifact on disk"
    requirements = registry.requirements_for(dataset.capability_id)
    if requirements.require_independent_truth:
        truth = dataset.truth_provenance
        if truth is None:
            return "no truth provenance: spatial requires independent pathology/segmentation truth"
        if not truth.is_independent_truth:
            return (
                "truth provenance is not independent pathology/segmentation truth "
                "(kind must be pathology_annotation or segmentation_truth, provider "
                "independent of authors, blinded to system outputs)"
            )
    return ""


def _lab_study_exclusion_reason(
    study: ExternalLabStudy, registry: IVNRegistry, counted_dataset_ids: Sequence[str], repo_root: Path
) -> str:
    if study.status == EntityStatus.RETRACTED.value:
        return "retracted"
    if study.status != EntityStatus.VERIFIED.value:
        return f"status {study.status} is not VERIFIED (frameworks and slots never count)"
    if not study.independence.declares_independent:
        return "independence declaration not signed"
    if not study.capsule_path or not study.capsule_sha256:
        return "missing hash-bound capsule/report artifact"
    capsule = repo_root / study.capsule_path
    if not capsule.is_file():
        return "capsule/report artifact missing on disk"
    if sha256_file(capsule).lower() != study.capsule_sha256.lower():
        return "recorded SHA-256 does not match capsule artifact on disk"
    if study.dataset_id not in counted_dataset_ids:
        return "references a dataset that does not itself count as independent"
    return ""


def _review_exclusion_reason(review: NonAuthorReview, registry: IVNRegistry, repo_root: Path) -> str:
    if review.status == EntityStatus.RETRACTED.value:
        return "retracted"
    if review.status != EntityStatus.VERIFIED.value:
        return f"status {review.status} is not VERIFIED (pending reviewer slots never count)"
    if not review.declared_non_author:
        return "reviewer did not declare non-authorship"
    if registry.reviewer_is_author(review):
        if registry.author_roster:
            return "reviewer matches the author roster"
        return "author roster is empty: non-authorship cannot be established (fail-closed)"
    if not review.blinded:
        return "review was not blinded"
    if not review.attestation_id:
        return "missing reviewer attestation id"
    if not review.review_path or not review.review_sha256:
        return "missing hash-bound review artifact"
    review_file = repo_root / review.review_path
    if not review_file.is_file():
        return "review artifact missing on disk"
    if sha256_file(review_file).lower() != review.review_sha256.lower():
        return "recorded SHA-256 does not match review artifact on disk"
    return ""


def _distinct(values: Sequence[str]) -> int:
    return len({value.strip().casefold() for value in values if value.strip()})


def evaluate_capability(
    capability_id: str, registry: IVNRegistry, *, repo_root: Optional[Path] = None
) -> CapabilityNetworkAssessment:
    """Assess one flagship capability against its IVN requirements."""
    if capability_id not in FLAGSHIP_CAPABILITIES:
        raise IVNError(f"unknown flagship capability '{capability_id}'")
    root = Path(repo_root) if repo_root else Path.cwd()
    requirements = registry.requirements_for(capability_id)

    counted_datasets: List[str] = []
    excluded_datasets: List[Dict[str, str]] = []
    for dataset in registry.datasets:
        if dataset.capability_id != capability_id:
            continue
        reason = _dataset_exclusion_reason(dataset, registry, root)
        if reason:
            excluded_datasets.append({"dataset_id": dataset.dataset_id, "reason": reason})
        else:
            counted_datasets.append(dataset.dataset_id)

    counted_labs: List[str] = []
    excluded_labs: List[Dict[str, str]] = []
    for study in registry.lab_studies:
        if study.capability_id != capability_id:
            continue
        reason = _lab_study_exclusion_reason(
            study, registry, counted_datasets, root
        )
        if reason:
            excluded_labs.append({"study_id": study.study_id, "reason": reason})
        else:
            counted_labs.append(study.study_id)

    counted_reviews: List[str] = []
    excluded_reviews: List[Dict[str, str]] = []
    for review in registry.reviews:
        if review.capability_id != capability_id:
            continue
        reason = _review_exclusion_reason(review, registry, root)
        if reason:
            excluded_reviews.append({"review_id": review.review_id, "reason": reason})
        else:
            counted_reviews.append(review.review_id)

    checks: List[RequirementCheck] = []
    gaps: List[str] = []

    datasets_ok = len(counted_datasets) >= requirements.min_independent_datasets
    checks.append(
        RequirementCheck(
            requirement="independent_datasets",
            required=f">= {requirements.min_independent_datasets}",
            observed=str(len(counted_datasets)),
            satisfied=datasets_ok,
            detail="counted only when independent of authors, VERIFIED, and "
            "preregistration/report hashes match on disk "
            "(donor-aware where the capability requires it)",
        )
    )
    if not datasets_ok:
        gaps.append(
            f"independent datasets: {len(counted_datasets)}/{requirements.min_independent_datasets} counted"
            + (f" ({len(excluded_datasets)} excluded)" if excluded_datasets else "")
        )

    counted_ds = [d for d in registry.datasets if d.dataset_id in set(counted_datasets)]
    for axis, attr, minimum in (
        ("cross_disease", "disease", requirements.min_distinct_diseases),
        ("cross_tissue", "tissue", requirements.min_distinct_tissues),
        ("cross_technology", "technology", requirements.min_distinct_technologies),
    ):
        if minimum <= 0:
            continue
        observed = _distinct([getattr(d, attr) for d in counted_ds])
        satisfied = observed >= minimum
        checks.append(
            RequirementCheck(
                requirement=axis,
                required=f">= {minimum} distinct",
                observed=str(observed),
                satisfied=satisfied,
                detail=f"coverage over counted datasets only ({', '.join(counted_datasets) or 'none'})",
            )
        )
        if not satisfied:
            gaps.append(f"{axis}: {observed}/{minimum} distinct across counted datasets")

    if requirements.require_independent_truth:
        independent = [
            d for d in counted_ds if d.truth_provenance and d.truth_provenance.is_independent_truth
        ]
        satisfied = bool(counted_ds) and len(independent) == len(counted_ds)
        checks.append(
            RequirementCheck(
                requirement="independent_truth",
                required="every counted dataset carries independent pathology/segmentation truth",
                observed=f"{len(independent)}/{len(counted_ds)}",
                satisfied=satisfied,
                detail="truth must be pathology_annotation or segmentation_truth, "
                "independent of authors, blinded to system outputs",
            )
        )
        if not satisfied:
            gaps.append(
                "independent_truth: counted spatial datasets without independent "
                "pathology/segmentation truth"
            )

    distinct_institutions = {
        study.institution.strip().casefold()
        for study in registry.lab_studies
        if study.study_id in set(counted_labs)
    }
    labs_ok = len(counted_labs) >= requirements.min_external_labs and len(
        distinct_institutions
    ) >= requirements.min_external_labs
    checks.append(
        RequirementCheck(
            requirement="external_labs",
            required=f">= {requirements.min_external_labs} distinct institutions",
            observed=f"{len(counted_labs)} verified studies across {len(distinct_institutions)} institutions",
            satisfied=labs_ok,
            detail="only VERIFIED studies with matching capsule hashes on counted datasets",
        )
    )
    if not labs_ok:
        gaps.append(
            f"external labs: {len(counted_labs)}/{requirements.min_external_labs} verified "
            f"({len(distinct_institutions)} distinct institutions)"
        )

    reviews_ok = len(counted_reviews) >= requirements.min_non_author_reviewers
    checks.append(
        RequirementCheck(
            requirement="non_author_reviewers",
            required=f">= {requirements.min_non_author_reviewers}",
            observed=str(len(counted_reviews)),
            satisfied=reviews_ok,
            detail="only blinded, attested reviews by reviewers absent from the author roster",
        )
    )
    if not reviews_ok:
        gaps.append(
            f"non-author reviewers: {len(counted_reviews)}/{requirements.min_non_author_reviewers}"
        )

    return CapabilityNetworkAssessment(
        capability_id=capability_id,
        complete=all(check.satisfied for check in checks),
        counted_datasets=tuple(counted_datasets),
        excluded_datasets=tuple(excluded_datasets),
        counted_lab_studies=tuple(counted_labs),
        excluded_lab_studies=tuple(excluded_labs),
        counted_reviews=tuple(counted_reviews),
        excluded_reviews=tuple(excluded_reviews),
        checks=tuple(checks),
        blocking_gaps=tuple(gaps),
    )


# ------------------------------------------------------------------------------
# Network-level assessment & OPEN_QUESTIONS alignment
# ------------------------------------------------------------------------------

#: The four open blockers recorded in ``docs/context/OPEN_QUESTIONS.md``.  The
#: IVN derives their status from evidence; it never marks them resolved by
#: construction.
OPEN_QUESTION_BLOCKERS = (
    "no-approved-empirical-calibration-profiles",
    "annotation-and-spatial-real-data-validation-is-missing",
    "cross-host-and-independent-review-are-incomplete",
    "external-adoption-and-governance-are-not-established",
)


def _calibration_freeze_state(registry: IVNRegistry) -> Dict[str, Any]:
    """Report the packaged calibration + freeze state honestly.

    The packaged empirical calibration registry ships zero APPROVED profiles
    (all LEGACY_UNCALIBRATED); the IVN registry ships zero freezes.  Any
    APPROVED profile must additionally be hash-frozen on held-out contexts
    (see :mod:`bionexus.calibration_freeze`) before the blocker may close.
    """
    approved_frozen: List[str] = []
    approved_unfrozen: List[str] = []
    try:
        from bionexus.empirical_warrant import CalibrationReviewStatus

        data_root = Path(__file__).resolve().parent / "data"
        packaged = json.loads(
            (data_root / "empirical_calibration_registry.json").read_text(encoding="utf-8")
        )
        for profile_payload in packaged.get("profiles", []):
            if profile_payload.get("review_status") == CalibrationReviewStatus.APPROVED.value:
                profile_id = profile_payload.get("profile_id", "?")
                version = profile_payload.get("version", "?")
                frozen = any(
                    freeze.get("profile_id") == profile_id
                    and freeze.get("profile_version") == version
                    and freeze.get("held_out_contexts")
                    for freeze in registry.calibration_freezes
                )
                (approved_frozen if frozen else approved_unfrozen).append(f"{profile_id}:{version}")
    except (OSError, json.JSONDecodeError):
        pass
    return {
        "approved_frozen_profiles": approved_frozen,
        "approved_unfrozen_profiles": approved_unfrozen,
        "frozen_profile_records": len(registry.calibration_freezes),
    }


def open_questions_alignment(network: Mapping[str, Any], registry: IVNRegistry) -> Dict[str, Any]:
    """Derive the four OPEN_QUESTIONS blockers from the network assessment.

    Every blocker remains open unless the underlying evidence gates say
    otherwise; the adoption/governance blocker additionally requires a signed
    governance council record which this schema cannot synthesize, so it stays
    open until such a record exists (schema or local maintainer test is not
    adoption or endorsement).
    """
    capabilities = network.get("capabilities", {})
    annotation = capabilities.get("scrna.annotation_evidence", {})
    spatial = capabilities.get("spatial.inference_validity", {})

    freeze_state = _calibration_freeze_state(registry)
    calibration_open = not freeze_state["approved_frozen_profiles"]

    realdata_open = bool(annotation.get("blocking_gaps")) or bool(spatial.get("blocking_gaps"))
    review_open = any(
        not caps.get("complete") and (
            caps.get("counted_lab_studies") == []
            or caps.get("counted_reviews") == []
            or bool(caps.get("blocking_gaps"))
        )
        for caps in capabilities.values()
    )

    blockers = {
        "no-approved-empirical-calibration-profiles": {
            "still_open": calibration_open,
            "basis": freeze_state,
            "note": "profiles must be APPROVED and hash-frozen on held-out contexts",
        },
        "annotation-and-spatial-real-data-validation-is-missing": {
            "still_open": realdata_open,
            "basis": {
                "annotation_gaps": list(annotation.get("blocking_gaps", [])),
                "spatial_gaps": list(spatial.get("blocking_gaps", [])),
            },
            "note": "annotation requires never-seen cross-disease/tissue/technology cohorts; "
            "spatial requires a full public cohort with independent pathology/segmentation truth",
        },
        "cross-host-and-independent-review-are-incomplete": {
            "still_open": review_open,
            "basis": {
                capability: {
                    "verified_lab_studies": list(caps.get("counted_lab_studies", [])),
                    "verified_reviews": list(caps.get("counted_reviews", [])),
                }
                for capability, caps in capabilities.items()
            },
            "note": "frameworks and reviewer slots do not count as completed evidence",
        },
        "external-adoption-and-governance-are-not-established": {
            "still_open": True,
            "basis": {"signed_governance_council_records": 0},
            "note": "a schema or local maintainer test is not adoption or endorsement; "
            "closing this blocker requires signed governance council records this "
            "schema cannot synthesize",
        },
    }
    return {
        "source": "docs/context/OPEN_QUESTIONS.md",
        "blockers": blockers,
        "all_still_open_as_assessed": any(item["still_open"] for item in blockers.values()),
    }


def evaluate_network(
    registry: IVNRegistry, *, repo_root: Optional[Path] = None
) -> Dict[str, Any]:
    """Assess every flagship capability and derive the OPEN_QUESTIONS view."""
    assessments = {
        capability_id: evaluate_capability(capability_id, registry, repo_root=repo_root)
        for capability_id in FLAGSHIP_CAPABILITIES
    }
    complete = all(assessment.complete for assessment in assessments.values())
    network: Dict[str, Any] = {
        "schema_version": IVN_SCHEMA_VERSION,
        "network_status": "COMPLETE" if complete else "INCOMPLETE",
        "quota": ">= 3 independent datasets x >= 2 external labs x >= 1 non-author reviewer "
        "per flagship capability",
        "capabilities": {
            capability_id: assessment.to_dict()
            for capability_id, assessment in assessments.items()
        },
    }
    network["open_questions"] = open_questions_alignment(network, registry)
    return network


def verify_registry_integrity(
    registry: IVNRegistry, *, repo_root: Optional[Path] = None
) -> Dict[str, Any]:
    """Recompute every recorded artifact hash in the registry (drift check)."""
    root = Path(repo_root) if repo_root else Path.cwd()
    drift: List[Dict[str, str]] = []
    for dataset in registry.datasets:
        for label, rel, digest in (
            ("preregistration", dataset.preregistration_path, dataset.preregistration_sha256),
            ("report", dataset.report_path, dataset.report_sha256),
        ):
            if not rel and not digest:
                continue
            path = root / rel if rel else None
            if not digest or not path or not path.is_file():
                drift.append(
                    {"entity": dataset.dataset_id, "artifact": rel, "problem": "missing"}
                )
            elif sha256_file(path).lower() != digest.lower():
                drift.append(
                    {"entity": dataset.dataset_id, "artifact": rel, "problem": "sha256_mismatch"}
                )
    for study in registry.lab_studies:
        if not study.capsule_path and not study.capsule_sha256:
            continue
        path = root / study.capsule_path if study.capsule_path else None
        if not study.capsule_sha256 or not path or not path.is_file():
            drift.append({"entity": study.study_id, "artifact": study.capsule_path, "problem": "missing"})
        elif sha256_file(path).lower() != study.capsule_sha256.lower():
            drift.append(
                {"entity": study.study_id, "artifact": study.capsule_path, "problem": "sha256_mismatch"}
            )
    for review in registry.reviews:
        if not review.review_path and not review.review_sha256:
            continue
        path = root / review.review_path if review.review_path else None
        if not review.review_sha256 or not path or not path.is_file():
            drift.append({"entity": review.review_id, "artifact": review.review_path, "problem": "missing"})
        elif sha256_file(path).lower() != review.review_sha256.lower():
            drift.append(
                {"entity": review.review_id, "artifact": review.review_path, "problem": "sha256_mismatch"}
            )
    return {
        "schema_version": IVN_SCHEMA_VERSION,
        "checked_entities": len(registry.datasets)
        + len(registry.lab_studies)
        + len(registry.reviews),
        "drift": drift,
        "integrity": "PASS" if not drift else "FAIL",
    }


def generate_merkle_root(registry: IVNRegistry) -> str:
    """Compute a deterministic Merkle-style root hash over all registry entities."""
    from bionexus.ivn_ledger_page import generate_merkle_root as _gen_root

    return _gen_root(registry)


def render_public_ledger_html(
    registry: IVNRegistry,
    *,
    network_assessment: Optional[Mapping[str, Any]] = None,
    repo_root: Optional[Path] = None,
    custom_title: str = "BioNexus Independent Validation Network (IVN) — Public Evidence Ledger",
) -> str:
    """Render a standalone, zero-dependency HTML document representing the IVN Public Ledger."""
    from bionexus.ivn_ledger_page import render_public_ledger_html as _render_html

    return _render_html(
        registry,
        network_assessment=network_assessment,
        repo_root=repo_root,
        custom_title=custom_title,
    )

