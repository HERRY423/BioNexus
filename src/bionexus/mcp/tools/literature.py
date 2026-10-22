from __future__ import annotations

import asyncio
import logging
import urllib.parse
import urllib.request
from typing import Any, Awaitable, Callable, Dict, Optional

from bionexus.egress_guard import guarded_urlopen
from bionexus.mcp.client import get_api_key

logger = logging.getLogger("bionexus.mcp.tools")

def _get_http() -> Callable[..., Awaitable[Any]]:
    import bionexus.mcp_server as _srv
    return _srv.async_http_request

async def tool_search_pubmed(
    query: str,
    max_results: int = 5,
    offset: int = 0,
    sort: str = "pub_date",
    mindate: Optional[str] = None,
    maxdate: Optional[str] = None,
) -> Dict[str, Any]:
    """Search NCBI PubMed for biomedical literature with pagination and date filters."""
    max_results = min(max(1, int(max_results)), 50)
    offset = max(0, int(offset))
    api_key = get_api_key("NCBI_API_KEY")

    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retstart": str(offset),
        "retmax": str(max_results),
        "sort": sort,
    }
    if mindate:
        params["mindate"] = mindate
        params["datetype"] = "pdat"
    if maxdate:
        params["maxdate"] = maxdate
        params["datetype"] = "pdat"
    if api_key:
        params["api_key"] = api_key

    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{urllib.parse.urlencode(params)}"
    search_data = await _get_http()(search_url)
    esearch = search_data.get("esearchresult", {})
    id_list = esearch.get("idlist", [])
    total_found = int(esearch.get("count", 0))

    if not id_list:
        return {"query": query, "total_found": total_found, "offset": offset, "limit": max_results, "articles": []}

    summary_params = {"db": "pubmed", "id": ",".join(id_list), "retmode": "json"}
    if api_key:
        summary_params["api_key"] = api_key

    summary_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{urllib.parse.urlencode(summary_params)}"
    )
    summary_data = await _get_http()(summary_url)
    result_dict = summary_data.get("result", {})

    articles = []
    for pmid in id_list:
        info = result_dict.get(pmid, {})
        title = info.get("title", "No title")
        authors = [a.get("name", "") for a in info.get("authors", [])]
        source = info.get("source", "")
        pubdate = info.get("pubdate", "")
        doi = next((item.get("value") for item in info.get("articleids", []) if item.get("idtype") == "doi"), None)

        articles.append(
            {
                "pmid": pmid,
                "title": title,
                "authors": authors[:5] + (["et al."] if len(authors) > 5 else []),
                "journal": source,
                "pub_date": pubdate,
                "doi": doi,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            }
        )

    return {
        "query": query,
        "total_found": total_found,
        "offset": offset,
        "limit": max_results,
        "returned": len(articles),
        "articles": articles,
    }


async def tool_get_pubmed_article(pmid: str) -> Dict[str, Any]:
    """Retrieve full abstract, MeSH terms, and citation metadata for a specific PubMed PMID."""
    pmid = str(pmid).strip()
    api_key = get_api_key("NCBI_API_KEY")

    params = {"db": "pubmed", "id": pmid, "retmode": "json"}
    if api_key:
        params["api_key"] = api_key

    summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{urllib.parse.urlencode(params)}"
    summary_data = await _get_http()(summary_url)
    info = summary_data.get("result", {}).get(pmid, {})

    abstract_text = ""
    abstract_status = "NOT_FETCHED"
    abstract_error = None
    mesh_terms = []
    try:
        fetch_params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
        if api_key:
            fetch_params["api_key"] = api_key
        fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{urllib.parse.urlencode(fetch_params)}"

        def _fetch_xml() -> bytes:
            req = urllib.request.Request(fetch_url, headers={"User-Agent": "BioNexus-LocalMCP/2.0.0"})
            with guarded_urlopen(
                req,
                timeout=15,
                purpose="Local MCP endpoint availability probe",
            ) as resp:
                return resp.read()

        xml_bytes = await asyncio.to_thread(_fetch_xml)
        import xml.etree.ElementTree as ET

        root = ET.fromstring(xml_bytes)
        abstract_elem = root.findall(".//AbstractText")
        abstract_text = " ".join("".join(elem.itertext()) for elem in abstract_elem)
        abstract_status = "AVAILABLE" if abstract_text.strip() else "ABSENT_IN_SOURCE"
        mesh_elems = root.findall(".//MeshHeading/DescriptorName")
        mesh_terms = [m.text for m in mesh_elems if m.text]
    except Exception as e:
        abstract_status = "FETCH_FAILED"
        abstract_error = type(e).__name__
        logger.debug("Could not fetch full XML abstract for PMID %s: %s", pmid, abstract_error)

    authors = [a.get("name", "") for a in info.get("authors", [])]
    doi = next((item.get("value") for item in info.get("articleids", []) if item.get("idtype") == "doi"), None)

    return {
        "pmid": pmid,
        "title": info.get("title", ""),
        "authors": authors,
        "journal": info.get("source", ""),
        "pub_date": info.get("pubdate", ""),
        "volume": info.get("volume", ""),
        "issue": info.get("issue", ""),
        "pages": info.get("pages", ""),
        "doi": doi,
        "abstract": abstract_text,
        "abstract_status": abstract_status,
        "abstract_error": abstract_error,
        "mesh_terms": mesh_terms,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
    }


async def tool_search_biorxiv(query: str, server: str = "biorxiv", limit: int = 5, page: int = 1) -> Dict[str, Any]:
    """Search preprints on bioRxiv or medRxiv with pagination."""
    limit = min(max(1, int(limit)), 50)
    page = max(1, int(page))
    server = "medrxiv" if server.lower() == "medrxiv" else "biorxiv"

    epmc_query = f"{query} (SRC:PPR OR PUBLISHER:{server})"
    params = {"query": epmc_query, "format": "json", "pageSize": str(limit), "page": str(page), "resultType": "lite"}
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{urllib.parse.urlencode(params)}"
    data = await _get_http()(url)

    hit_count = data.get("hitCount", 0)
    results = data.get("resultList", {}).get("result", [])
    papers = []
    for r in results:
        papers.append(
            {
                "title": r.get("title", ""),
                "author_string": r.get("authorString", ""),
                "journal_title": r.get("journalTitle", server.upper()),
                "pub_year": r.get("pubYear", ""),
                "doi": r.get("doi", ""),
                "abstract_snippet": r.get("abstractText", ""),
                "url": f"https://doi.org/{r.get('doi')}" if r.get("doi") else "",
            }
        )

    return {
        "query": query,
        "server": server,
        "total_hits": hit_count,
        "page": page,
        "limit": limit,
        "preprints": papers,
    }


