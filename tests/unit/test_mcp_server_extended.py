"""
Unit tests for extended MCP Server v2.0.0 tools, resources, prompts, and rate limiting.
"""

import pytest
import asyncio
import json
from pathlib import Path
import sys
from unittest.mock import patch

# Ensure scripts dir is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from local_mcp_server import (
    handle_rpc_request_async,
    TokenBucketRateLimiter,
    TOOLS_SCHEMA,
    RESOURCES_SCHEMA,
    PROMPTS_SCHEMA,
    tool_search_gnomad,
    tool_search_pdb,
    tool_search_alphafold,
    tool_search_reactome,
    tool_search_string,
    tool_search_cosmic,
    tool_search_geo,
    tool_get_gene_expression
)


def test_mcp_server_v2_initialize():
    """Verify v2.0.0 initialization returns tools, resources, and prompts capabilities."""
    async def _run():
        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {}
        }
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    res = resp["result"]
    assert res["protocolVersion"] == "2024-11-05"
    assert res["serverInfo"]["version"] == "2.0.0"
    assert "tools" in res["capabilities"]
    assert "resources" in res["capabilities"]
    assert "prompts" in res["capabilities"]


def test_mcp_tools_list_count():
    """Verify all 16 scientific tools are registered."""
    async def _run():
        req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        return await handle_rpc_request_async(req)

    resp = asyncio.run(_run())
    tools = resp["result"]["tools"]
    tool_names = {t["name"] for t in tools}
    expected_unique = {
        "search_uniprot", "search_ensembl", "search_gnomad", "search_pdb",
        "search_alphafold", "search_reactome", "search_string", "search_geo",
        "get_gene_expression",
    }
    assert expected_unique == tool_names
    assert "search_pubmed" not in tool_names
    assert "search_cosmic" not in tool_names


def test_mcp_hosted_fallbacks_opt_in(monkeypatch):
    monkeypatch.setenv("BIONEXUS_LOCAL_HOSTED_FALLBACKS", "1")
    from local_mcp_server import public_tools_schema

    names = {t["name"] for t in public_tools_schema()}
    assert "search_pubmed" in names
    assert "search_cosmic" in names
    assert len(names) == 16


def test_mcp_resources_primitives():
    """Verify resources/list and resources/read."""
    async def _run():
        list_req = {"jsonrpc": "2.0", "id": 3, "method": "resources/list", "params": {}}
        list_resp = await handle_rpc_request_async(list_req)
        resources = list_resp["result"]["resources"]
        assert len(resources) >= 4
        uris = [r["uri"] for r in resources]
        assert "bionexus://workflows/drug_target_discovery" in uris

        read_req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": "bionexus://workflows/drug_target_discovery"}
        }
        read_resp = await handle_rpc_request_async(read_req)
        contents = read_resp["result"]["contents"]
        assert len(contents) == 1
        assert "bionexus://" in contents[0]["uri"]

    asyncio.run(_run())


def test_mcp_prompts_primitives():
    """Verify prompts/list and prompts/get."""
    async def _run():
        list_req = {"jsonrpc": "2.0", "id": 5, "method": "prompts/list", "params": {}}
        list_resp = await handle_rpc_request_async(list_req)
        prompts = list_resp["result"]["prompts"]
        assert len(prompts) >= 4
        p_names = {p["name"] for p in prompts}
        assert "drug_target_analysis" in p_names
        assert "variant_pathogenicity" in p_names
        assert "antibody_developability_audit" in p_names
        assert "survival_biomarker_screening" in p_names

        get_req = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "prompts/get",
            "params": {
                "name": "drug_target_analysis",
                "arguments": {"disease": "Melanoma", "target_gene": "BRAF"}
            }
        }
        get_resp = await handle_rpc_request_async(get_req)
        msgs = get_resp["result"]["messages"]
        assert len(msgs) == 1
        assert "BRAF" in msgs[0]["content"]["text"]
        assert "Melanoma" in msgs[0]["content"]["text"]

    asyncio.run(_run())


def test_token_bucket_rate_limiter():
    """Verify token bucket permits burst and then throttles."""
    async def _run():
        limiter = TokenBucketRateLimiter(rate=100.0, capacity=2.0)
        t0 = asyncio.get_event_loop().time()
        await limiter.acquire()
        await limiter.acquire()
        t1 = asyncio.get_event_loop().time()
        assert (t1 - t0) < 0.1

    asyncio.run(_run())


@patch("local_mcp_server.async_http_request")
def test_tool_search_gnomad_mock(mock_http):
    """Test gnomAD gene constraint tool parsing."""
    async def _run():
        mock_http.return_value = {
            "data": {
                "gene": {
                    "gene_id": "ENSG00000012048",
                    "symbol": "BRCA1",
                    "name": "BRCA1 DNA repair associated",
                    "gnomad_constraint": {
                        "pLI": 0.999,
                        "loeuf": 0.12,
                        "mis_z": 2.45
                    }
                }
            }
        }
        res = await tool_search_gnomad(gene_symbol="BRCA1")
        assert res["symbol"] == "BRCA1"
        assert res["constraint"]["pLI"] == 0.999
        assert res["constraint"]["loeuf"] == 0.12

    asyncio.run(_run())


@patch("local_mcp_server.async_http_request")
def test_tool_search_pdb_mock(mock_http):
    """Test RCSB PDB structure tool."""
    async def _run():
        mock_http.side_effect = [
            {"result_set": [{"identifier": "7K43", "score": 1.0}], "total_count": 1},
            {
                "struct": {"title": "Structure of SARS-CoV-2 Spike"},
                "exptl": [{"method": "ELECTRON MICROSCOPY"}],
                "rcsb_entry_info": {"resolution_combined": [2.6]},
                "rcsb_accession_info": {"initial_release_date": "2020-10-14"}
            }
        ]
        res = await tool_search_pdb(query="Spike", limit=1)
        assert res["total_found"] == 1
        assert len(res["structures"]) == 1
        assert res["structures"][0]["pdb_id"] == "7K43"
        assert res["structures"][0]["resolution_angstrom"] == 2.6

    asyncio.run(_run())


@patch("local_mcp_server.async_http_request")
def test_tool_search_alphafold_mock(mock_http):
    """Test AlphaFold DB prediction lookup."""
    async def _run():
        mock_http.return_value = [{
            "entryId": "AF-P04637-F1",
            "gene": "TP53",
            "organismScientificName": "Homo sapiens",
            "uniprotSequenceLength": 393,
            "globalPlddt": 68.4,
            "pdbUrl": "https://alphafold.ebi.ac.uk/files/AF-P04637-F1-model_v4.pdb"
        }]
        res = await tool_search_alphafold("P04637")
        assert res["uniprot_id"] == "P04637"
        assert res["global_plddt"] == 68.4
        assert "pdb_url" in res

    asyncio.run(_run())
