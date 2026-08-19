"""
Shared result contract and Scientific Evidence Operating Layer for BioNexus (EvidenceCard 2.0).

Structured into three distinct hierarchical epistemic layers:
1. Layer 1: Execution State (EXECUTED | DEGRADED | REFUSED | FAILED)
   - Decoupled entirely from scientific conclusions: did the code run, fail, or get refused?
2. Layer 2: Evidence Dimensions & Qualitative Evaluation (A | B | C | UNTESTED | NOT_APPLICABLE | INSUFFICIENT | CONFLICTED)
   - Input Integrity, Assumption Validity, Statistical Support, Parameter Robustness, Cross-Method Concordance, External Validation.
3. Layer 3: Conclusion Maturity (ABSTAIN -> FRAGILE -> CONFLICTED -> PRELIMINARY -> SUPPORTED -> ROBUST -> REPLICATED)
   - Rigorous progression from single-run exploratory to parameter-stable to externally replicated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Optional


class ExecutionState(str, Enum):
    """
    Layer 1: Execution State.
    Answers: 'Did the method actually execute, or is it in preflight / refused / degraded state?'
    """

    PERMITTED = "PERMITTED"  # Preflight preconditions satisfied, execution permitted but not yet run
    PERMITTED_WITH_LIMITS = "PERMITTED_WITH_LIMITS"  # Permitted but with documented soft-limit overrides
    EXECUTED = "EXECUTED"  # Official gold-standard backend/code executed properly
    DEGRADED = "DEGRADED"  # Heuristic fallback, partial stack, or approximate parameters
    REFUSED = "REFUSED"  # Deterministically refused (missing required backend/hard gate)
    FAILED = "FAILED"  # Runtime crash, exception, divergence, convergence failure


class DimensionGrade(str, Enum):
    """
    Layer 2: Evidence Dimension Status.
    Explicitly distinguishes evaluation grades from untested or invalid states.
    CRITICAL: UNTESTED != GRADE_C (tested and fragile/violated).
    """

    GRADE_A = "A"  # Gold standard / Strong statistical support / Verified input
    GRADE_B = "B"  # Moderate / Plausible / Standard assumed distribution
    GRADE_C = "C"  # Marginal / Violated assumption / Suspect data scaling / Fragile
    UNTESTED = "UNTESTED"  # Dimension was not evaluated in this run
    UNASSESSED = "UNASSESSED"  # Preflight / unexecuted state
    NOT_APPLICABLE = "NOT_APPLICABLE"  # Dimension does not apply to this method
    INSUFFICIENT = "INSUFFICIENT"  # Evaluated, but sample size or statistical power is inadequate
    CONFLICTED = "CONFLICTED"  # Evaluated across methods, results are contradictory


class ConclusionMaturity(str, Enum):
    """
    Layer 3: Scientific Epistemic Maturity Model.
    Hierarchical maturity of the scientific finding:

    - UNASSESSED: Preflight viability passed, but computational analysis and statistics have not executed.
    - ABSTAIN: Execution refused, runtime failed, or clinical claim refused without certification.
    - FRAGILE: Parameter sensitive, violated distribution assumptions, or suspect inputs.
    - CONFLICTED: Contradictory evidence across alternative methods or discordant benchmarks.
    - PRELIMINARY: Plausible single-run execution with standard assumed parameters (Exploratory baseline).
    - SUPPORTED: Current data directly supports hypothesis (Inputs A/B, Assumptions A/B, Stats A/B).
    - ROBUST: SUPPORTED + verified stable under parameter perturbations (Parameter Robustness == Grade A).
    - REPLICATED: ROBUST + verified by independent external datasets, orthogonal assays, or gold-standard truth sets.
    """

    UNASSESSED = "UNASSESSED"
    ABSTAIN = "ABSTAIN"
    FRAGILE = "FRAGILE"
    CONFLICTED = "CONFLICTED"
    PRELIMINARY = "PRELIMINARY"
    SUPPORTED = "SUPPORTED"
    ROBUST = "ROBUST"
    REPLICATED = "REPLICATED"


# Backward compatibility constants and aliases
ConclusionStatus = ConclusionMaturity
EvidenceGrade = DimensionGrade

GRADE_A = DimensionGrade.GRADE_A.value
GRADE_B = DimensionGrade.GRADE_B.value
GRADE_C = DimensionGrade.GRADE_C.value
ABSTAIN = "abstain"
UNTESTED = DimensionGrade.UNTESTED.value
UNASSESSED = DimensionGrade.UNASSESSED.value
NOT_APPLICABLE = DimensionGrade.NOT_APPLICABLE.value
INSUFFICIENT = DimensionGrade.INSUFFICIENT.value
CONFLICTED = DimensionGrade.CONFLICTED.value

RESEARCH_USE_ONLY = (
    "Research-use only. Not a clinical diagnostic, not CLIA/CAP validated, and not an authorized medical device."
)


@dataclass
class EvidenceCard:
    """
    EvidenceCard 2.0: Three-layer Scientific Epistemic Evidence Card.
    """

    # Layer 1: Execution State
    execution_state: str = ExecutionState.EXECUTED.value

    # Layer 2: Evidence Dimensions
    input_integrity: str = DimensionGrade.GRADE_A.value
    assumption_validity: str = DimensionGrade.GRADE_B.value
    statistical_support: str = DimensionGrade.GRADE_B.value
    parameter_robustness: str = DimensionGrade.UNTESTED.value
    cross_method_concordance: str = DimensionGrade.UNTESTED.value
    external_validation: str = DimensionGrade.UNTESTED.value

    # Extra diagnostics & details
    details: Dict[str, Any] = field(default_factory=dict)

    # Layer 4: Purpose-aware fields (Research Intent / Analysis Purpose)
    research_purpose: Optional[str] = None  # exploratory | screening | confirmatory | causal | clinical
    evidence_ceiling: Optional[str] = None  # highest reachable ConclusionMaturity under current purpose
    override_records: List[Dict[str, Any]] = field(default_factory=list)  # active researcher overrides
    residual_limitations: List[str] = field(default_factory=list)  # limitations that remain after override
    blocked_claims: List[str] = field(default_factory=list)  # claims still not warranted after override

    # Backward compatibility field
    execution_fidelity: Optional[str] = None

    def __post_init__(self) -> None:
        # Support legacy execution_fidelity initialization
        if self.execution_fidelity is not None:
            fid_upper = str(self.execution_fidelity).upper()
            if fid_upper in ("A", "GOLD-WRAPPER", "EXECUTED"):
                self.execution_state = ExecutionState.EXECUTED.value
            elif fid_upper in ("B", "C", "HEURISTIC", "DEGRADED"):
                self.execution_state = ExecutionState.DEGRADED.value
            elif fid_upper in ("ABSTAIN", "REFUSE", "REFUSED"):
                self.execution_state = ExecutionState.REFUSED.value
            elif fid_upper in ("FAILED", "FAIL"):
                self.execution_state = ExecutionState.FAILED.value
        else:
            if self.execution_state == ExecutionState.EXECUTED.value:
                self.execution_fidelity = GRADE_A
            elif self.execution_state == ExecutionState.DEGRADED.value:
                self.execution_fidelity = GRADE_C
            elif self.execution_state in (ExecutionState.REFUSED.value, ExecutionState.FAILED.value):
                self.execution_fidelity = ABSTAIN

    def to_dict(self) -> Dict[str, Any]:
        """Convert EvidenceCard to dictionary."""
        d = asdict(self)
        if not d.get("execution_fidelity"):
            d["execution_fidelity"] = GRADE_A if self.execution_state == ExecutionState.EXECUTED.value else GRADE_C
        # Strip empty purpose-aware fields for backward compatibility
        for key in ("research_purpose", "evidence_ceiling", "override_records", "residual_limitations", "blocked_claims"):
            if not d.get(key):
                d.pop(key, None)
        return d

    def synthesize_status(self, abstain: bool = False) -> str:
        """Synthesize overall scientific conclusion maturity from the card dimensions."""
        return synthesize_conclusion_maturity(self, abstain=abstain)

    def to_markdown(self) -> str:
        """Render a formatted markdown evidence card (v2.0)."""
        status = self.synthesize_status()
        exec_st = self.execution_state
        lines = [
            "### BioNexus Evidence Card (v2.0)",
            f"**Conclusion Maturity**: `{status}` | **Execution State**: `{exec_st}`",
            "",
            "#### Layer 1: Execution State",
            f"- **State**: `{exec_st}` ({self.details.get('execution_backend', 'default')})",
            "",
            "#### Layer 2: Evidence Dimensions",
            "| Dimension | Status | Evaluation Notes |",
            "| :--- | :---: | :--- |",
            f"| **Input Integrity** | `{self.input_integrity}` | {self.details.get('input_notes', 'Verified semantics')} |",
            f"| **Assumption Validity** | `{self.assumption_validity}` | {self.details.get('assumption_notes', 'Distribution assumptions evaluated')} |",
            f"| **Statistical Support** | `{self.statistical_support}` | {self.details.get('statistical_notes', 'Statistical tests evaluated')} |",
            f"| **Parameter Robustness** | `{self.parameter_robustness}` | {self.details.get('robustness_notes', 'Parameter sweep status')} |",
            f"| **Cross-method Concordance** | `{self.cross_method_concordance}` | {self.details.get('concordance_notes', 'Cross-algorithm concordance')} |",
            f"| **External Validation** | `{self.external_validation}` | {self.details.get('validation_notes', 'Orthogonal ground truth benchmark')} |",
            "",
            "#### Layer 3: Scientific Conclusion",
            f"- **Maturity**: `{status}`",
            f"- **Assessment**: {self.details.get('conclusion_notes', 'Scientific epistemic evaluation synthesized across all dimensions.')}",
        ]
        return "\n".join(lines)


def synthesize_conclusion_maturity(card: EvidenceCard | Dict[str, Any], abstain: bool = False) -> str:
    """
    Synthesize Layer 3 ConclusionMaturity from Layer 1 ExecutionState and Layer 2 Dimensions.

    Hierarchy of scientific certainty:
    1. ABSTAIN: Refusal, crash, or missing essential input.
    2. CONFLICTED: Discordant results across alternative methods.
    3. FRAGILE: Degraded execution, violated assumptions, fragile parameters, or suspect inputs.
    4. REPLICATED: Supported + Robust + Externally validated against independent ground truth.
    5. ROBUST: Supported + Verified stable under parameter sweeps/perturbations.
    6. SUPPORTED: Verified input + valid assumptions + solid statistics on current dataset.
    7. PRELIMINARY: Plausible single execution run (standard baseline).
    """
    if isinstance(card, dict):
        exec_state = card.get("execution_state")
        exec_fid = card.get("execution_fidelity", GRADE_A)
        if not exec_state:
            fid_upper = str(exec_fid).upper()
            if fid_upper in ("A", "GOLD-WRAPPER", "EXECUTED"):
                exec_state = ExecutionState.EXECUTED.value
            elif fid_upper in ("B", "C", "HEURISTIC", "DEGRADED"):
                exec_state = ExecutionState.DEGRADED.value
            elif fid_upper in ("ABSTAIN", "REFUSE", "REFUSED"):
                exec_state = ExecutionState.REFUSED.value
            else:
                exec_state = ExecutionState.FAILED.value

        inp_int = card.get("input_integrity", GRADE_A)
        assump = card.get("assumption_validity", GRADE_B)
        stat_sup = card.get("statistical_support", GRADE_B)
        param_rob = card.get("parameter_robustness", UNTESTED)
        concord = card.get("cross_method_concordance", UNTESTED)
        ext_val = card.get("external_validation", UNTESTED)
    else:
        exec_state = card.execution_state
        inp_int = card.input_integrity
        assump = card.assumption_validity
        stat_sup = card.statistical_support
        param_rob = card.parameter_robustness
        concord = card.cross_method_concordance
        ext_val = card.external_validation

    # 1. Hard Abstention / Refusal / Failure
    if (
        abstain
        or exec_state in (ExecutionState.REFUSED.value, ExecutionState.FAILED.value)
        or str(inp_int).lower() == "abstain"
        or str(exec_state).lower() == "abstain"
    ):
        return ConclusionMaturity.ABSTAIN.value

    # 2. Preflight / Unexecuted Permitted State
    if exec_state in (ExecutionState.PERMITTED.value, "PERMITTED"):
        return ConclusionMaturity.UNASSESSED.value

    # 3. Conflicted across alternative methods
    if concord in (DimensionGrade.CONFLICTED.value, GRADE_C, "conflicted"):
        return ConclusionMaturity.CONFLICTED.value

    # 3. Fragile: Violated assumptions, degraded execution, sensitive parameters, or suspect inputs
    if (
        exec_state == ExecutionState.DEGRADED.value
        or inp_int == GRADE_C
        or assump == GRADE_C
        or param_rob == GRADE_C
        or stat_sup in (GRADE_C, DimensionGrade.INSUFFICIENT.value, "INSUFFICIENT")
    ):
        return ConclusionMaturity.FRAGILE.value

    # 4. Replicated: Validated against external independent datasets/benchmarks
    if (
        ext_val == GRADE_A
        and param_rob in (GRADE_A, GRADE_B)
        and stat_sup == GRADE_A
        and inp_int == GRADE_A
        and assump in (GRADE_A, GRADE_B)
        and exec_state == ExecutionState.EXECUTED.value
    ):
        return ConclusionMaturity.REPLICATED.value

    # 5. Robust: Verified stable under parameter sweeps/perturbations
    if (
        param_rob == GRADE_A
        and stat_sup == GRADE_A
        and inp_int == GRADE_A
        and assump in (GRADE_A, GRADE_B)
        and exec_state == ExecutionState.EXECUTED.value
    ):
        return ConclusionMaturity.ROBUST.value

    # 6. Supported: High statistical support and verified inputs/assumptions on current data
    if (
        inp_int == GRADE_A
        and assump in (GRADE_A, GRADE_B)
        and stat_sup == GRADE_A
        and exec_state == ExecutionState.EXECUTED.value
    ):
        return ConclusionMaturity.SUPPORTED.value

    # 7. Preliminary / Tentative: Standard exploratory run with moderate support/assumptions
    return ConclusionMaturity.PRELIMINARY.value


def synthesize_conclusion_status(card: EvidenceCard | Dict[str, Any], abstain: bool = False) -> str:
    """Backward compatibility alias for synthesize_conclusion_maturity."""
    maturity = synthesize_conclusion_maturity(card, abstain=abstain)
    # If legacy callers expect TENTATIVE for PRELIMINARY
    return maturity


def attach_meta(
    payload: Dict[str, Any],
    *,
    method: str,
    backend: str,
    evidence_grade: str = GRADE_A,
    execution_state: Optional[str] = None,
    limitations: Optional[Iterable[str]] = None,
    abstain: bool = False,
    abstain_reason: Optional[str] = None,
    evidence_card: Optional[EvidenceCard | Dict[str, Any]] = None,
    conclusion_status: Optional[str] = None,
    conclusion_maturity: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a copy of payload with the standard plugin contract fields and EvidenceCard 2.0."""
    out = dict(payload)
    out["method"] = method
    out["backend"] = backend
    out["evidence_grade"] = evidence_grade
    out["limitations"] = list(limitations or [])
    out["abstain"] = bool(abstain)
    if abstain or abstain_reason:
        out["abstain_reason"] = abstain_reason or "Insufficient evidence or missing backend."

    # Determine execution state
    if execution_state is None:
        if abstain:
            execution_state = ExecutionState.REFUSED.value
        elif evidence_grade == GRADE_A:
            execution_state = ExecutionState.EXECUTED.value
        else:
            execution_state = ExecutionState.DEGRADED.value

    out["execution_state"] = execution_state

    # Construct or attach EvidenceCard
    if evidence_card is None:
        card = EvidenceCard(
            execution_state=execution_state,
            input_integrity=GRADE_A if evidence_grade in (GRADE_A, GRADE_B) else GRADE_C,
            assumption_validity=GRADE_B if evidence_grade == GRADE_A else GRADE_C,
            statistical_support=GRADE_B if evidence_grade == GRADE_A else GRADE_C,
            details={"execution_backend": backend, "method": method},
        )
    elif isinstance(evidence_card, EvidenceCard):
        card = evidence_card
    else:
        card = EvidenceCard(**evidence_card)

    status = conclusion_maturity or conclusion_status or card.synthesize_status(abstain=abstain)
    out["evidence_card"] = card.to_dict()
    out["conclusion_maturity"] = status
    out["conclusion_status"] = status  # Maintain backward compatibility

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
        execution_state=ExecutionState.REFUSED.value,
        input_integrity=DimensionGrade.UNTESTED.value,
        assumption_validity=DimensionGrade.UNTESTED.value,
        statistical_support=DimensionGrade.UNTESTED.value,
        parameter_robustness=DimensionGrade.UNTESTED.value,
        cross_method_concordance=DimensionGrade.UNTESTED.value,
        external_validation=DimensionGrade.UNTESTED.value,
        details={"refusal_reason": reason},
    )
    return attach_meta(
        payload,
        method=method,
        backend="none",
        evidence_grade=ABSTAIN,
        execution_state=ExecutionState.REFUSED.value,
        limitations=[reason],
        abstain=True,
        abstain_reason=reason,
        evidence_card=card,
        conclusion_maturity=ConclusionMaturity.ABSTAIN.value,
    )


# ---------------------------------------------------------------------------
# Purpose-aware evidence ceiling enforcement
# ---------------------------------------------------------------------------

# Ordered maturity levels (lowest to highest).
_MATURITY_ORDER = [
    ConclusionMaturity.UNASSESSED,
    ConclusionMaturity.ABSTAIN,
    ConclusionMaturity.FRAGILE,
    ConclusionMaturity.CONFLICTED,
    ConclusionMaturity.PRELIMINARY,
    ConclusionMaturity.SUPPORTED,
    ConclusionMaturity.ROBUST,
    ConclusionMaturity.REPLICATED,
]

_MATURITY_RANK = {m: i for i, m in enumerate(_MATURITY_ORDER)}


def cap_conclusion_by_purpose(
    maturity: str,
    ceiling: ConclusionMaturity,
) -> str:
    """Cap a ConclusionMaturity at the evidence ceiling defined by a ResearchPurpose.

    If the computed maturity exceeds the ceiling, it is reduced to the ceiling
    and a note is attached.  If the maturity is already at or below the ceiling,
    it is returned unchanged.
    """
    try:
        actual = ConclusionMaturity(maturity)
    except ValueError:
        return maturity
    if _MATURITY_RANK.get(actual, 0) <= _MATURITY_RANK.get(ceiling, 0):
        return maturity
    return ceiling.value
