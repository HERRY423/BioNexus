"""
Unit tests for the bionexus_warrant_check MCP tool (Biomni / full-privilege host gate).
"""

import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from local_mcp_server import TOOLS_SCHEMA, handle_rpc_request_async, tool_bionexus_warrant_check


def _run_warrant_check(**kwargs):
    return asyncio.run(tool_bionexus_warrant_check(**kwargs))


def test_warrant_tool_registered_as_local_unique():
    by_name = {t["name"]: t for t in TOOLS_SCHEMA}
    tool = by_name["bionexus_warrant_check"]
    assert tool["annotations"]["bionexus_role"] == "local_unique"
    assert tool["inputSchema"]["required"] == ["query"]


def test_warrant_check_returns_structured_verdict():
    res = _run_warrant_check(
        query="Run differential expression between condition A and condition B on single-cell data",
        data_metadata={"donors_per_condition": 1, "conditions": 2},
    )
    for key in (
        "status",
        "rationale",
        "evidence_ceiling",
        "host_integration",
        "boundary",
    ):
        assert key in res, f"missing warrant payload key: {key}"
    assert res["status"] in {
        "PERMITTED",
        "PERMITTED_WITH_LIMITS",
        "NEEDS_DATA",
        "ABSTAIN",
        "DEGRADED_ADVISORY",
        "EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN",
    }
    assert "biomni" in res["host_integration"]["intended_hosts"]
    assert "not clinical validation" in res["boundary"]


def test_warrant_check_blocks_overclaim_with_confounded_design():
    """n=1 donor per condition must never yield an unrestricted population-effect permit."""
    res = _run_warrant_check(
        query="Identify population-wide treatment effect genes from single-cell differential expression",
        data_metadata={"donors_per_condition": 1, "conditions": 2},
        research_purpose="confirmatory",
    )
    assert res["status"] != "PERMITTED", "overclaiming design must not be permitted outright"
    surfaced = any(
        res.get(key)
        for key in ("missing_data_requests", "remedies", "violations", "blocked_claims")
    )
    assert surfaced, "fail-closed verdict must state what is missing or blocked"


def test_warrant_check_unresolvable_intent_fails_closed():
    res = _run_warrant_check(query="hello what can you do")
    assert res["status"] == "NEEDS_DATA"
    assert res.get("matched_capability_id") is None
    assert res.get("missing_data_requests")


def test_warrant_check_via_jsonrpc_tools_call():
    req = {
        "jsonrpc": "2.0",
        "id": 42,
        "method": "tools/call",
        "params": {
            "name": "bionexus_warrant_check",
            "arguments": {"query": "Cluster my single-cell dataset and find marker genes"},
        },
    }
    resp = asyncio.run(handle_rpc_request_async(req))
    assert resp["id"] == 42
    content = resp["result"]["content"][0]["text"]
    assert '"status"' in content
