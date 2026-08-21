"""Strict tests for the real Antigravity host acceptance gate."""

import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

import evals.antigravity_acceptance as antigravity_acceptance
from bionexus.versions import VERSION
from evals.antigravity_acceptance import (
    RUN_SCHEMA,
    build_live_report,
    build_request,
    validate_live_run,
)
from scripts import mcp_host_audit


def _receipt(tmp_path, monkeypatch, *, dirty=False):
    monkeypatch.setattr(mcp_host_audit, "_git_commit", lambda _root: "a" * 40)
    monkeypatch.setattr(mcp_host_audit, "_git_dirty", lambda _root: dirty)
    audit_path = tmp_path / "mcp-audit.jsonl"
    event = mcp_host_audit.append_host_probe(
        audit_path=audit_path,
        host_name="antigravity",
        host_version="1.2.3",
        model="gemini-test",
        session_id="ag-session-0001",
        challenge="challenge-0000000001",
        human_approved=True,
        plugin_version=VERSION,
        server_version="2.1.0",
        tool_catalog=[{"name": "bionexus_host_probe"}],
        repo_root=REPO_ROOT,
    )
    return audit_path, event


def _run(request, event):
    records = []
    for case in request["cases"]:
        records.append(
            {
                "capability_id": case["capability_id"],
                "input_hash": case["input_hash"],
                "trap_id": case["trap_id"],
                "observed_status": (
                    "ABSTAIN" if "overclaim" in case["trap_id"] or "hallucination" in case["trap_id"] else "PERMITTED"
                ),
                "warrant_text": "Bounded host rationale with explicit evidence limits.",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "session_id": "ag-session-0001",
                    "receipt_event_hash": event["event_hash"],
                },
            }
        )
    return {
        "schema_version": RUN_SCHEMA,
        "host": "antigravity",
        "host_version": "1.2.3",
        "model": "gemini-test",
        "execution_mode": "live_mcp",
        "is_live": True,
        "human_approved": True,
        "session_id": "ag-session-0001",
        "receipt_event_hash": event["event_hash"],
        "request_sha256": request["request_sha256"],
        "plugin_version": VERSION,
        "records": records,
    }


def test_valid_live_run_passes_and_preserves_scope(tmp_path, monkeypatch):
    request = build_request(REPO_ROOT / "evals" / "datasets" / "l2_agent_claims.yaml")
    audit_path, event = _receipt(tmp_path, monkeypatch)
    run = _run(request, event)

    errors, receipt = validate_live_run(run, request, audit_path)
    report = build_live_report(run, request, receipt)

    assert errors == []
    assert report["summary"]["total_traps"] == 6
    assert report["summary"]["agreement_rate"] == 1.0
    assert report["integration"]["evidence_scope"] == "technical_host_integration_only"
    assert report["integration"]["biological_claim_status"] == "not_evaluated"


def test_direct_api_or_replay_cannot_pass_as_live_host(tmp_path, monkeypatch):
    request = build_request(REPO_ROOT / "evals" / "datasets" / "l2_agent_claims.yaml")
    audit_path, event = _receipt(tmp_path, monkeypatch)
    run = _run(request, event)
    run["execution_mode"] = "direct_gemini_api"
    run["is_live"] = False

    errors, _receipt_event = validate_live_run(run, request, audit_path)
    assert any("live_mcp" in error for error in errors)


def test_missing_receipt_fails_closed(tmp_path, monkeypatch):
    request = build_request(REPO_ROOT / "evals" / "datasets" / "l2_agent_claims.yaml")
    audit_path, event = _receipt(tmp_path, monkeypatch)
    run = _run(request, event)
    run["receipt_event_hash"] = "sha256:" + "0" * 64

    errors, _receipt_event = validate_live_run(run, request, audit_path)
    assert any("not found" in error for error in errors)


def test_dirty_worktree_receipt_is_not_formal_evidence(tmp_path, monkeypatch):
    request = build_request(REPO_ROOT / "evals" / "datasets" / "l2_agent_claims.yaml")
    audit_path, event = _receipt(tmp_path, monkeypatch, dirty=True)
    run = _run(request, event)

    errors, _receipt_event = validate_live_run(run, request, audit_path)
    assert any("dirty or unverifiable" in error for error in errors)


def test_changed_fixed_input_is_detected(tmp_path, monkeypatch):
    request = build_request(REPO_ROOT / "evals" / "datasets" / "l2_agent_claims.yaml")
    audit_path, event = _receipt(tmp_path, monkeypatch)
    run = _run(request, event)
    run["records"][0]["input_hash"] = "sha256:" + "f" * 64

    errors, _receipt_event = validate_live_run(run, request, audit_path)
    assert any("input_hash" in error for error in errors)


def test_configured_snapshot_requires_independent_local_verification(tmp_path, monkeypatch):
    request = build_request(REPO_ROOT / "evals" / "datasets" / "l2_agent_claims.yaml")
    audit_path, event = _receipt(tmp_path, monkeypatch)
    event["git_dirty_source"] = "configured_snapshot"
    event["event_hash"] = mcp_host_audit._event_hash(event)
    audit_path.write_text(mcp_host_audit.canonical_json(event) + "\n", encoding="utf-8")
    run = _run(request, event)

    monkeypatch.setattr(antigravity_acceptance, "_local_git_state", lambda _root: ("b" * 40, False))
    errors, _receipt_event = validate_live_run(run, request, audit_path)
    assert any("does not match" in error for error in errors)

    monkeypatch.setattr(antigravity_acceptance, "_local_git_state", lambda _root: ("a" * 40, False))
    errors, _receipt_event = validate_live_run(run, request, audit_path)
    assert errors == []
