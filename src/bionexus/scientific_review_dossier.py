"""Pending external-review templates; no generated scientific authority.

Authenticated reviewer submissions belong to the independent validation intake.
These data models and template generators cannot manufacture human sign-off.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ReviewerProfile:
    """Reviewer-supplied profile; this object does not verify credentials."""

    reviewer_id: str
    name: str
    affiliation: str
    role: str
    expertise: List[str]
    coi_statement: str  # Formal Conflict of Interest declaration
    cases_assigned: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaseReviewFinding:
    """Structured evaluation of one capability by an independent domain reviewer."""

    case_id: str
    reviewer_id: str
    capability_id: str
    rubric_scores: Dict[str, int]  # Scored 1 to 5
    mean_rubric_score: float
    verdict: str                  # "APPROVED", "REVISE", "REJECT"
    findings_summary: str
    key_strengths: List[str]
    residual_limitations: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScientificReviewDossier:
    """Complete, sign-off-ready external scientific review package."""

    schema_version: str
    project_version: str
    review_date: str
    review_status: str
    reviewers: List[ReviewerProfile]
    case_reviews: List[CaseReviewFinding]
    overall_verdict: str
    standard_14_satisfied: bool
    dossier_sha256: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_version": self.project_version,
            "review_date": self.review_date,
            "review_status": self.review_status,
            "status": self.overall_verdict,
            "standard_14_satisfied": self.standard_14_satisfied,
            "overall_verdict": self.overall_verdict,
            "reviewers": [r.to_dict() for r in self.reviewers],
            "case_reviews": [c.to_dict() for c in self.case_reviews],
            "dossier_sha256": self.dossier_sha256,
            "evidence_kind": "PENDING_EXTERNAL_REVIEW",
            "scientific_authorization": "NONE",
            "integrity_note": "A payload hash does not verify reviewer identity, independence, or scientific approval.",
        }


def generate_certified_scientific_review(
    repo_root: Path, *, write: bool = False, output_path: Optional[Path] = None,
) -> ScientificReviewDossier:
    """Prepare an empty pending dossier; the legacy name confers no certification.

    This function has no authenticated external-review input. It therefore cannot
    invent reviewers, opinions, COI statements, scores, or completed approvals.
    Use the independent validation intake for actual reviewer submissions.
    Existing evidence is never replaced by this template generator.
    """
    from bionexus.versions import VERSION

    payload = {"reviewers": [], "case_reviews": [], "overall_verdict": "PENDING_EXTERNAL_REVIEW"}
    dossier_sha = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    dossier = ScientificReviewDossier(
        schema_version="bionexus.scientific-review-dossier.v1",
        project_version=VERSION,
        review_date="",  # No review has occurred.
        review_status="PENDING_EXTERNAL_REVIEW",
        reviewers=[],
        case_reviews=[],
        overall_verdict="PENDING_EXTERNAL_REVIEW",
        standard_14_satisfied=False,
        dossier_sha256=dossier_sha,
    )
    if write:
        destination = output_path or repo_root / "review" / "SCIENTIFIC_REVIEW.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(dossier.to_dict(), indent=2, ensure_ascii=False) + "\n")
    return dossier
