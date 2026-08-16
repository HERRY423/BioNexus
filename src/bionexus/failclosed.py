"""
BioNexus Fail-Closed Execution Gate (BNS-005 §7).

Philosophy: **knowing when not to compute is a scientific capability.**
The most scarce BioNexus API is not `run()` — it is `prevent_invalid_run()`.

The closed-by-default mapping (BNS-AD-014):

    missing evidence            -> ABSTAIN (request data)
    invalid input               -> REFUSE
    backend unavailable         -> DEGRADE WITH DISCLOSURE
    assumption violated         -> BLOCK CLAIM
    claim beyond warrant        -> BLOCK CLAIM
    external validation absent  -> CAP EVIDENCE LEVEL

Every row prevents an invalid run or an invalid claim *before* compute.
`prevent_invalid_run()` is the single canonical entry point: hosts SHOULD
call it before any execution and MUST honor its verdict.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from bionexus.abi import enforce_evidence_ceiling
from bionexus.failures import classify_violation
from bionexus.intent_router import RoutingDecision, RoutingStatus, route_scientific_intent


@dataclass
class PreventionDecision:
    """The verdict of the fail-closed gate for one requested run."""

    prevented: bool
    prevention_kind: Optional[str]  # row of the fail-closed table, None when permitted
    action: str  # ABSTAIN | REFUSE | DEGRADE WITH DISCLOSURE | BLOCK CLAIM | CAP EVIDENCE LEVEL | RUN PERMITTED
    reason: str
    failure_mode_ids: List[str] = field(default_factory=list)
    remedies: List[str] = field(default_factory=list)
    missing_data_requests: List[str] = field(default_factory=list)
    claimed_maturity: Optional[str] = None
    warranted_maturity: Optional[str] = None
    routing: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out = asdict(self)
        return out


# The normative fail-closed table (BNS-AD-014)
FAIL_CLOSED_TABLE: List[Dict[str, str]] = [
    {"condition": "missing evidence", "prevention_kind": "MISSING_EVIDENCE", "action": "ABSTAIN (request data)"},
    {"condition": "invalid input", "prevention_kind": "INVALID_INPUT", "action": "REFUSE"},
    {"condition": "backend unavailable", "prevention_kind": "BACKEND_UNAVAILABLE", "action": "DEGRADE WITH DISCLOSURE"},
    {"condition": "assumption violated", "prevention_kind": "ASSUMPTION_VIOLATED", "action": "BLOCK CLAIM"},
    {"condition": "claim beyond warrant", "prevention_kind": "CLAIM_BEYOND_WARRANT", "action": "BLOCK CLAIM"},
    {"condition": "external validation absent", "prevention_kind": "EXTERNAL_VALIDATION_ABSENT", "action": "CAP EVIDENCE LEVEL"},
]

# Violation signatures that indicate input-semantics failures vs assumption failures
_INPUT_SIGNATURES = ("normalized", "integer", "spatial spots", "coordinates", "zero events", "missing required input")
_ASSUMPTION_SIGNATURES = ("replicat", "pseudoreplication", "assumption", "distribution", "mechanism", "censor")


def _classify_prevention_kind(decision: RoutingDecision) -> str:
    """Map a refused routing decision onto its fail-closed row."""
    joined = " ".join(decision.violations).lower()
    if "forbidden claim" in joined:
        return "CLAIM_BEYOND_WARRANT"
    if any(sig in joined for sig in _INPUT_SIGNATURES):
        return "INVALID_INPUT"
    if any(sig in joined for sig in _ASSUMPTION_SIGNATURES):
        return "ASSUMPTION_VIOLATED"
    return "ASSUMPTION_VIOLATED"  # conservative default: blocked, never waved through


def prevent_invalid_run(
    query: str,
    *,
    data_metadata: Optional[Dict[str, Any]] = None,
    claimed_maturity: Optional[str] = None,
    has_external_validation: bool = False,
    allow_degraded: bool = False,
) -> PreventionDecision:
    """
    The canonical fail-closed gate (BNS-AD-013).

    Evaluates a requested run against the scientific contract BEFORE any
    compute and returns the prevention verdict. Hosts call this instead of
    `run()` first: an unpervised `run()` of an invalid request is a
    conformance violation (BNS-HC-002).
    """
    decision = route_scientific_intent(
        query=query,
        data_metadata=data_metadata,
        allow_degraded=allow_degraded,
    )
    routing_dict = decision.to_dict()
    failure_ids = sorted({fid for v in decision.violations for fid in classify_violation(v)})

    # 1. Missing evidence -> ABSTAIN (request data)
    if decision.status == RoutingStatus.NEEDS_DATA:
        return PreventionDecision(
            prevented=True,
            prevention_kind="MISSING_EVIDENCE",
            action="ABSTAIN (request data)",
            reason=decision.rationale,
            failure_mode_ids=failure_ids,
            remedies=decision.remedies,
            missing_data_requests=decision.missing_data_requests,
            routing=routing_dict,
        )

    # 2./4./5. Refusals -> REFUSE or BLOCK CLAIM by failure class
    if decision.status == RoutingStatus.ABSTAIN:
        kind = _classify_prevention_kind(decision)
        action = "BLOCK CLAIM" if kind == "CLAIM_BEYOND_WARRANT" else "REFUSE"
        return PreventionDecision(
            prevented=True,
            prevention_kind=kind,
            action=action,
            reason=decision.rationale,
            failure_mode_ids=failure_ids,
            remedies=decision.remedies,
            routing=routing_dict,
        )

    # 3. Backend unavailable with consent -> DEGRADE WITH DISCLOSURE
    if decision.status == RoutingStatus.DEGRADED_ADVISORY:
        return PreventionDecision(
            prevented=True,
            prevention_kind="BACKEND_UNAVAILABLE",
            action="DEGRADE WITH DISCLOSURE",
            reason=decision.rationale,
            failure_mode_ids=sorted(set(failure_ids) | {"BN-F010"}),
            remedies=decision.remedies,
            routing=routing_dict,
        )

    # 6. External validation absent -> CAP EVIDENCE LEVEL
    if claimed_maturity and decision.matched_capability is not None:
        warranted = enforce_evidence_ceiling(
            decision.matched_capability.id,
            str(claimed_maturity).upper(),
            has_external_validation=has_external_validation,
        )
        if warranted != str(claimed_maturity).upper():
            return PreventionDecision(
                prevented=False,
                prevention_kind="EXTERNAL_VALIDATION_ABSENT",
                action="CAP EVIDENCE LEVEL",
                reason=(
                    f"Claimed maturity {claimed_maturity} exceeds the evidence ceiling of "
                    f"'{decision.matched_capability.id}' without external validation; "
                    f"capped to {warranted} (BNS-CC-013)."
                ),
                failure_mode_ids=["BN-F012"],
                claimed_maturity=str(claimed_maturity).upper(),
                warranted_maturity=warranted,
                routing=routing_dict,
            )
        return PreventionDecision(
            prevented=False,
            prevention_kind=None,
            action="RUN PERMITTED",
            reason=decision.rationale,
            claimed_maturity=str(claimed_maturity).upper(),
            warranted_maturity=warranted,
            routing=routing_dict,
        )

    # Clean permitted run
    return PreventionDecision(
        prevented=False,
        prevention_kind=None,
        action="RUN PERMITTED",
        reason=decision.rationale,
        routing=routing_dict,
    )
