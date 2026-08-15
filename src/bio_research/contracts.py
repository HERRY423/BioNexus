"""Shared result contract for every analysis output.

Every numeric or classification result must carry method, backend,
evidence grade, and limitations. Heuristics must not silently upgrade
to gold-standard names.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Iterable, Optional


class EvidenceGrade(str, Enum):
    """A = gold-standard backend; B = simplified real estimator; C = heuristic."""

    A = "A"
    B = "B"
    C = "C"
    ABSTAIN = "abstain"


GRADE_A = EvidenceGrade.A.value
GRADE_B = EvidenceGrade.B.value
GRADE_C = EvidenceGrade.C.value
ABSTAIN = EvidenceGrade.ABSTAIN.value

RESEARCH_USE_ONLY = (
    "Research-use only. Not a clinical diagnostic, not CLIA/CAP validated, "
    "and not an authorized medical device."
)


def attach_meta(
    payload: Dict[str, Any],
    *,
    method: str,
    backend: str,
    evidence_grade: str,
    limitations: Optional[Iterable[str]] = None,
    abstain: bool = False,
    abstain_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a copy of payload with the standard plugin contract fields."""
    out = dict(payload)
    out["method"] = method
    out["backend"] = backend
    out["evidence_grade"] = evidence_grade
    out["limitations"] = list(limitations or [])
    out["abstain"] = bool(abstain)
    if abstain or abstain_reason:
        out["abstain_reason"] = abstain_reason or "Insufficient evidence or missing backend."
    if RESEARCH_USE_ONLY not in out["limitations"]:
        out["limitations"].append(RESEARCH_USE_ONLY)
    return out


def refuse(
    *,
    method: str,
    reason: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Standard abstention payload when a gold-standard backend is required."""
    payload: Dict[str, Any] = dict(extra or {})
    payload["refused"] = True
    return attach_meta(
        payload,
        method=method,
        backend="none",
        evidence_grade=ABSTAIN,
        limitations=[reason],
        abstain=True,
        abstain_reason=reason,
    )
