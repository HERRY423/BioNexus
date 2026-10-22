"""Shared strict MCP tool boundary for SDK and legacy stdio transports.

Transport success is not scientific authorization. The text and structured
projections contain the same JSON payload, including failures.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from bionexus.evidence_contract import evidence_contract


@lru_cache(maxsize=1)
def runtime_identity() -> dict[str, Any]:
    """Identify package bytes observed by this process; not remote attestation."""
    root = Path(__file__).resolve().parents[1]
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(root.rglob('*')) if p.is_file() and p.suffix in {'.py', '.json'}}
    raw = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    try:
        sdk = importlib.metadata.version('mcp')
    except importlib.metadata.PackageNotFoundError:
        sdk = 'NOT_INSTALLED'
    return {'schema': 'bionexus.mcp-runtime.v1',
            'package_tree_sha256': hashlib.sha256(raw).hexdigest(),
            'package_file_count': len(files), 'mcp_sdk_version': sdk,
            'identity_basis': 'LOCAL_PACKAGE_BYTES_AT_PROCESS_START',
            'remote_attestation': False}


def error_payload(code: str, message: str) -> dict[str, Any]:
    return {'status': 'TOOL_UNAVAILABLE' if code == 'UNKNOWN_TOOL' else 'FAILED',
            'error': {'code': code, 'message': message},
            'evidence_contract': evidence_contract(scope='No positive assessment: MCP tool call did not complete.'),
            'boundary': 'Transport failure is not a scientific finding or a negative biological result.'}


def tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    payload = dict(payload, runtime_identity=dict(runtime_identity()))
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True)
    return {'content': [{'type': 'text', 'text': text}],
            'structuredContent': {'result': text}, 'isError': is_error}


async def call_tool(name: str, arguments: Any) -> dict[str, Any]:
    # Delayed import avoids a schemas -> tools -> transport cycle.
    from jsonschema import Draft202012Validator

    from bionexus.mcp.schemas import TOOL_ADAPTER_MAP, public_tools_schema
    schema = next((t['inputSchema'] for t in public_tools_schema() if t['name'] == name), None)
    if schema is None:
        return tool_result(error_payload('UNKNOWN_TOOL', 'Tool is not in the advertised catalog.'), is_error=True)
    try:
        # JSON forbids NaN/Infinity; reject Python callers that evade wire parsing.
        json.dumps(arguments, allow_nan=False)
        Draft202012Validator(schema).validate(arguments)
    except Exception:
        return tool_result(error_payload('INVALID_ARGUMENTS', 'Arguments do not satisfy the advertised input schema.'), is_error=True)
    try:
        result = await TOOL_ADAPTER_MAP[name](arguments)
        if result.get('error') and result.get('status') not in {'FAILED', 'TOOL_UNAVAILABLE'}:
            result = error_payload('TOOL_REPORTED_ERROR', 'Tool reported an execution or upstream service error.')
        return tool_result(result, is_error=result.get('status') in {'FAILED', 'TOOL_UNAVAILABLE'})
    except Exception as exc:
        # Preserve the error type, never echo secrets, input data or private paths.
        return tool_result(error_payload('TOOL_EXECUTION_FAILED', type(exc).__name__), is_error=True)
