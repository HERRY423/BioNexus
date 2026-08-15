"""
Unit tests for Asynchronous Model Context Protocol (MCP) Server.
Validates JSON-RPC 2.0 protocol handling, tool registry, and dispatch mechanisms.
Uses native asyncio.run() for universal compatibility without requiring external test plugins.
"""

import asyncio
import sys
from pathlib import Path

# Ensure scripts dir is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from local_mcp_server import handle_rpc_request_async


def test_mcp_initialize():
    """Verify standard initialize handshake response."""
    async def _run():
        req = {
            "jsonrpc": "2.0",
            "id": "test-init-1",
            "method": "initialize",
            "params": {}
        }
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "test-init-1"
    assert "result" in resp
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "bio-research-local-mcp"
    assert result["serverInfo"]["version"] == "2.0.0"


def test_mcp_ping():
    """Verify ping response."""
    async def _run():
        req = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "ping",
            "params": {}
        }
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp == {"jsonrpc": "2.0", "id": 42, "result": {}}


def test_mcp_tools_list():
    """Verify tools/list exposes all required scientific tools."""
    async def _run():
        req = {
            "jsonrpc": "2.0",
            "id": "list-tools-1",
            "method": "tools/list",
            "params": {}
        }
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp is not None
    assert "result" in resp
    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]

    expected_tools = [
        "search_uniprot",
        "search_ensembl",
        "search_gnomad",
        "search_pdb",
    ]
    for expected in expected_tools:
        assert expected in tool_names, f"Missing tool: {expected}"


def test_mcp_unknown_method():
    """Verify proper error response for non-existent methods."""
    async def _run():
        req = {
            "jsonrpc": "2.0",
            "id": "bad-method-1",
            "method": "non_existent_method",
            "params": {}
        }
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp is not None
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_mcp_unknown_tool():
    """Verify error response for unknown tool calls."""
    async def _run():
        req = {
            "jsonrpc": "2.0",
            "id": "bad-tool-1",
            "method": "tools/call",
            "params": {
                "name": "super_secret_unsupported_tool",
                "arguments": {}
            }
        }
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp is not None
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_mcp_notification_no_response():
    """Verify that JSON-RPC notifications (no id) return None without writing response."""
    async def _run():
        req = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp is None
