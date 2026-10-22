"""
Local Fallback MCP Server for BioNexus.

Compatibility Facade:
Implementation has been modularized into `bionexus.mcp`:
- `bionexus.mcp.client`: Rate limiting and HTTP request logic
- `bionexus.mcp.tools`: Modular tool implementations (literature, targets, omics, governance)
- `bionexus.mcp.schemas`: Tools, resources, and prompt schemas
- `bionexus.mcp.server`: FastMCP server runtime, stdio duplex RPC loop, and main()

All public symbols and module attributes are re-exported here for 100% backward compatibility.
"""

from bionexus.mcp import (
    _DEFAULT_HIDDEN_LOCAL_TOOLS,
    _HOSTED_FALLBACK_TOOLS,
    _LOCAL_CGC_HINTS,
    LOG_FILE,
    PROMPTS_SCHEMA,
    RESOURCES_SCHEMA,
    SERVER_VERSION,
    TOOL_ADAPTER_MAP,
    TOOLS_SCHEMA,
    TokenBucketRateLimiter,
    _annotate_local_mcp_roles,
    _capability_evidence_ceiling,
    _get_limiter_for_url,
    async_http_request,
    async_stdio_reader,
    configure_runtime_from_argv,
    create_mcp_server,
    get_api_key,
    get_prompt_content,
    get_resource_content,
    handle_rpc_request_async,
    logger,
    main,
    process_single_rpc,
    public_tools_schema,
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
    write_json_response,
)

__all__ = [
    "LOG_FILE",
    "PROMPTS_SCHEMA",
    "RESOURCES_SCHEMA",
    "SERVER_VERSION",
    "TOOLS_SCHEMA",
    "TOOL_ADAPTER_MAP",
    "TokenBucketRateLimiter",
    "_DEFAULT_HIDDEN_LOCAL_TOOLS",
    "_HOSTED_FALLBACK_TOOLS",
    "_LOCAL_CGC_HINTS",
    "_annotate_local_mcp_roles",
    "_capability_evidence_ceiling",
    "_get_limiter_for_url",
    "async_http_request",
    "async_stdio_reader",
    "configure_runtime_from_argv",
    "create_mcp_server",
    "get_api_key",
    "get_prompt_content",
    "get_resource_content",
    "handle_rpc_request_async",
    "logger",
    "main",
    "process_single_rpc",
    "public_tools_schema",
    "tool_bionexus_host_probe",
    "tool_bionexus_warrant_check",
    "tool_get_gene_expression",
    "tool_get_pubmed_article",
    "tool_search_alphafold",
    "tool_search_biorxiv",
    "tool_search_chembl",
    "tool_search_clinical_trials",
    "tool_search_cosmic",
    "tool_search_ensembl",
    "tool_search_geo",
    "tool_search_gnomad",
    "tool_search_opentargets",
    "tool_search_pdb",
    "tool_search_pubmed",
    "tool_search_reactome",
    "tool_search_string",
    "tool_search_uniprot",
    "write_json_response",
]

if __name__ == "__main__":
    main()
