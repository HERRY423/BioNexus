"""Negative and integrity tests for live-host MCP receipts."""

from pathlib import Path
from types import SimpleNamespace

import scripts.mcp_host_audit as mcp_host_audit
from scripts.mcp_host_audit import append_host_probe, find_receipt, verify_audit_log


def _append(path: Path, session_id: str = "ag-session-0001"):
    return append_host_probe(
        audit_path=path,
        host_name="antigravity",
        host_version="1.0-test",
        model="gemini-test",
        session_id=session_id,
        challenge="challenge-0000000001",
        human_approved=True,
        plugin_version="1.0.0-rc.1",
        server_version="2.1.0",
        tool_catalog=[{"name": "bionexus_host_probe"}],
    )


def test_two_receipts_form_valid_hash_chain(tmp_path):
    path = tmp_path / "audit.jsonl"
    first = _append(path)
    second = _append(path, session_id="ag-session-0002")

    events, errors = verify_audit_log(path)
    assert errors == []
    assert len(events) == 2
    assert second["previous_event_hash"] == first["event_hash"]
    assert find_receipt(events, second["event_hash"]) == second


def test_tampered_receipt_is_detected(tmp_path):
    path = tmp_path / "audit.jsonl"
    _append(path)
    content = path.read_text(encoding="utf-8")
    path.write_text(content.replace('"human_approved":true', '"human_approved":false'), encoding="utf-8")

    _events, errors = verify_audit_log(path)
    assert any("event_hash mismatch" in error for error in errors)


def test_invalid_existing_chain_refuses_append(tmp_path):
    import pytest

    path = tmp_path / "audit.jsonl"
    _append(path)
    path.write_text(path.read_text(encoding="utf-8").replace('"sequence":1', '"sequence":7'), encoding="utf-8")

    with pytest.raises(ValueError, match="refusing to append"):
        _append(path, session_id="ag-session-0002")


def test_git_helpers_use_explicit_executable_and_repo_local_ignore(monkeypatch, tmp_path):
    calls = []

    def _run(command, **kwargs):
        calls.append((command, kwargs))
        stdout = "abc123\n" if "rev-parse" in command else ""
        return SimpleNamespace(stdout=stdout)

    monkeypatch.delenv("BIONEXUS_GIT_COMMIT", raising=False)
    monkeypatch.setenv("BIONEXUS_GIT_EXECUTABLE", r"D:\Git\cmd\git.exe")
    monkeypatch.setattr(mcp_host_audit.subprocess, "run", _run)

    assert mcp_host_audit._git_commit(tmp_path) == "abc123"
    assert mcp_host_audit._git_dirty(tmp_path) is False
    assert calls[0][0][0] == r"D:\Git\cmd\git.exe"
    assert calls[1][0][0] == r"D:\Git\cmd\git.exe"
    assert calls[1][0][1:3] == ["-c", "core.excludesFile="]
