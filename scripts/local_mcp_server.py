#!/usr/bin/env python3
"""
Local Fallback MCP Server for Bio-Research.
Implements Model Context Protocol (MCP) JSON-RPC over stdio using Python standard library.
Provides direct access to NCBI PubMed, bioRxiv, ChEMBL, OpenTargets, and ClinicalTrials.gov.
"""

import sys
import json
import os
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional

# --- Configuration & Auth Loading ---
def get_api_key(key_name: str) -> Optional[str]:
    """Retrieve API key from environment variable or local .env file."""
    val = os.environ.get(key_name)
    if val:
        return val.strip()
    
    # Try reading from .env in parent directories
    for search_dir in [os.getcwd(), os.path.dirname(os.path.abspath(__file__)), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]:
        env_path = os.path.join(search_dir, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(f"{key_name}="):
                            return line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception:
                pass
    return None


def http_get_json(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 15) -> Any:
    """Helper to perform HTTP GET returning parsed JSON."""
    req_headers = {"User-Agent": "BioResearch-LocalMCP/1.2.0 (OpenScience)"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
        return json.loads(data)


def http_post_json(url: str, json_data: Dict[str, Any], headers: Optional[Dict[str, str]] = None, timeout: int = 15) -> Any:
    """Helper to perform HTTP POST with JSON body."""
    req_headers = {
        "User-Agent": "BioResearch-LocalMCP/1.2.0 (OpenScience)",
        "Content-Type": "application/json"
    }
    if headers:
        req_headers.update(headers)
    body = json.dumps(json_data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=req_headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
        return json.loads(data)


# --- Tool Implementations ---

def tool_search_pubmed(query: str, max_results: int = 5) -> Dict[str, Any]:
    """Search NCBI PubMed for biomedical literature."""
    max_results = min(max(1, int(max_results)), 20)
    api_key = get_api_key("NCBI_API_KEY")
    
    # 1. ESearch
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": str(max_results),
        "sort": "pub_date"
    }
    if api_key:
        params["api_key"] = api_key
    
    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{urllib.parse.urlencode(params)}"
    search_data = http_get_json(search_url)
    id_list = search_data.get("esearchresult", {}).get("idlist", [])
    
    if not id_list:
        return {"query": query, "total_found": 0, "articles": []}
    
    # 2. ESummary
    summary_params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "json"
    }
    if api_key:
        summary_params["api_key"] = api_key
    
    summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{urllib.parse.urlencode(summary_params)}"
    summary_data = http_get_json(summary_url)
    result_dict = summary_data.get("result", {})
    
    articles = []
    for pmid in id_list:
        info = result_dict.get(pmid, {})
        title = info.get("title", "No title")
        authors = [a.get("name", "") for a in info.get("authors", [])]
        source = info.get("source", "")
        pubdate = info.get("pubdate", "")
        doi = next((item.get("value") for item in info.get("articleids", []) if item.get("idtype") == "doi"), None)
        
        articles.append({
            "pmid": pmid,
            "title": title,
            "authors": authors[:5] + (["et al."] if len(authors) > 5 else []),
            "journal": source,
            "pub_date": pubdate,
            "doi": doi,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        })
    
    return {
        "query": query,
        "total_found": search_data.get("esearchresult", {}).get("count", len(articles)),
        "articles": articles
    }


def tool_search_biorxiv(query: str, server: str = "biorxiv", limit: int = 5) -> Dict[str, Any]:
    """Search preprints on bioRxiv or medRxiv."""
    limit = min(max(1, int(limit)), 20)
    server = "medrxiv" if server.lower() == "medrxiv" else "biorxiv"
    
    # Use Europe PMC API filtered for bioRxiv/medRxiv preprints for better keyword search
    epmc_query = f"{query} (SRC:PPR OR PUBLISHER:biorxiv OR PUBLISHER:medrxiv)"
    params = {
        "query": epmc_query,
        "format": "json",
        "pageSize": str(limit),
        "resultType": "lite"
    }
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{urllib.parse.urlencode(params)}"
    data = http_get_json(url)
    
    results = data.get("resultList", {}).get("result", [])
    papers = []
    for r in results:
        papers.append({
            "title": r.get("title", ""),
            "author_string": r.get("authorString", ""),
            "journal_title": r.get("journalTitle", server.upper()),
            "pub_year": r.get("pubYear", ""),
            "doi": r.get("doi", ""),
            "url": f"https://doi.org/{r.get('doi')}" if r.get("doi") else ""
        })
    
    return {
        "query": query,
        "server": server,
        "preprints": papers
    }


def tool_search_chembl(query: str, entity_type: str = "molecule", limit: int = 5) -> Dict[str, Any]:
    """Query ChEMBL database for bioactive molecules or drug targets."""
    limit = min(max(1, int(limit)), 20)
    entity_type = entity_type.lower()
    
    if entity_type == "target":
        url = f"https://www.ebi.ac.uk/chembl/api/data/target/search.json?q={urllib.parse.quote(query)}&limit={limit}"
        data = http_get_json(url)
        targets = []
        for t in data.get("targets", []):
            targets.append({
                "chembl_id": t.get("target_chembl_id"),
                "pref_name": t.get("pref_name"),
                "target_type": t.get("target_type"),
                "organism": t.get("organism")
            })
        return {"query": query, "entity_type": "target", "results": targets}
    else:
        url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/search.json?q={urllib.parse.quote(query)}&limit={limit}"
        data = http_get_json(url)
        molecules = []
        for m in data.get("molecules", []):
            props = m.get("molecule_properties") or {}
            structures = m.get("molecule_structures") or {}
            molecules.append({
                "chembl_id": m.get("molecule_chembl_id"),
                "pref_name": m.get("pref_name"),
                "max_phase": m.get("max_phase"),
                "molecule_type": m.get("molecule_type"),
                "molecular_weight": props.get("full_mwt"),
                "canonical_smiles": structures.get("canonical_smiles")
            })
        return {"query": query, "entity_type": "molecule", "results": molecules}


def tool_search_opentargets(query: str, limit: int = 5) -> Dict[str, Any]:
    """Query Open Targets Platform GraphQL API for disease and target search."""
    limit = min(max(1, int(limit)), 20)
    gql_query = """
    query SearchQuery($queryString: String!, $size: Int!) {
      search(queryString: $queryString, entityNames: ["target", "disease"], page: {size: $size, index: 0}) {
        total
        hits {
          id
          name
          entity
          description
        }
      }
    }
    """
    payload = {
        "query": gql_query,
        "variables": {
            "queryString": query,
            "size": limit
        }
    }
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    data = http_post_json(url, payload)
    hits = data.get("data", {}).get("search", {}).get("hits", [])
    
    return {
        "query": query,
        "total_hits": data.get("data", {}).get("search", {}).get("total", len(hits)),
        "results": hits
    }


def tool_search_clinical_trials(condition: str, intervention: str = "", limit: int = 5) -> Dict[str, Any]:
    """Query ClinicalTrials.gov API v2 for clinical studies."""
    limit = min(max(1, int(limit)), 20)
    params = {
        "query.cond": condition,
        "pageSize": str(limit)
    }
    if intervention:
        params["query.intr"] = intervention
    
    url = f"https://clinicaltrials.gov/api/v2/studies?{urllib.parse.urlencode(params)}"
    data = http_get_json(url)
    studies = []
    for s in data.get("studies", []):
        protocol = s.get("protocolSection", {})
        id_module = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        design_module = protocol.get("designModule", {})
        
        nct_id = id_module.get("nctId")
        brief_title = id_module.get("briefTitle")
        overall_status = status_module.get("overallStatus")
        phases = design_module.get("phases", [])
        
        studies.append({
            "nct_id": nct_id,
            "title": brief_title,
            "status": overall_status,
            "phases": phases,
            "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else ""
        })
    
    return {
        "condition": condition,
        "intervention": intervention,
        "studies": studies
    }


# --- Tool Definitions ---

TOOLS_SCHEMA = [
    {
        "name": "search_pubmed",
        "description": "Search PubMed database for biomedical and life sciences research literature via NCBI E-utilities API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords, gene symbols, disease names, or MeSH terms (e.g. 'KRAS G12D inhibitor', 'scRNA-seq batch effect')."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of articles to return (1-20, default 5).",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_biorxiv",
        "description": "Search recent life sciences preprints on bioRxiv and medRxiv.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query terms or topic keywords."
                },
                "server": {
                    "type": "string",
                    "enum": ["biorxiv", "medrxiv"],
                    "description": "Preprint server name ('biorxiv' or 'medrxiv'). Default is 'biorxiv'.",
                    "default": "biorxiv"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum preprints to return (1-20, default 5).",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_chembl",
        "description": "Query ChEMBL database for bioactive small molecules, compounds, drugs, and protein targets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Compound name, target name, or keyword (e.g. 'Osimertinib', 'EGFR', 'aspirin')."
                },
                "entity_type": {
                    "type": "string",
                    "enum": ["molecule", "target"],
                    "description": "Search for bioactive molecules/compounds or protein targets. Default is 'molecule'.",
                    "default": "molecule"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum entries to return (1-20, default 5).",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_opentargets",
        "description": "Search Open Targets Platform for disease-target associations, therapeutic targets, and disease ontology entries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Gene symbol or disease name (e.g. 'BRCA1', 'Non-small cell lung cancer')."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum hits to return (1-20, default 5).",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_clinical_trials",
        "description": "Query ClinicalTrials.gov API for registered clinical studies, trial phases, and recruitment statuses.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "condition": {
                    "type": "string",
                    "description": "Condition or disease being studied (e.g. 'Melanoma', 'Type 2 Diabetes')."
                },
                "intervention": {
                    "type": "string",
                    "description": "Optional drug or therapy intervention (e.g. 'Pembrolizumab').",
                    "default": ""
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum trials to return (1-20, default 5).",
                    "default": 5
                }
            },
            "required": ["condition"]
        }
    }
]


# --- Stdio JSON-RPC Server Loop ---

def handle_rpc_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Dispatch incoming JSON-RPC request and return response."""
    msg_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})
    
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "bio-research-local-mcp",
                    "version": "1.2.0"
                }
            }
        }
    elif method == "notifications/initialized" or method == "initialized":
        return None  # No response needed for notifications
    elif method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {}
        }
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": TOOLS_SCHEMA
            }
        }
    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        try:
            if tool_name == "search_pubmed":
                res = tool_search_pubmed(args.get("query", ""), args.get("max_results", 5))
            elif tool_name == "search_biorxiv":
                res = tool_search_biorxiv(args.get("query", ""), args.get("server", "biorxiv"), args.get("limit", 5))
            elif tool_name == "search_chembl":
                res = tool_search_chembl(args.get("query", ""), args.get("entity_type", "molecule"), args.get("limit", 5))
            elif tool_name == "search_opentargets":
                res = tool_search_opentargets(args.get("query", ""), args.get("limit", 5))
            elif tool_name == "search_clinical_trials":
                res = tool_search_clinical_trials(args.get("condition", ""), args.get("intervention", ""), args.get("limit", 5))
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown tool: {tool_name}"
                    }
                }
            
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(res, indent=2, ensure_ascii=False)
                        }
                    ]
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "isError": True,
                    "content": [
                        {
                            "type": "text",
                            "text": f"Error executing tool {tool_name}: {str(e)}"
                        }
                    ]
                }
            }
    else:
        if msg_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
        return None


def main():
    """Main stdio loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = handle_rpc_request(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {str(e)}"
                }
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
