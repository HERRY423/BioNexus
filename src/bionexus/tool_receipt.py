"""BioNexus Tool Execution Receipt Engine (BNS-025).

Provides tamper-evident cryptographic execution receipts binding:
- plugin_id: identifier of the executing plugin
- plugin_version: exact release version of the executing plugin
- tool_name: canonical name of the invoked tool/function
- request_sha256: SHA-256 digest of canonical request payload
- response_sha256: SHA-256 digest of canonical response payload
- execution_status: status of the execution (SUCCESS, ABSTAIN, REJECTED, ERROR)
- receipt_hash: SHA-256 over unsigned canonical receipt dictionary
- optional hash-chain linkage for audit trails.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

PathLike = Union[str, Path]

SCHEMA_VERSION = "bionexus.tool-execution-receipt.v1"


class ToolReceiptLevel(IntEnum):
    """Declared receipt tier (BNS-025), not a verified trust state.

    LEVEL_0_CONTENT_INTEGRITY: Binds request SHA, response SHA, timestamp, and declared tool name.
        Proves tamper-evidence only. Producer identity is UNVERIFIED; backend fidelity is UNASSESSED.
        Certifies ZERO scientific evidence factors.
    LEVEL_1_HOST_OBSERVED: Recorded by an independent host observer (ChatGPT, Claude, Rosalind, BCTK).
        Records a claimed host observation; trusted observer verification is not implemented.
    LEVEL_2_PROVIDER_ATTESTED: Binds a provider cryptographic signature or independent verification attestation.
        Carries a claimed attestation; trusted signature verification is not implemented.
    """

    LEVEL_0_CONTENT_INTEGRITY = 0
    LEVEL_1_HOST_OBSERVED = 1
    LEVEL_2_PROVIDER_ATTESTED = 2


def canonical_json(data: Any) -> str:
    """Serialize object to strictly canonical deterministic JSON."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_canonical_payload(payload: Any) -> str:
    """Compute SHA-256 digest of canonical JSON serialization of payload."""
    if payload is None:
        return hashlib.sha256(b"null").hexdigest()
    if isinstance(payload, bytes):
        return hashlib.sha256(payload).hexdigest()
    if isinstance(payload, str):
        # If already a valid JSON string, parse and normalize canonical representation
        try:
            parsed = json.loads(payload)
            return hashlib.sha256(canonical_json(parsed).encode("utf-8")).hexdigest()
        except Exception:
            return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def compute_receipt_hash(unsigned_receipt: Dict[str, Any]) -> str:
    """Compute SHA-256 digest of the unsigned receipt payload."""
    payload = {k: v for k, v in unsigned_receipt.items() if k != "receipt_hash"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def create_tool_receipt(
    *,
    plugin_id: str,
    plugin_version: str,
    tool_name: str,
    request_payload: Any,
    response_payload: Any,
    execution_status: str = "SUCCESS",
    metadata: Optional[Dict[str, Any]] = None,
    receipt_level: int = ToolReceiptLevel.LEVEL_0_CONTENT_INTEGRITY.value,
    host_context: Optional[Dict[str, Any]] = None,
    attestation: Optional[Dict[str, Any]] = None,
    previous_receipt_hash: Optional[str] = None,
    chain_index: Optional[int] = None,
    receipt_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a tamper-evident cryptographic tool execution receipt (BNS-025).

    Args:
        plugin_id: Unique identifier for the plugin (e.g. 'bionexus-reliability').
        plugin_version: Version of the plugin (e.g. '1.0.0-rc.3').
        tool_name: Canonical tool or action name (e.g. 'query_uniprot').
        request_payload: Raw request dictionary, arguments, or JSON string.
        response_payload: Raw response dictionary, results, or JSON string.
        execution_status: Status ('SUCCESS', 'ABSTAIN', 'REJECTED', 'ERROR').
        metadata: Optional dictionary with auxiliary execution context.
        receipt_level: Tier level (0=Content Integrity, 1=Host Observed, 2=Provider Attested).
        host_context: Optional Level 1 host observer context.
        attestation: Optional Level 2 cryptographic provider/assessor attestation.
        previous_receipt_hash: Optional SHA-256 of the prior receipt for chaining.
        chain_index: Optional sequential integer in audit chain.
        receipt_id: Optional explicit receipt ID; generated if None.
        timestamp: Optional explicit ISO-8601 UTC timestamp; now() if None.

    Returns:
        A complete, signed receipt dictionary conforming to SCHEMA_VERSION.
    """
    if not plugin_id:
        raise ValueError("plugin_id cannot be empty")
    if not plugin_version:
        raise ValueError("plugin_version cannot be empty")
    if not tool_name:
        raise ValueError("tool_name cannot be empty")

    ts = timestamp or datetime.now(timezone.utc).isoformat()
    rid = receipt_id or f"RCPT-{uuid.uuid4().hex[:12]}"

    req_hash = hash_canonical_payload(request_payload)
    resp_hash = hash_canonical_payload(response_payload)

    receipt: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": rid,
        "receipt_level": int(receipt_level),
        "timestamp": ts,
        "plugin_id": str(plugin_id),
        "plugin_version": str(plugin_version),
        "tool_name": str(tool_name),
        "request_sha256": req_hash,
        "response_sha256": resp_hash,
        "execution_status": str(execution_status).upper(),
        "metadata": metadata or {},
    }

    if host_context is not None:
        receipt["host_context"] = host_context
    if attestation is not None:
        receipt["attestation"] = attestation
    if previous_receipt_hash is not None:
        receipt["previous_receipt_hash"] = previous_receipt_hash
    if chain_index is not None:
        receipt["chain_index"] = int(chain_index)

    receipt["receipt_hash"] = compute_receipt_hash(receipt)
    return receipt


def create_content_integrity_receipt(
    *,
    plugin_id: str,
    plugin_version: str,
    tool_name: str,
    request_payload: Any,
    response_payload: Any,
    execution_status: str = "SUCCESS",
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Level 0: Generate a Content Integrity Receipt proving payload hash integrity only."""
    return create_tool_receipt(
        plugin_id=plugin_id,
        plugin_version=plugin_version,
        tool_name=tool_name,
        request_payload=request_payload,
        response_payload=response_payload,
        execution_status=execution_status,
        metadata=metadata,
        receipt_level=ToolReceiptLevel.LEVEL_0_CONTENT_INTEGRITY.value,
        **kwargs,
    )


def create_host_observed_receipt(
    *,
    host: str,
    connector_id: str,
    tool_name: str,
    request_payload: Any,
    response_payload: Any,
    plugin_version: str = "1.0.0",
    execution_status: str = "SUCCESS",
    mcp_server_uri: Optional[str] = None,
    tool_schema_digest: Optional[str] = None,
    session_id: Optional[str] = None,
    transport: str = "mcp",
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Level 1: Generate a Host-Observed Execution Receipt recorded by an independent host observer."""
    host_ctx = {
        "host": str(host),
        "connector_id": str(connector_id),
        "mcp_server_uri": mcp_server_uri,
        "tool_schema_digest": tool_schema_digest or hashlib.sha256(tool_name.encode()).hexdigest(),
        "session_id": session_id or uuid.uuid4().hex,
        "transport": str(transport),
    }
    return create_tool_receipt(
        plugin_id=connector_id,
        plugin_version=plugin_version,
        tool_name=tool_name,
        request_payload=request_payload,
        response_payload=response_payload,
        execution_status=execution_status,
        metadata=metadata,
        receipt_level=ToolReceiptLevel.LEVEL_1_HOST_OBSERVED.value,
        host_context=host_ctx,
        **kwargs,
    )


def create_attested_tool_receipt(
    *,
    plugin_id: str,
    plugin_version: str,
    tool_name: str,
    request_payload: Any,
    response_payload: Any,
    attestation: Dict[str, Any],
    execution_status: str = "SUCCESS",
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Record a Level 2 attestation declaration; this does not verify its signature."""
    if not isinstance(attestation, dict) or not attestation:
        raise ValueError("Level 2 receipt requires non-empty attestation dictionary")
    return create_tool_receipt(
        plugin_id=plugin_id,
        plugin_version=plugin_version,
        tool_name=tool_name,
        request_payload=request_payload,
        response_payload=response_payload,
        execution_status=execution_status,
        metadata=metadata,
        receipt_level=ToolReceiptLevel.LEVEL_2_PROVIDER_ATTESTED.value,
        attestation=attestation,
        **kwargs,
    )


def verify_tool_receipt(
    receipt: Dict[str, Any],
    *,
    expected_request: Any = None,
    expected_response: Any = None,
    expected_plugin_id: Optional[str] = None,
    expected_plugin_version: Optional[str] = None,
    expected_tool_name: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """Verify self-consistent hash bindings, not producer identity or execution truth.

    Returns:
        (is_valid, list_of_error_strings)
    """
    errors: List[str] = []

    if not isinstance(receipt, dict):
        return False, ["Receipt must be a JSON dictionary"]

    schema = receipt.get("schema_version")
    if schema != SCHEMA_VERSION:
        errors.append(f"Invalid schema_version '{schema}', expected '{SCHEMA_VERSION}'")

    for key in ("receipt_level", "level"):
        if key in receipt and (type(receipt[key]) is not int or receipt[key] not in (0, 1, 2)):
            errors.append(f"Invalid {key}: expected integer 0, 1 or 2")
    if ("receipt_level" in receipt and "level" in receipt
            and receipt["receipt_level"] != receipt["level"]):
        errors.append("Conflicting receipt_level and level declarations")

    required_fields = [
        "receipt_id",
        "timestamp",
        "plugin_id",
        "plugin_version",
        "tool_name",
        "request_sha256",
        "response_sha256",
        "execution_status",
        "receipt_hash",
    ]
    for field in required_fields:
        if not receipt.get(field):
            errors.append(f"Missing or empty required field '{field}'")

    if errors:
        return False, errors

    # Verify self-consistent receipt hash
    computed_hash = compute_receipt_hash(receipt)
    recorded_hash = receipt.get("receipt_hash")
    if computed_hash != recorded_hash:
        errors.append(
            f"Receipt hash mismatch: recorded '{recorded_hash}', recomputed '{computed_hash}'"
        )

    # Verify request payload hash if provided
    if expected_request is not None:
        expected_req_hash = hash_canonical_payload(expected_request)
        if receipt.get("request_sha256") != expected_req_hash:
            errors.append(
                f"Request payload hash mismatch: recorded '{receipt.get('request_sha256')}', "
                f"expected '{expected_req_hash}'"
            )

    # Verify response payload hash if provided
    if expected_response is not None:
        expected_resp_hash = hash_canonical_payload(expected_response)
        if receipt.get("response_sha256") != expected_resp_hash:
            errors.append(
                f"Response payload hash mismatch: recorded '{receipt.get('response_sha256')}', "
                f"expected '{expected_resp_hash}'"
            )

    # Verify explicit expected identifiers
    if expected_plugin_id and receipt.get("plugin_id") != expected_plugin_id:
        errors.append(
            f"Plugin ID mismatch: recorded '{receipt.get('plugin_id')}', expected '{expected_plugin_id}'"
        )
    if expected_plugin_version and receipt.get("plugin_version") != expected_plugin_version:
        errors.append(
            f"Plugin version mismatch: recorded '{receipt.get('plugin_version')}', expected '{expected_plugin_version}'"
        )
    if expected_tool_name and receipt.get("tool_name") != expected_tool_name:
        errors.append(
            f"Tool name mismatch: recorded '{receipt.get('tool_name')}', expected '{expected_tool_name}'"
        )

    return len(errors) == 0, errors


def append_receipt_log(receipt: Dict[str, Any], log_path: PathLike) -> None:
    """Append a validated receipt to a JSON Lines log file."""
    valid, errors = verify_tool_receipt(receipt)
    if not valid:
        raise ValueError(f"Cannot append invalid receipt: {', '.join(errors)}")

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(receipt, ensure_ascii=False) + "\n")


def verify_receipt_log_chain(log_path: PathLike) -> Tuple[bool, List[str]]:
    """Verify full sequential hash-chain integrity of a receipt log file.

    Returns:
        (is_valid, list_of_error_strings)
    """
    path = Path(log_path)
    if not path.is_file():
        return False, [f"Receipt log file not found: {path}"]

    errors: List[str] = []
    receipts: List[Dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as handle:
        for line_num, line in enumerate(handle, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                item = json.loads(line_str)
                receipts.append(item)
            except Exception as exc:
                errors.append(f"Line {line_num}: Invalid JSON ({exc})")

    if errors:
        return False, errors

    prev_hash: Optional[str] = None
    for idx, r in enumerate(receipts):
        valid, r_errors = verify_tool_receipt(r)
        if not valid:
            errors.append(f"Receipt {idx} ({r.get('receipt_id', 'unknown')}): {', '.join(r_errors)}")
            continue

        if "previous_receipt_hash" in r:
            recorded_prev = r["previous_receipt_hash"]
            if idx == 0 and recorded_prev is not None:
                errors.append(f"Receipt 0 has unexpected previous_receipt_hash '{recorded_prev}'")
            elif idx > 0 and recorded_prev != prev_hash:
                errors.append(
                    f"Receipt {idx} chain break: previous_receipt_hash '{recorded_prev}' != '{prev_hash}'"
                )

        if "chain_index" in r:
            if r["chain_index"] != idx:
                errors.append(
                    f"Receipt {idx} sequence mismatch: chain_index {r['chain_index']} != {idx}"
                )

        prev_hash = r.get("receipt_hash")

    return len(errors) == 0, errors


def extract_evidence_factors_from_receipt(
    receipt: Dict[str, Any],
) -> Tuple[Set[str], List[str]]:
    """Check receipt integrity without promoting unverified authority claims.

    Receipt tiers, host_context and attestation are supplied by the caller.
    This module has no trusted observer or provider-signature verifier, so even
    a well-formed Level 1/2 receipt establishes no scientific evidence factors.
    Verified external assessments must use their own scoped trust contracts.
    """
    valid, errors = verify_tool_receipt(receipt)
    if not valid:
        return set(), [f"Tool receipt verification failed: {', '.join(errors)}"]

    status = receipt.get("execution_status", "")
    if not isinstance(status, str) or status.upper() != "SUCCESS":
        return set(), [f"Tool receipt execution_status '{status}' is not SUCCESS (no factors certified)"]

    level = receipt.get("receipt_level", receipt.get("level", 0))
    rid = receipt.get("receipt_id", "unknown")
    if level == ToolReceiptLevel.LEVEL_0_CONTENT_INTEGRITY.value:
        return set(), [
            f"Receipt {rid}: Level 0 Content Integrity receipt; self-consistent hash binding "
            "verified (producer_identity=UNVERIFIED, backend_fidelity=UNASSESSED, "
            "external_validation=UNASSESSED). Zero scientific evidence factors certified."
        ]
    label = "Host-Observed" if level == 1 else "Provider/Independent Attested"
    return set(), [
        f"Receipt {rid}: declared Level {level} {label} receipt; content integrity only. "
        "ATTESTATION_NOT_VERIFIED: no trusted observer or provider signature verification "
        "is configured in this receipt contract. producer_identity=UNVERIFIED, "
        "backend_fidelity=UNASSESSED, external_validation=UNASSESSED. "
        "Zero scientific evidence factors certified."
    ]


def extract_evidence_factors_from_receipt_log(
    log_path: PathLike,
) -> Tuple[Set[str], List[str]]:
    """Verify receipt log chain and extract all certified evidence factors from it.

    Returns:
        (set_of_verified_factors, list_of_audit_notes)
    """
    valid, errors = verify_receipt_log_chain(log_path)
    if not valid:
        return set(), [f"Receipt log chain verification failed: {', '.join(errors)}"]

    path = Path(log_path)
    all_factors: Set[str] = set()
    all_notes: List[str] = [f"Verified hash-chain log at {path}"]

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line_str = line.strip()
            if not line_str:
                continue
            try:
                receipt = json.loads(line_str)
                factors, notes = extract_evidence_factors_from_receipt(receipt)
                all_factors.update(factors)
                all_notes.extend(notes)
            except Exception:
                pass

    return all_factors, all_notes

