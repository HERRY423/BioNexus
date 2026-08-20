"""Tamper-evident receipts for live BioNexus MCP host acceptance.

This module deliberately records only bounded host-integration metadata. It is
not a security attestation and it does not turn a host transcript into
biological evidence. The append-only hash chain makes accidental or later
editing detectable by the acceptance verifier.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

AUDIT_SCHEMA = "bionexus.mcp-host-audit.v1"
GENESIS_HASH = "GENESIS"
_APPEND_LOCK = threading.Lock()
_HOST_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")


def _git_executable() -> str:
    """Return an explicit Git binary when GUI hosts do not inherit PATH."""
    return os.environ.get("BIONEXUS_GIT_EXECUTABLE", "").strip() or "git"


def canonical_json(value: Any) -> str:
    """Return stable JSON used by every audit hash."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _event_hash(event: Dict[str, Any]) -> str:
    unsigned = {key: value for key, value in event.items() if key != "event_hash"}
    return sha256_json(unsigned)


def _read_events(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    events: List[Dict[str, Any]] = []
    errors: List[str] = []
    if not path.exists():
        return events, errors

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
            continue
        if not isinstance(event, dict):
            errors.append(f"line {line_number}: event must be a JSON object")
            continue
        events.append(event)
    return events, errors


def verify_audit_log(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Verify sequence, previous-hash links, and event hashes."""
    events, errors = _read_events(path)
    previous_hash = GENESIS_HASH
    expected_sequence = 1

    for index, event in enumerate(events, start=1):
        if event.get("schema_version") != AUDIT_SCHEMA:
            errors.append(f"event {index}: unsupported schema_version")
        if event.get("sequence") != expected_sequence:
            errors.append(f"event {index}: expected sequence {expected_sequence}")
        if event.get("previous_event_hash") != previous_hash:
            errors.append(f"event {index}: previous_event_hash mismatch")
        computed_hash = _event_hash(event)
        if event.get("event_hash") != computed_hash:
            errors.append(f"event {index}: event_hash mismatch")
        previous_hash = str(event.get("event_hash", ""))
        expected_sequence += 1
    return events, errors


def _git_commit(repo_root: Optional[Path]) -> str:
    configured = os.environ.get("BIONEXUS_GIT_COMMIT", "").strip()
    if configured:
        return configured
    if repo_root is None:
        return "unknown"
    try:
        result = subprocess.run(
            [_git_executable(), "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _git_dirty(repo_root: Optional[Path]) -> Optional[bool]:
    configured = os.environ.get("BIONEXUS_GIT_DIRTY", "").strip().lower()
    if configured:
        if configured in {"false", "0", "no"}:
            return False
        if configured in {"true", "1", "yes"}:
            return True
        return None
    if repo_root is None:
        return None
    try:
        result = subprocess.run(
            [
                _git_executable(),
                "-c",
                "core.excludesFile=",
                "status",
                "--porcelain",
                "--untracked-files=normal",
            ],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def append_host_probe(
    *,
    audit_path: Path,
    host_name: str,
    host_version: str,
    model: str,
    session_id: str,
    challenge: str,
    human_approved: bool,
    plugin_version: str,
    server_version: str,
    tool_catalog: Iterable[Dict[str, Any]],
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Append one server-side host acceptance receipt and return it."""
    host_name = host_name.strip().lower()
    host_version = host_version.strip()
    model = model.strip()
    session_id = session_id.strip()
    challenge = challenge.strip()

    if not _HOST_RE.fullmatch(host_name):
        raise ValueError("host_name must be a lowercase host identifier")
    if not host_version:
        raise ValueError("host_version is required")
    if not model:
        raise ValueError("model is required")
    if not 8 <= len(session_id) <= 128:
        raise ValueError("session_id must contain 8-128 characters")
    if not 16 <= len(challenge) <= 256:
        raise ValueError("challenge must contain 16-256 characters")
    if not isinstance(human_approved, bool):
        raise ValueError("human_approved must be a boolean")

    audit_path = audit_path.resolve()
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    with _APPEND_LOCK:
        events, errors = verify_audit_log(audit_path)
        if errors:
            raise ValueError("refusing to append to invalid audit chain: " + "; ".join(errors))

        previous_hash = events[-1]["event_hash"] if events else GENESIS_HASH
        configured_dirty = bool(os.environ.get("BIONEXUS_GIT_DIRTY", "").strip())
        event: Dict[str, Any] = {
            "schema_version": AUDIT_SCHEMA,
            "sequence": len(events) + 1,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "host_acceptance_probe",
            "host_name": host_name,
            "host_version": host_version,
            "model": model,
            "session_id": session_id,
            "challenge_sha256": sha256_json({"challenge": challenge}),
            "human_approved": human_approved,
            "plugin_version": plugin_version,
            "server_name": "bionexus-local-mcp",
            "server_version": server_version,
            "git_commit": _git_commit(repo_root),
            "git_dirty": _git_dirty(repo_root),
            "git_dirty_source": "configured_snapshot" if configured_dirty else "git_status",
            "tool_catalog_sha256": sha256_json(list(tool_catalog)),
            "previous_event_hash": previous_hash,
        }
        event["event_hash"] = _event_hash(event)
        with audit_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(canonical_json(event) + "\n")
            handle.flush()
            # Flush is sufficient for this tamper-evident technical receipt.
            # Windows GUI-hosted stdio processes can block indefinitely in
            # FlushFileBuffers/os.fsync even after the bytes are readable.
            if os.name != "nt":
                os.fsync(handle.fileno())
        return event


def find_receipt(events: Iterable[Dict[str, Any]], event_hash: str) -> Optional[Dict[str, Any]]:
    """Return a receipt by hash, or None when the audit log does not contain it."""
    return next((event for event in events if event.get("event_hash") == event_hash), None)
