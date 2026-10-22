"""
FastMCP Server, JSON-RPC stdio transport, and CLI runtime for BioNexus MCP.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from bionexus.mcp.schemas import (
    PROMPTS_SCHEMA,
    RESOURCES_SCHEMA,
    get_prompt_content,
    get_resource_content,
    public_tools_schema,
)
from bionexus.mcp.tools import (
    tool_bionexus_host_probe,
    tool_bionexus_warrant_check,
    tool_get_gene_expression,
    tool_get_pubmed_article,
    tool_search_alphafold,
    tool_search_biorxiv,
    tool_search_chembl,
    tool_search_clinical_trials,
    tool_search_cosmic,
    tool_search_ensembl,
    tool_search_geo,
    tool_search_gnomad,
    tool_search_opentargets,
    tool_search_pdb,
    tool_search_pubmed,
    tool_search_reactome,
    tool_search_string,
    tool_search_uniprot,
)

LOG_FILE = os.environ.get(
    "BIONEXUS_MCP_LOG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_mcp_server.log")
)
logger = logging.getLogger("bionexus.mcp.server")
SERVER_VERSION = "2.1.0"

FastMCP: Any = None
try:
    FastMCP = getattr(importlib.import_module("mcp.server"), "MCPServer", None)
    if FastMCP is None:
        FastMCP = importlib.import_module("mcp.server.fastmcp").FastMCP
except ImportError:
    pass

def create_mcp_server() -> Any:
    """Create and configure the official FastMCP Server for BioNexus."""
    if FastMCP is None:
        raise ImportError(
            "Official MCP Python SDK (`mcp`) is not installed or exposes an unsupported server API. "
            "Install a compatible release via `pip install mcp`."
        )

    mcp = FastMCP("bionexus-local-mcp")

    @mcp.tool(
        name="search_uniprot",
        description="Search UniProtKB for protein metadata, sequences, and functional annotations.",
    )
    async def search_uniprot(query: str, organism: str = "human", limit: int = 5) -> str:
        res = await tool_search_uniprot(query=query, organism=organism, limit=limit)
        return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="search_ensembl",
        description="Search Ensembl REST API for gene symbols, stable IDs, genomic coordinates, and transcripts.",
    )
    async def search_ensembl(symbol: str, species: str = "human") -> str:
        res = await tool_search_ensembl(symbol=symbol, species=species)
        return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="search_gnomad",
        description="Search gnomAD GraphQL API for gene constraint metrics (pLI, LOEUF) and variant population frequencies.",
    )
    async def search_gnomad(gene_symbol: Optional[str] = None, variant_id: Optional[str] = None) -> str:
        res = await tool_search_gnomad(gene_symbol=gene_symbol, variant_id=variant_id)
        return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="search_pdb",
        description="Search RCSB Protein Data Bank (PDB) for 3D macromolecular experimental structures.",
    )
    async def search_pdb(query: str, limit: int = 5) -> str:
        res = await tool_search_pdb(query=query, limit=limit)
        return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="search_alphafold",
        description="Search AlphaFold DB for AI-predicted 3D protein structures, global pLDDT confidence, and PDB download URLs.",
    )
    async def search_alphafold(uniprot_id: str) -> str:
        res = await tool_search_alphafold(uniprot_id=uniprot_id)
        return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="search_reactome",
        description="Search Reactome Pathway Knowledgebase for biological pathways and reaction networks.",
    )
    async def search_reactome(query: str, species: str = "Homo sapiens", limit: int = 5) -> str:
        res = await tool_search_reactome(query=query, species=species, limit=limit)
        return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="search_string",
        description="Search STRING database for functional and physical protein-protein interaction networks.",
    )
    async def search_string(gene_symbol: str, species: int = 9606, limit: int = 10, required_score: int = 400) -> str:
        res = await tool_search_string(
            gene_symbol=gene_symbol, species=species, limit=limit, required_score=required_score
        )
        return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="search_geo",
        description="Search NCBI Gene Expression Omnibus (GEO) for functional genomics datasets, expression microarrays, and RNA-seq studies.",
    )
    async def search_geo(query: str, max_results: int = 5) -> str:
        res = await tool_search_geo(query=query, max_results=max_results)
        return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="get_gene_expression",
        description="Query GTEx Portal for median RNA gene expression across 54 human non-diseased tissue sites.",
    )
    async def get_gene_expression(gene_symbol: str, tissue_site: Optional[str] = None) -> str:
        res = await tool_get_gene_expression(gene_symbol=gene_symbol, tissue_site=tissue_site)
        return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="bionexus_warrant_check",
        description=(
            "Pre-execution scientific warrant gate: evaluate an analysis intent against BioNexus "
            "invariants and evidence rules BEFORE running AI-generated code. Returns the routing "
            "verdict, blocked claims, remedies, and evidence ceiling. Not clinical validation."
        ),
    )
    async def bionexus_warrant_check(
        query: str,
        data_metadata: Optional[Dict[str, Any]] = None,
        research_purpose: Optional[str] = None,
        lab_policy: Optional[str] = None,
        intent_keywords: Optional[List[str]] = None,
    ) -> str:
        res = await tool_bionexus_warrant_check(
            query=query,
            data_metadata=data_metadata,
            research_purpose=research_purpose,
            lab_policy=lab_policy,
            intent_keywords=intent_keywords,
        )
        return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.tool(
        name="bionexus_host_probe",
        description=(
            "Record a server-side, tamper-evident receipt proving that this host reached the local BioNexus MCP. "
            "Integration evidence only; not biological or clinical validation."
        ),
    )
    async def bionexus_host_probe(
        host_name: str,
        host_version: str,
        model: str,
        session_id: str,
        challenge: str,
        human_approved: bool,
    ) -> str:
        res = await tool_bionexus_host_probe(
            host_name=host_name,
            host_version=host_version,
            model=model,
            session_id=session_id,
            challenge=challenge,
            human_approved=human_approved,
        )
        # Keep the success payload compact for older GUI MCP clients. The
        # tamper-evident audit log remains the authoritative full receipt.
        return json.dumps(res, separators=(",", ":"), ensure_ascii=False)

    flag = os.environ.get("BIONEXUS_LOCAL_HOSTED_FALLBACKS", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        @mcp.tool(
            name="search_pubmed",
            description="[local fallback — prefer hosted MCP if connected] Search NCBI PubMed for biomedical literature with pagination and date filters.",
        )
        async def search_pubmed(
            query: str,
            max_results: int = 5,
            offset: int = 0,
            sort: str = "pub_date",
            mindate: Optional[str] = None,
            maxdate: Optional[str] = None,
        ) -> str:
            res = await tool_search_pubmed(
                query=query, max_results=max_results, offset=offset, sort=sort, mindate=mindate, maxdate=maxdate
            )
            return json.dumps(res, indent=2, ensure_ascii=False)

        @mcp.tool(
            name="get_pubmed_article",
            description="[local fallback — prefer hosted MCP if connected] Retrieve full metadata, abstract, and DOI/PMC links for a specific PubMed PMID.",
        )
        async def get_pubmed_article(pmid: str) -> str:
            res = await tool_get_pubmed_article(pmid=pmid)
            return json.dumps(res, indent=2, ensure_ascii=False)

        @mcp.tool(name="search_biorxiv", description="[local fallback — prefer hosted MCP if connected] Search Europe PMC for bioRxiv and medRxiv life science preprints.")
        async def search_biorxiv(query: str, server: str = "biorxiv", limit: int = 5, page: int = 1) -> str:
            res = await tool_search_biorxiv(query=query, server=server, limit=limit, page=page)
            return json.dumps(res, indent=2, ensure_ascii=False)

        @mcp.tool(
            name="search_chembl",
            description="[local fallback — prefer hosted MCP if connected] Query ChEMBL database for bioactive molecules, drug targets, or bioactivity assays.",
        )
        async def search_chembl(query: str, entity_type: str = "molecule", limit: int = 5, offset: int = 0) -> str:
            res = await tool_search_chembl(query=query, entity_type=entity_type, limit=limit, offset=offset)
            return json.dumps(res, indent=2, ensure_ascii=False)

        @mcp.tool(
            name="search_opentargets",
            description="[local fallback — prefer hosted MCP if connected] Search Open Targets Platform GraphQL API for disease targets, evidence, and drug associations.",
        )
        async def search_opentargets(
            query: str, entity_types: Optional[List[str]] = None, limit: int = 5, page_index: int = 0
        ) -> str:
            res = await tool_search_opentargets(query=query, entity_types=entity_types, limit=limit, page_index=page_index)
            return json.dumps(res, indent=2, ensure_ascii=False)

        @mcp.tool(
            name="search_clinical_trials",
            description="[local fallback — prefer hosted MCP if connected] Search ClinicalTrials.gov API v2 for active and completed interventional/observational clinical studies.",
        )
        async def search_clinical_trials(
            condition: str = "",
            intervention: str = "",
            status: Optional[str] = None,
            limit: int = 5,
            page_token: Optional[str] = None,
        ) -> str:
            res = await tool_search_clinical_trials(
                condition=condition, intervention=intervention, status=status, limit=limit, page_token=page_token
            )
            return json.dumps(res, indent=2, ensure_ascii=False)

        @mcp.tool(
            name="search_cosmic",
            description="Search local CGC gene hint and Ensembl cross-reference (Research-use only; not the official COSMIC API).",
        )
        async def search_cosmic(gene_symbol: str) -> str:
            res = await tool_search_cosmic(gene_symbol=gene_symbol)
            return json.dumps(res, indent=2, ensure_ascii=False)

    @mcp.resource("bionexus://workflows/drug_target_discovery")
    def res_drug_target_discovery() -> str:
        return get_resource_content("bionexus://workflows/drug_target_discovery")

    @mcp.resource("bionexus://workflows/single_cell_atlas")
    def res_single_cell_atlas() -> str:
        return get_resource_content("bionexus://workflows/single_cell_atlas")

    @mcp.resource("bionexus://workflows/variant_interpretation")
    def res_variant_interpretation() -> str:
        return get_resource_content("bionexus://workflows/variant_interpretation")

    @mcp.resource("bionexus://configs/acmg_rules")
    def res_acmg_rules() -> str:
        return get_resource_content("bionexus://configs/acmg_rules")

    @mcp.resource("bionexus://configs/germline_vgenes")
    def res_germline_vgenes() -> str:
        return get_resource_content("bionexus://configs/germline_vgenes")

    @mcp.resource("bionexus://configs/docking_params")
    def res_docking_params() -> str:
        return get_resource_content("bionexus://configs/docking_params")

    @mcp.prompt("drug_target_analysis")
    def prompt_drug_target_analysis(target_gene: str = "Unknown Target", disease: str = "Unknown Disease") -> str:
        return get_prompt_content("drug_target_analysis", {"target_gene": target_gene, "disease": disease})

    @mcp.prompt("variant_pathogenicity")
    def prompt_variant_pathogenicity(variant: str = "Unknown Variant", disease: str = "Unknown Condition") -> str:
        return get_prompt_content("variant_pathogenicity", {"variant": variant, "disease": disease})

    @mcp.prompt("antibody_developability_audit")
    def prompt_antibody_developability_audit(antibody_name: str = "Unknown Antibody", sequence: str = "") -> str:
        return get_prompt_content(
            "antibody_developability_audit", {"antibody_name": antibody_name, "sequence": sequence}
        )

    @mcp.prompt("survival_biomarker_screening")
    def prompt_survival_biomarker_screening(
        biomarker_gene: str = "Unknown Gene", cancer_cohort: str = "Unknown Cohort"
    ) -> str:
        return get_prompt_content(
            "survival_biomarker_screening", {"biomarker_gene": biomarker_gene, "cancer_cohort": cancer_cohort}
        )

    @mcp.prompt("spatial_niche_discovery")
    def prompt_spatial_niche_discovery(tissue_type: str = "Unknown Tissue") -> str:
        return get_prompt_content("spatial_niche_discovery", {"tissue_type": tissue_type})

    @mcp.prompt("single_cell_integration")
    def prompt_single_cell_integration(dataset_summary: str = "Unknown Summary") -> str:
        return get_prompt_content("single_cell_integration", {"dataset_summary": dataset_summary})

    # Use the same raw-JSON boundary as legacy stdio. FastMCP's default
    # argument conversion can coerce strings/numbers to evidence booleans.
    from bionexus.mcp.transport import call_tool, runtime_identity

    types = importlib.import_module('mcp.types')
    runtime_identity()

    @mcp._mcp_server.list_tools()
    async def strict_tools() -> list[Any]:
        return [types.Tool(**item) for item in public_tools_schema()]

    @mcp._mcp_server.call_tool(validate_input=False)
    async def strict_call(name: str, arguments: dict[str, Any]) -> Any:
        return types.CallToolResult(**await call_tool(name, arguments))

    return mcp


# --- Compatibility Layer: Protocol Handshake & Dispatcher ---


async def handle_rpc_request_async(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Dispatch incoming JSON-RPC request asynchronously.
    Supports modern discovery and legacy MCP JSON-RPC 2.0 handshake for backwards compatibility.
    """
    if (not isinstance(req, dict) or req.get('jsonrpc') != '2.0'
            or not isinstance(req.get('method'), str)
            or not isinstance(req.get('params', {}), dict)
            or ('id' in req and (isinstance(req['id'], bool) or not isinstance(req['id'], (str, int, type(None)))))):
        return {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid Request'}}
    msg_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    logger.debug(f"Handling method: {method}, id: {msg_id}")
    if 'id' not in req:
        return None  # Notifications cannot execute tools or emit responses.

    if method == "initialize":
        # Backward-compatibility handshake for legacy clients
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {},
                },
                "serverInfo": {
                    "name": "bionexus-local-mcp",
                    "version": SERVER_VERSION,
                },
            },
        }
    elif method in ("notifications/initialized", "initialized"):
        return None
    elif method in ("server/discover", "discover"):
        # Modern stateless discovery primitive
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "serverInfo": {
                    "name": "bionexus-local-mcp",
                    "version": SERVER_VERSION,
                    "sdk": "official-mcp-python-sdk",
                },
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
                "tools": public_tools_schema(),
                "resources": RESOURCES_SCHEMA,
                "prompts": PROMPTS_SCHEMA,
            },
        }
    elif method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {},
        }
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": public_tools_schema(),
            },
        }
    elif method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "resources": RESOURCES_SCHEMA,
            },
        }
    elif method == "resources/read":
        uri = params.get("uri", "")
        content = get_resource_content(uri)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "text/yaml",
                        "text": content,
                    }
                ],
            },
        }
    elif method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "prompts": PROMPTS_SCHEMA,
            },
        }
    elif method == "prompts/get":
        prompt_name = params.get("name", "")
        p_args = params.get("arguments", {})
        prompt_text = get_prompt_content(prompt_name, p_args)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "description": f"Prompt template for {prompt_name}",
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": prompt_text,
                        },
                    }
                ],
            },
        }
    elif method == "tools/call":
        from bionexus.mcp.transport import call_tool
        tool_name = params.get("name")
        args = params.get("arguments", {})
        if not isinstance(tool_name, str):
            return {'jsonrpc': '2.0', 'id': msg_id, 'error': {'code': -32602, 'message': 'Invalid tool name'}}
        return {'jsonrpc': '2.0', 'id': msg_id, 'result': await call_tool(tool_name, args)}
    else:
        if msg_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }
        return None


# --- Async Stdio Main Loop & Entry Point ---


def configure_runtime_from_argv(argv: Optional[List[str]] = None) -> None:
    """Bind explicit host-launch options without weakening fail-closed defaults."""
    args = list(sys.argv[1:] if argv is None else argv)
    option = "--audit-log"
    if option not in args:
        return

    index = args.index(option)
    if index + 1 >= len(args) or not args[index + 1].strip() or args[index + 1].startswith("-"):
        raise ValueError("--audit-log requires an explicit non-empty path")
    if option in args[index + 2 :]:
        raise ValueError("--audit-log may be specified only once")

    configured_path = args[index + 1].strip()
    environment_path = os.environ.get("BIONEXUS_MCP_AUDIT_LOG", "").strip()
    if environment_path and Path(environment_path) != Path(configured_path):
        raise ValueError("conflicting MCP audit log paths in environment and command line")
    os.environ["BIONEXUS_MCP_AUDIT_LOG"] = configured_path


async def async_stdio_reader() -> None:
    """Asynchronous stdin reader supporting standard input lines."""
    loop = asyncio.get_running_loop()

    from bionexus.mcp.transport import runtime_identity
    runtime_identity()
    pending: set[asyncio.Task] = set()
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
            task = asyncio.create_task(process_single_rpc(req))
            pending.add(task)
            task.add_done_callback(pending.discard)
        except Exception as e:
            logger.error(f"JSON-RPC parse error: {e}")
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {str(e)}",
                },
            }
            write_json_response(err_resp)
    if pending:
        await asyncio.gather(*pending)


def write_json_response(resp: Dict[str, Any]) -> None:
    """Safely serialize and write JSON response to standard output."""
    output = json.dumps(resp, ensure_ascii=False, allow_nan=False) + "\n"
    sys.stdout.write(output)
    sys.stdout.flush()


async def process_single_rpc(req: Dict[str, Any]) -> None:
    """Process a single JSON-RPC request and emit the response."""
    try:
        resp = await handle_rpc_request_async(req)
        if resp is not None:
            write_json_response(resp)
    except Exception as e:
        logger.error(f"Unexpected error processing RPC request: {e}")
        if isinstance(req, dict) and "id" in req:
            write_json_response(
                {
                    "jsonrpc": "2.0",
                    "id": req.get("id"),
                    "error": {
                        "code": -32603,
                        "message": f"Internal RPC error: {str(e)}",
                    },
                }
            )


def main() -> None:
    """Main process entry point."""
    configure_runtime_from_argv()
    logger.info("BioNexus Local MCP Server starting...")
    if "--legacy" in sys.argv or os.environ.get("BIONEXUS_MCP_LEGACY_MODE") == "1" or FastMCP is None:
        try:
            asyncio.run(async_stdio_reader())
        except (KeyboardInterrupt, SystemExit):
            logger.info("Server shutting down.")
        except Exception as e:
            logger.critical(f"Fatal server crash: {e}", exc_info=True)
            raise SystemExit(1) from e
    else:
        try:
            server = create_mcp_server()
            server.run(transport="stdio")
        except Exception as e:
            # A failed/partially initialized SDK session must not silently switch
            # protocol implementations. Legacy mode requires an explicit launch.
            logger.critical('Official MCP stdio transport failed', exc_info=True)
            raise SystemExit(1) from e


if __name__ == "__main__":
    main()

