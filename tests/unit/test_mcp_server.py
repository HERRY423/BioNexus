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

from local_mcp_server import create_mcp_server, handle_rpc_request_async


def test_official_fastmcp_server_sdk(monkeypatch):
    """Verify official MCP Python SDK FastMCP server instance and tool registration."""
    import pytest

    monkeypatch.delenv("BIONEXUS_LOCAL_HOSTED_FALLBACKS", raising=False)
    try:
        server = create_mcp_server()
    except (ImportError, ModuleNotFoundError):
        pytest.skip("Official MCP Python SDK (`mcp`) not installed in test environment.")

    assert server is not None
    assert server.name == "bionexus-local-mcp"
    tools = server._tool_manager.list_tools()
    assert len(tools) == 9
    tool_names = {t.name for t in tools}
    assert "search_uniprot" in tool_names
    assert "search_ensembl" in tool_names
    assert "search_gnomad" in tool_names
    assert "search_pdb" in tool_names
    assert "search_alphafold" in tool_names
    assert "search_reactome" in tool_names
    assert "search_string" in tool_names
    assert "search_geo" in tool_names
    assert "get_gene_expression" in tool_names
    assert "search_pubmed" not in tool_names
    assert "search_chembl" not in tool_names

    # Opt-in for hosted fallbacks
    monkeypatch.setenv("BIONEXUS_LOCAL_HOSTED_FALLBACKS", "1")
    server_with_fallbacks = create_mcp_server()
    tools_all = server_with_fallbacks._tool_manager.list_tools()
    assert len(tools_all) == 16
    tool_names_all = {t.name for t in tools_all}
    assert "search_pubmed" in tool_names_all
    assert "search_chembl" in tool_names_all


def test_mcp_server_discover_modern():
    """Verify modern stateless server/discover protocol response."""

    async def _run():
        req = {"jsonrpc": "2.0", "id": "discover-1", "method": "server/discover", "params": {}}
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "discover-1"
    res = resp["result"]
    assert res["serverInfo"]["sdk"] == "official-mcp-python-sdk"
    assert "tools" in res
    assert "resources" in res
    assert "prompts" in res


def test_mcp_initialize():
    """Verify standard legacy initialize handshake response for backward compatibility."""

    async def _run():
        req = {"jsonrpc": "2.0", "id": "test-init-1", "method": "initialize", "params": {}}
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "test-init-1"
    assert "result" in resp
    result = resp["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == "bionexus-local-mcp"
    assert result["serverInfo"]["version"] == "2.0.0"


def test_mcp_ping():
    """Verify ping response."""

    async def _run():
        req = {"jsonrpc": "2.0", "id": 42, "method": "ping", "params": {}}
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp == {"jsonrpc": "2.0", "id": 42, "result": {}}


def test_mcp_tools_list():
    """Verify tools/list exposes all required scientific tools."""

    async def _run():
        req = {"jsonrpc": "2.0", "id": "list-tools-1", "method": "tools/list", "params": {}}
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
        req = {"jsonrpc": "2.0", "id": "bad-method-1", "method": "non_existent_method", "params": {}}
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
            "params": {"name": "super_secret_unsupported_tool", "arguments": {}},
        }
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp is not None
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_mcp_notification_no_response():
    """Verify that JSON-RPC notifications (no id) return None without writing response."""

    async def _run():
        req = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp is None


def test_mcp_tools_call_readonly():
    """Verify read-only tools/call via JSON-RPC returns structured result."""
    from unittest.mock import patch

    async def _run():
        with patch("local_mcp_server.async_http_request") as mock_http:
            mock_http.return_value = [
                {
                    "entryId": "AF-P04637-F1",
                    "gene": "TP53",
                    "organismScientificName": "Homo sapiens",
                    "uniprotSequenceLength": 393,
                    "globalPlddt": 68.4,
                    "pdbUrl": "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-model_v4.pdb",
                }
            ]
            req = {
                "jsonrpc": "2.0",
                "id": "call-1",
                "method": "tools/call",
                "params": {"name": "search_alphafold", "arguments": {"uniprot_id": "P04637"}},
            }
            return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp is not None
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == "call-1"
    assert "result" in resp
    assert not resp["result"].get("isError")
    content = resp["result"]["content"]
    assert len(content) >= 1
    assert "P04637" in content[0]["text"]
