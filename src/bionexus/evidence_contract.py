"""Positive-output semantics shared by existing evidence and warrant records.

This is a qualification of an assessment, not a new evidence store or authority.
It deliberately cannot attest scientific truth or authenticate a reviewer.
Standard library only: the passive bundle reader also runs with python -S.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "bionexus.evidence-state.v1"
IMPLEMENTATION_REVISION = "p0a-1"
RULE_REVISION = "positive-output-v1"
ENUMS = {
    "assessment_kind": ("CONDITIONAL", "ARTIFACT_REVIEW", "BUNDLE_INTEGRITY", "EXTERNAL_REVIEW", "UNACCEPTED"),
    "outcome": ("POSITIVE", "RESTRICTED", "UNKNOWN"),
    "positive_basis": ("NONE", "DECLARED_PREMISES", "CHECKED_ARTIFACTS", "CONSISTENT_BYTES", "BOUND_RESPONSE_AND_DECLARED_REVIEW"),
    "input_integrity": ("UNKNOWN", "CHECKED", "INVALID"),
    "analysis_execution": ("UNKNOWN", "SUCCESS_REPORTED_AND_BOUND", "FAILED_OR_UNRESOLVED"),
    "premises": ("UNKNOWN", "DECLARED", "ARTIFACT_CHECKED_WITH_DECLARED_CONTEXT"),
    "human_review": ("UNKNOWN", "RECORDED_UNAUTHENTICATED"),
    "reviewer_identity": ("UNKNOWN", "DECLARED"),
    "independence": ("UNKNOWN",),
    "support_status": ("CANDIDATE_CORE", "EXPERIMENTAL", "UNACCEPTED"),
}
CONSTANTS = {"schema": SCHEMA, "scientific_authorization": "NONE",
             "scientific_facts_verified": False, "implementation_revision": IMPLEMENTATION_REVISION,
             "rule_revision": RULE_REVISION}
BASES = {"CONDITIONAL": "DECLARED_PREMISES", "ARTIFACT_REVIEW": "CHECKED_ARTIFACTS",
         "BUNDLE_INTEGRITY": "CONSISTENT_BYTES", "EXTERNAL_REVIEW": "BOUND_RESPONSE_AND_DECLARED_REVIEW"}


def validate_evidence_contract(value: Any) -> dict[str, Any]:
    """Reject unknown versions/enums and inconsistent positive projections.

    Validation proves only contract conformance, never the assertions it carries.
    """
    if not isinstance(value, dict) or set(value) != set(ENUMS) | set(CONSTANTS) | {"scope", "observations"}:
        raise ValueError("Evidence-state contract has missing or unknown fields")
    for key, expected in CONSTANTS.items():
        if type(value[key]) is not type(expected) or value[key] != expected:
            raise ValueError(f"Unsupported evidence-state {key}")
    for key, options in ENUMS.items():
        if not isinstance(value[key], str) or value[key] not in options:
            raise ValueError(f"Unknown evidence-state {key}")
    if not isinstance(value["scope"], str) or not value["scope"].strip():
        raise ValueError("A positive-output scope must be explicit")
    observations = value["observations"]
    if (not isinstance(observations, list) or any(not isinstance(x, str) or not x.strip() for x in observations)
            or len(observations) != len(set(observations))):
        raise ValueError("Observations must be distinct nonempty identifiers")
    if (value["human_review"] == "UNKNOWN") != (value["reviewer_identity"] == "UNKNOWN"):
        raise ValueError("Review record and identity source disagree")
    if value["outcome"] == "POSITIVE":
        if value["positive_basis"] != BASES.get(value["assessment_kind"]):
            raise ValueError("Positive basis does not match assessment kind")
        if value["support_status"] == "UNACCEPTED":
            raise ValueError("Unaccepted surfaces cannot issue positive contracts")
        if value["assessment_kind"] != "CONDITIONAL" and (value["input_integrity"] != "CHECKED" or not observations):
            raise ValueError("Artifact positives require identified checks")
        if value["analysis_execution"] == "FAILED_OR_UNRESOLVED" and value["assessment_kind"] == "EXTERNAL_REVIEW":
            raise ValueError("Failed execution cannot support an external positive")
        if value["assessment_kind"] == "EXTERNAL_REVIEW" and (
                value["human_review"] != "RECORDED_UNAUTHENTICATED"
                or value["analysis_execution"] != "SUCCESS_REPORTED_AND_BOUND"):
            raise ValueError("External positives require bound response and explicit review")
    elif value["positive_basis"] != "NONE":
        raise ValueError("Nonpositive outcomes cannot carry a positive basis")
    if value["assessment_kind"] == "CONDITIONAL" and (
            value["premises"] != "DECLARED" or value["input_integrity"] != "UNKNOWN"
            or value["analysis_execution"] != "UNKNOWN" or observations):
        raise ValueError("Declared conditions cannot become checked facts")
    return value


def evidence_contract(kind: str = "UNACCEPTED", *, positive: bool = False,
                      scope: str = "No accepted positive-output interpretation.",
                      observations: list[str] | None = None, input_integrity: str = "UNKNOWN",
                      execution: str = "UNKNOWN", reviewed: bool = False,
                      support: str = "EXPERIMENTAL") -> dict[str, Any]:
    if type(positive) is not bool or type(reviewed) is not bool:
        raise ValueError("Positive and review states require booleans")
    return validate_evidence_contract({
        **CONSTANTS, "assessment_kind": kind, "outcome": "POSITIVE" if positive else "RESTRICTED",
        "positive_basis": BASES.get(kind, "NONE") if positive else "NONE",
        "input_integrity": input_integrity, "analysis_execution": execution,
        "premises": "DECLARED" if kind in {"CONDITIONAL", "EXTERNAL_REVIEW"} else
                    "ARTIFACT_CHECKED_WITH_DECLARED_CONTEXT" if kind == "ARTIFACT_REVIEW" else "UNKNOWN",
        "human_review": "RECORDED_UNAUTHENTICATED" if reviewed else "UNKNOWN",
        "reviewer_identity": "DECLARED" if reviewed else "UNKNOWN", "independence": "UNKNOWN",
        "support_status": "UNACCEPTED" if kind == "UNACCEPTED" else support,
        "scope": scope, "observations": list(observations or []),
    })


def conditional_contract(positive: bool, *, scope: str = "If supplied declarations hold, the stated rule conditions are satisfied.",
                         support: str = "CANDIDATE_CORE", reviewed: bool = False) -> dict[str, Any]:
    return evidence_contract("CONDITIONAL", positive=positive, scope=scope, support=support, reviewed=reviewed)


def contract_text(value: dict[str, Any]) -> str:
    """One consumer rendering for CLI, Markdown and review reports."""
    c = validate_evidence_contract(value)
    return (f"Evidence contract: {c['schema']} | {c['assessment_kind']} / {c['outcome']} / {c['positive_basis']}\n"
            f"Scope: {c['scope']}\n"
            f"Premises: {c['premises']}; analysis execution: {c['analysis_execution']}; "
            f"human review: {c['human_review']}; independence: {c['independence']}. "
            "Scientific facts verified: false; scientific authorization: NONE.")


def contract_schema() -> dict[str, Any]:
    """Structural schema; validate_evidence_contract also enforces transitions."""
    props: dict[str, Any] = {key: {"enum": list(options)} for key, options in ENUMS.items()}
    props.update({key: {"const": value} for key, value in CONSTANTS.items()})
    props.update(scope={"type": "string", "minLength": 1},
                 observations={"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True})
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": SCHEMA,
            "type": "object", "additionalProperties": False, "required": list(props), "properties": props}


def interpret_positive_output(payload: dict[str, Any], *, surface: str) -> dict[str, Any]:
    """Consumer gate: a legacy success flag alone has no accepted interpretation.

    Never use this local conformance check as authentication of a remote producer.
    The caller must still preserve source context and bound artifacts.
    """
    import json
    from pathlib import Path
    inventory = json.loads((Path(__file__).parent / "data/positive-output-surfaces.v1.json").read_text(encoding="utf-8"))
    entry = next((item for item in inventory["surfaces"] if item["surface"] == surface), None)
    if entry is None or entry["status"] == "UNACCEPTED":
        raise ValueError("Surface is outside the accepted positive-output contract")
    contract = validate_evidence_contract(payload.get("evidence_contract"))
    if contract["assessment_kind"] != entry["assessment_kind"] or contract["support_status"] != entry["status"]:
        raise ValueError("Output cannot borrow another surface's support or assessment kind")
    if contract["outcome"] == "POSITIVE":
        if surface == 'mcp:bionexus_warrant_check':
            if payload.get('claim_evaluation_error') or payload.get('error'):
                raise ValueError('Failed MCP evaluation cannot carry a positive contract')
            nested = payload.get('claim_warrant_evaluation')
            if not isinstance(nested, dict):
                raise ValueError('MCP preflight requires a separate completed claim assessment')
            nested_contract = validate_evidence_contract(nested.get('evidence_contract'))
            if (nested.get('governing_status') != payload.get('status')
                    or nested_contract['assessment_kind'] != 'CONDITIONAL'
                    or (nested_contract['outcome'] == 'POSITIVE') != (nested.get('is_fully_warranted') is True)):
                raise ValueError('MCP route and nested claim assessment disagree')
            # A permitted workflow can still have an unwarranted broader claim.
            # The top-level scope is routing feasibility, never claim authority.
        kind = contract["assessment_kind"]
        if kind == "ARTIFACT_REVIEW" and (payload.get("overall_status") != "ROBUST_PASS" or payload.get("passed") is not True):
            raise ValueError("Positive contract conflicts with the DE audit outcome")
        if kind == "BUNDLE_INTEGRITY" and payload.get("status") != "CONSISTENT":
            raise ValueError("Positive contract conflicts with bundle consistency")
        for flag in ("is_fully_warranted", "claim_warranted", "is_warranted"):
            if flag in payload and payload[flag] is not True:
                raise ValueError("Positive contract conflicts with the declared conditional result")
        positive_maturities = {"PRELIMINARY", "SUPPORTED", "ROBUST", "REPLICATED"}
        for field in ("claim_maturity", "evidence_maturity", "conclusion_maturity", "conclusion_status"):
            if field in payload and payload[field] not in positive_maturities:
                raise ValueError("Positive contract conflicts with the primary maturity outcome")
        # A scoped disclaimer may legitimately have evidence_ceiling=UNASSESSED.
        # A deployment BLOCK also does not by itself invalidate a warrant.
        if surface in {"cli:route", "mcp:bionexus_warrant_check"} or surface.endswith(".route_scientific_intent"):
            if payload.get("status") not in {"PERMITTED", "PERMITTED_WITH_LIMITS", "DEGRADED_ADVISORY"}:
                raise ValueError("Positive contract conflicts with the routing outcome")
        if surface.endswith(".PolicyDecision"):
            nested = payload.get("warrant")
            if not isinstance(nested, dict) or nested.get("evidence_contract") != contract:
                raise ValueError("Policy and warrant contracts disagree")
            interpret_positive_output(nested, surface="python:bionexus.warrant.WarrantAssessment")
        if payload.get("execution_state") in {"FAILED", "REFUSED", "PERMITTED", "PERMITTED_WITH_LIMITS"}:
            raise ValueError("Nonexecution cannot carry a positive result contract")
    return {"positive": contract["outcome"] == "POSITIVE", "basis": contract["positive_basis"],
            "scope": contract["scope"], "scientific_facts_verified": False, "scientific_authorization": "NONE"}
