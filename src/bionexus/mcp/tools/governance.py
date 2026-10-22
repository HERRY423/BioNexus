from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

# This module is part of the installed package; a missing audit helper is an
# installation error, never a reason to silently discard host evidence.
from bionexus.mcp_host_audit import append_host_probe

logger = logging.getLogger("bionexus.mcp.governance")

async def tool_bionexus_warrant_check(
    query: str,
    data_metadata: Optional[Dict[str, Any]] = None,
    research_purpose: Optional[str] = None,
    lab_policy: Optional[str] = None,
    intent_keywords: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Pre-execution scientific warrant gate for full-privilege agent hosts.

    Wraps ``bionexus.intent_router.route_scientific_intent`` as a single MCP call
    that any host (Biomni, Claude Code, Codex, Cursor, ...) can invoke BEFORE
    executing model-generated analysis code. Returns the authoritative routing
    verdict, matched capability, blocked claims, remedies, and evidence ceiling.
    """
    from bionexus.mcp.transport import error_payload

    if not isinstance(query, str) or (data_metadata is not None and not isinstance(data_metadata, dict)):
        return error_payload('INVALID_ARGUMENTS', 'query must be a string and data_metadata an object or null.')
    meta = data_metadata or {}
    count_keys = ('num_donors', 'biological_replicates', 'donors_per_condition', 'eligible_sections',
                  'min_replicates_per_condition', 'conditions', 'n_spatial_spots')
    bool_keys = ('has_spatial_coords', 'spatial_colocalization', 'ligand_receptor_inference',
                 'perturbation', 'is_perturbation', 'temporal_evidence', 'time_series',
                 'pseudobulk_aggregated', 'is_pseudobulk', 'independent_validation',
                 'independent_patients_verified', 'reference_ground_truth', 'clinical_ground_truth',
                 'clinical_validation', 'regulatory_certification', 'is_integer_like', 'is_normalized')
    if any(key in meta and (type(meta[key]) is not int or meta[key] < 0) for key in count_keys):
        return error_payload('INVALID_ARGUMENTS', 'Declared counts require nonnegative JSON integers.')
    if any(key in meta and type(meta[key]) is not bool for key in bool_keys):
        return error_payload('INVALID_ARGUMENTS', 'Declared evidence flags require JSON booleans.')
    if any(key in meta and (not isinstance(meta[key], str) or not meta[key].strip())
           for key in ('claim_class', 'requested_claim_class')):
        return error_payload('INVALID_ARGUMENTS', 'An explicit claim class must be a nonempty string.')
    if ('claim_class' in meta and 'requested_claim_class' in meta
            and meta['claim_class'] != meta['requested_claim_class']):
        return error_payload('INVALID_ARGUMENTS', 'Conflicting explicit claim classes cannot be silently selected.')
    try:
        from bionexus.intent_router import route_scientific_intent
    except ImportError as exc:
        return error_payload('CORE_UNAVAILABLE', type(exc).__name__)

    try:
        decision = route_scientific_intent(
            query,
            data_path=None,
            data_metadata=data_metadata,
            allow_degraded=False,
            allow_frontier=False,
            research_purpose=research_purpose,
            override_justification="",
            lab_policy=lab_policy,
            intent_keywords=intent_keywords,
        )
    except Exception as exc:
        return error_payload('ROUTING_FAILED', type(exc).__name__)
    payload = decision.to_dict()
    payload["evidence_ceiling"] = _capability_evidence_ceiling(decision.matched_capability)

    # Attach Scientific Claim IR and Epistemic Warrant Evaluation (BNS-017)
    try:
        from bionexus.claim_semantics import (
            DeterministicClaimParser,
            DeterministicWarrantEngine,
            EvidenceProfile,
            enforce_governing_status,
        )

        meta = data_metadata or {}

        def _declared_true(*keys: str) -> bool:
            """Only a JSON boolean true may activate a conditional premise."""
            return any(meta.get(key) is True for key in keys)

        ev_prof = EvidenceProfile(
            spatial_colocalization=_declared_true("has_spatial_coords", "spatial_colocalization"),
            ligand_receptor_inference=_declared_true("ligand_receptor_inference"),
            perturbation=_declared_true("perturbation", "is_perturbation"),
            temporal_evidence=_declared_true("temporal_evidence", "time_series"),
            biological_replicates_count=(
                meta.get("num_donors")
                or meta.get("biological_replicates")
                or meta.get("donors_per_condition")
                or meta.get("eligible_sections")
                or 0
            ),
            pseudobulk_aggregated=_declared_true("pseudobulk_aggregated", "is_pseudobulk"),
            independent_validation=_declared_true("independent_validation", "independent_patients_verified"),
            reference_ground_truth=_declared_true("reference_ground_truth"),
            clinical_ground_truth=_declared_true("clinical_ground_truth", "clinical_validation"),
            regulatory_certification=_declared_true("regulatory_certification"),
        )
        explicit_cc = meta.get("claim_class") or meta.get("requested_claim_class")
        claim_ir = DeterministicClaimParser.parse(
            query,
            explicit_claim_class=explicit_cc,
            data_metadata=meta,
        )
        if claim_ir.metadata.get('unsupported_explicit_claim_class'):
            return error_payload('INVALID_ARGUMENTS', 'Unsupported explicit claim class; no weaker class was substituted.')
        w_eval = DeterministicWarrantEngine.evaluate(claim_ir, ev_prof)
        enforce_governing_status(w_eval, decision.status.value)
        payload["scientific_claim_ir"] = claim_ir.to_dict()
        payload["claim_warrant_evaluation"] = w_eval.to_dict()
    except Exception as exc:
        prior_status = payload['status']
        payload = error_payload('CLAIM_EVALUATION_FAILED', type(exc).__name__)
        payload['preflight_status_before_error'] = prior_status
        payload['claim_evaluation_error'] = type(exc).__name__

    payload["host_integration"] = {
        "intended_hosts": ["biomni", "claude_code", "codex", "cursor", "any_mcp_host"],
        "call_timing": "Invoke BEFORE executing model-generated analysis code.",
        "motivation": (
            "Full-privilege agent platforms (e.g. Biomni) document that they execute "
            "LLM-generated code with full system privileges; sandboxing addresses OS-level "
            "risk, not scientific validity. This gate permits the compute but caps what the "
            "run may claim."
        ),
    }
    payload["boundary"] = (
        "Conditional preflight under supplied declarations only; no scientific facts, "
        "reviewer identities, independence, regulatory status or analysis execution are authenticated; "
        "not clinical validation."
    )
    return payload


def _capability_evidence_ceiling(capability: Any) -> Optional[str]:
    """Best-effort string form of a CapabilityContract's evidence ceiling."""
    if capability is None:
        return None
    raw = getattr(capability, "evidence_ceiling", None)
    value = getattr(raw, "value", raw)
    return str(value) if value is not None else None


async def tool_bionexus_host_probe(
    host_name: str,
    host_version: str,
    model: str,
    session_id: str,
    challenge: str,
    human_approved: bool,
) -> Dict[str, Any]:
    """Record a bounded server-side receipt for a live MCP host session."""
    configured_path = os.environ.get("BIONEXUS_MCP_AUDIT_LOG", "").strip()
    if not configured_path:
        raise ValueError(
            "BIONEXUS_MCP_AUDIT_LOG is not configured; refusing to claim a live host receipt"
        )

    repo_root = Path(__file__).resolve()
    while repo_root.parent != repo_root:
        if (repo_root / "pyproject.toml").is_file():
            break
        repo_root = repo_root.parent
    audit_path = Path(configured_path)
    if not audit_path.is_absolute():
        audit_path = repo_root / audit_path

    from bionexus.evidence_contract import evidence_contract
    from bionexus.mcp.schemas import public_tools_schema
    from bionexus.mcp.server import SERVER_VERSION
    from bionexus.mcp.transport import runtime_identity
    from bionexus.versions import PLUGIN_VERSION

    event = append_host_probe(
        audit_path=audit_path,
        host_name=host_name,
        host_version=host_version,
        model=model,
        session_id=session_id,
        challenge=challenge,
        human_approved=human_approved,
        plugin_version=PLUGIN_VERSION,
        server_version=SERVER_VERSION,
        tool_catalog=public_tools_schema(),
        # Installed wheels need not belong to a Git checkout. Never spawn Git
        # in a live MCP callback: bind the immutable package bytes instead.
        repo_root=None,
        runtime_identity=runtime_identity(),
    )
    return {
        "status": "RECORDED",
        "acceptance_verdict": "pending_run_validation",
        "human_approved": event['human_approved'],
        "host_identity_source": "DECLARED",
        "approval_source": "DECLARED",
        "git_metadata_source": "CONFIGURED_OR_UNKNOWN_NOT_QUERIED",
        "runtime_identity": event['runtime_identity'],
        "evidence_contract": evidence_contract(scope='One local MCP call and audit record; host identity and approval remain declared.'),
        "receipt_event_hash": event["event_hash"],
        "sequence": event["sequence"],
        "timestamp": event["timestamp"],
        "host_name": event["host_name"],
        "session_id": event["session_id"],
        "plugin_version": event["plugin_version"],
        "git_commit": event["git_commit"],
        "git_dirty": event["git_dirty"],
        "git_dirty_source": event["git_dirty_source"],
        "tool_catalog_sha256": event["tool_catalog_sha256"],
        "boundary": (
            "This receipt proves one local MCP server call and a tamper-evident log entry only; "
            "it is not biological validation, clinical validation, or cryptographic attestation."
        ),
    }


