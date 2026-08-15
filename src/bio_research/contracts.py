"""
Shared result contract and Scientific Evidence Operating Layer for BioNexus.

Decouples Execution Fidelity (did the official method run?) from Scientific Evidence
Quality (input integrity, assumption validity, statistical power, parameter robustness,
cross-method concordance, and external validation).

Every numeric or classification result carries method, backend, legacy evidence_grade,
a multi-dimensional EvidenceCard, and a synthesized conclusion_status.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Optional


class EvidenceGrade(str, Enum):
    """Legacy single-dimension grade: A = gold-standard backend; B = simplified real; C = heuristic."""

    A = "A"
    B = "B"
    C = "C"
    ABSTAIN = "abstain"


class ConclusionStatus(str, Enum):
    """
    Synthesized scientific certainty status:
    - SUPPORTED: High execution fidelity + verified input + valid assumptions + solid statistics.
    - TENTATIVE: Valid execution & plausible inputs, but single parameter run or unverified orthogonals.
    - FRAGILE: Parameter sensitive, unverified input scaling, or marginal statistical power.
    - CONFLICTED: Contradictory evidence across alternative methods or discordant with benchmarks.
    - ABSTAIN: Missing required backend, violated hard constraints, or clinical claim refusal.
    """

    SUPPORTED = "SUPPORTED"
    TENTATIVE = "TENTATIVE"
    FRAGILE = "FRAGILE"
    CONFLICTED = "CONFLICTED"
    ABSTAIN = "ABSTAIN"


GRADE_A = EvidenceGrade.A.value
GRADE_B = EvidenceGrade.B.value
GRADE_C = EvidenceGrade.C.value
ABSTAIN = EvidenceGrade.ABSTAIN.value

RESEARCH_USE_ONLY = (
    "Research-use only. Not a clinical diagnostic, not CLIA/CAP validated, "
    "and not an authorized medical device."
)


@dataclass
class EvidenceCard:
    """
    Multi-dimensional evaluation card for scientific evidence quality.
    """

    execution_fidelity: str = GRADE_A  # A (gold package) / B (simplified) / C (heuristic) / abstain
    input_integrity: str = GRADE_A     # A (verified raw/normalized integer/float) / B (plausible) / C (suspect scaling/NaNs)
    assumption_validity: str = GRADE_B # A (verified statistical distribution) / B (standard assumed) / C (violated) / UNKNOWN
    statistical_support: str = GRADE_B # A (strong effect + FDR < 0.05) / B (moderate) / C (marginal) / INSUFFICIENT
    parameter_robustness: str = "UNTESTED"  # A (stable across sweeps) / B (moderate variation) / C (fragile) / UNTESTED
    cross_method_concordance: str = "UNTESTED"  # A (unanimous) / B (majority) / C (conflicted) / UNTESTED
    external_validation: str = "UNTESTED"  # A (recovers ground truth) / B (partial) / C (inconsistent) / UNTESTED
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert EvidenceCard to dictionary."""
        return asdict(self)

    def synthesize_status(self, abstain: bool = False) -> str:
        """Synthesize overall scientific conclusion status from the card dimensions."""
        return synthesize_conclusion_status(self, abstain=abstain)

    def to_markdown(self) -> str:
        """Render a formatted markdown evidence card."""
        status = self.synthesize_status()
        lines = [
            "### BioNexus Evidence Card",
            f"**Conclusion Status**: `{status}`",
            "",
            "| Dimension | Grade | Evaluation Notes |",
            "| :--- | :---: | :--- |",
            f"| **Execution Fidelity** | `{self.execution_fidelity}` | {self.details.get('execution_notes', 'Standard execution')} |",
            f"| **Input Integrity** | `{self.input_integrity}` | {self.details.get('input_notes', 'Input verified')} |",
            f"| **Assumption Validity** | `{self.assumption_validity}` | {self.details.get('assumption_notes', 'Standard assumptions')} |",
            f"| **Statistical Support** | `{self.statistical_support}` | {self.details.get('statistical_notes', 'Empirical estimates')} |",
            f"| **Parameter Robustness** | `{self.parameter_robustness}` | {self.details.get('robustness_notes', 'Single parameter run')} |",
            f"| **Cross-method Concordance** | `{self.cross_method_concordance}` | {self.details.get('concordance_notes', 'Single method evaluated')} |",
            f"| **External Validation** | `{self.external_validation}` | {self.details.get('validation_notes', 'No orthogonal ground truth tested')} |",
        ]
        return "\n".join(lines)


def synthesize_conclusion_status(
    card: EvidenceCard | Dict[str, Any],
    abstain: bool = False
) -> str:
    """
    Synthesize the overall ConclusionStatus from evidence dimensions.
    """
    if isinstance(card, dict):
        exec_fid = card.get("execution_fidelity", GRADE_A)
        inp_int = card.get("input_integrity", GRADE_A)
        assump = card.get("assumption_validity", GRADE_B)
        stat_sup = card.get("statistical_support", GRADE_B)
        param_rob = card.get("parameter_robustness", "UNTESTED")
        concord = card.get("cross_method_concordance", "UNTESTED")
    else:
        exec_fid = card.execution_fidelity
        inp_int = card.input_integrity
        assump = card.assumption_validity
        stat_sup = card.statistical_support
        param_rob = card.parameter_robustness
        concord = card.cross_method_concordance

    # 1. Hard Abstention / Refusal
    if abstain or exec_fid.lower() == "abstain" or inp_int.lower() == "abstain":
        return ConclusionStatus.ABSTAIN.value

    # 2. Conflicted across alternative methods
    if concord == GRADE_C or concord.lower() == "conflicted":
        return ConclusionStatus.CONFLICTED.value

    # 3. Fragile: Violated assumptions, degraded inputs (e.g. log1p as raw counts), sensitive parameters, or insufficient statistics
    if (
        exec_fid == GRADE_C
        or inp_int == GRADE_C
        or assump == GRADE_C
        or param_rob == GRADE_C
        or stat_sup in (GRADE_C, "INSUFFICIENT")
    ):
        return ConclusionStatus.FRAGILE.value

    # 4. Supported: All essential dimensions verified at Grade A
    if (
        exec_fid == GRADE_A
        and inp_int == GRADE_A
        and assump == GRADE_A
        and stat_sup == GRADE_A
    ):
        return ConclusionStatus.SUPPORTED.value

    # 5. Tentative: Solid execution with standard assumptions or preliminary parameter sweeps
    return ConclusionStatus.TENTATIVE.value


def attach_meta(
    payload: Dict[str, Any],
    *,
    method: str,
    backend: str,
    evidence_grade: str,
    limitations: Optional[Iterable[str]] = None,
    abstain: bool = False,
    abstain_reason: Optional[str] = None,
    evidence_card: Optional[EvidenceCard | Dict[str, Any]] = None,
    conclusion_status: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a copy of payload with the standard plugin contract fields and EvidenceCard."""
    out = dict(payload)
    out["method"] = method
    out["backend"] = backend
    out["evidence_grade"] = evidence_grade
    out["limitations"] = list(limitations or [])
    out["abstain"] = bool(abstain)
    if abstain or abstain_reason:
        out["abstain_reason"] = abstain_reason or "Insufficient evidence or missing backend."

    # Construct or attach EvidenceCard
    if evidence_card is None:
        # Generate default baseline card matching evidence_grade
        card = EvidenceCard(
            execution_fidelity=evidence_grade,
            input_integrity=GRADE_A if evidence_grade in (GRADE_A, GRADE_B) else GRADE_C,
            assumption_validity=GRADE_B if evidence_grade == GRADE_A else GRADE_C,
            statistical_support=GRADE_B if evidence_grade == GRADE_A else GRADE_C,
            details={"execution_backend": backend, "method": method}
        )
    elif isinstance(evidence_card, EvidenceCard):
        card = evidence_card
    else:
        card = EvidenceCard(**evidence_card)

    status = conclusion_status or card.synthesize_status(abstain=abstain)
    out["evidence_card"] = card.to_dict()
    out["conclusion_status"] = status

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
    card = EvidenceCard(
        execution_fidelity=ABSTAIN,
        input_integrity=ABSTAIN,
        assumption_validity=ABSTAIN,
        statistical_support=ABSTAIN,
        details={"refusal_reason": reason}
    )
    return attach_meta(
        payload,
        method=method,
        backend="none",
        evidence_grade=ABSTAIN,
        limitations=[reason],
        abstain=True,
        abstain_reason=reason,
        evidence_card=card,
        conclusion_status=ConclusionStatus.ABSTAIN.value,
    )
