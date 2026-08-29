"""BioNexus Tool Execution Receipt Engine (BNS-021).

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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

PathLike = Union[str, Path]

SCHEMA_VERSION = "bionexus.tool-execution-receipt.v1"


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
    previous_receipt_hash: Optional[str] = None,
    chain_index: Optional[int] = None,
    receipt_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a tamper-evident cryptographic tool execution receipt.

    Args:
        plugin_id: Unique identifier for the plugin (e.g. 'bionexus-reliability').
        plugin_version: Version of the plugin (e.g. '1.0.0-rc.3').
        tool_name: Canonical tool or action name (e.g. 'query_uniprot').
        request_payload: Raw request dictionary, arguments, or JSON string.
        response_payload: Raw response dictionary, results, or JSON string.
        execution_status: Status ('SUCCESS', 'ABSTAIN', 'REJECTED', 'ERROR').
        metadata: Optional dictionary with auxiliary execution context.
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
        "timestamp": ts,
        "plugin_id": str(plugin_id),
        "plugin_version": str(plugin_version),
        "tool_name": str(tool_name),
        "request_sha256": req_hash,
        "response_sha256": resp_hash,
        "execution_status": str(execution_status).upper(),
        "metadata": metadata or {},
    }

    if previous_receipt_hash is not None:
        receipt["previous_receipt_hash"] = previous_receipt_hash
    if chain_index is not None:
        receipt["chain_index"] = int(chain_index)

    receipt["receipt_hash"] = compute_receipt_hash(receipt)
    return receipt


def verify_tool_receipt(
    receipt: Dict[str, Any],
    *,
    expected_request: Any = None,
    expected_response: Any = None,
    expected_plugin_id: Optional[str] = None,
    expected_plugin_version: Optional[str] = None,
    expected_tool_name: Optional[str] = None,
) -> Tuple[bool, List[str]]:
    """Verify cryptographic validity and content integrity of a tool receipt.

    Returns:
        (is_valid, list_of_error_strings)
    """
    errors: List[str] = []

    if not isinstance(receipt, dict):
        return False, ["Receipt must be a JSON dictionary"]

    schema = receipt.get("schema_version")
    if schema != SCHEMA_VERSION:
        errors.append(f"Invalid schema_version '{schema}', expected '{SCHEMA_VERSION}'")

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
