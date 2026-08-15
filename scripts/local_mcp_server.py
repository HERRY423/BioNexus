#!/usr/bin/env python3
"""
Local Fallback MCP Server for Bio-Research (High-Performance Async Edition v2.0.0).
Implements Model Context Protocol (MCP) JSON-RPC 2.0 over stdio with asyncio.
Provides direct, non-blocking, rate-limit resilient access to:
  - NCBI PubMed & PubMed Central
  - bioRxiv & medRxiv (Europe PMC backend)
  - ChEMBL (Molecules, Targets, Assays)
  - Open Targets Platform (GraphQL API)
  - ClinicalTrials.gov (API v2)
  - UniProtKB (Proteins, Functions, Sequences)
  - Ensembl REST API (Genes, Coordinates, Orthologs)
  - gnomAD (Population Allele Frequencies, LOEUF, Gene Constraints)
  - RCSB PDB (Experimental 3D Macromolecular Structures)
  - AlphaFold DB (AI Predicted 3D Structures & pLDDT Confidence)
  - Reactome (Biological Pathways & Reaction Networks)
  - STRING DB (Protein-Protein Physical & Functional Interactions)
  - Ensembl lookup + tiny local CGC hint (not the COSMIC API)
  - NCBI GEO (Gene Expression Omnibus Datasets & Samples)
  - GTEx Portal (54 Tissue Expression Profiles & eQTLs)

Supports complete MCP primitives: Tools, Resources, and Prompts.
"""

import sys
import json
import os
import asyncio
import logging
import urllib.request
import urllib.parse
import urllib.error
import time
from typing import Dict, Any, List, Optional, Tuple, Union

# --- Logging Configuration ---
LOG_FILE = os.environ.get("BIONEXUS_MCP_LOG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_mcp_server.log"))
logger = logging.getLogger("BioNexusMCP")
logger.setLevel(logging.INFO)

# Use file handler only to keep stdout clean for JSON-RPC
try:
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s"))
    logger.addHandler(file_handler)
except Exception:
    logger.addHandler(logging.NullHandler())


# --- Proactive Token-Bucket Rate Limiter ---

class TokenBucketRateLimiter:
    """Thread-safe token bucket rate limiter to prevent API 429 rate limit saturation."""
    def __init__(self, rate: float = 3.0, capacity: float = 5.0):
        self.rate = rate  # tokens added per second
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

            if self.tokens < 1.0:
                wait_time = (1.0 - self.tokens) / self.rate
                await asyncio.sleep(wait_time)
                self.tokens = 0.0
            else:
                self.tokens -= 1.0


# Domain-specific rate limiters
RATE_LIMITERS: Dict[str, TokenBucketRateLimiter] = {
    "ncbi": TokenBucketRateLimiter(rate=3.0, capacity=5.0),
    "ebi": TokenBucketRateLimiter(rate=5.0, capacity=10.0),
    "opentargets": TokenBucketRateLimiter(rate=5.0, capacity=10.0),
    "gnomad": TokenBucketRateLimiter(rate=4.0, capacity=8.0),
    "pdb": TokenBucketRateLimiter(rate=5.0, capacity=10.0),
    "alphafold": TokenBucketRateLimiter(rate=5.0, capacity=10.0),
    "string": TokenBucketRateLimiter(rate=3.0, capacity=5.0),
    "default": TokenBucketRateLimiter(rate=5.0, capacity=10.0),
}


def _get_limiter_for_url(url: str) -> TokenBucketRateLimiter:
    if "ncbi.nlm.nih.gov" in url:
        return RATE_LIMITERS["ncbi"]
    elif "ebi.ac.uk" in url or "uniprot.org" in url or "ensembl.org" in url or "reactome.org" in url:
        return RATE_LIMITERS["ebi"]
    elif "opentargets.org" in url:
        return RATE_LIMITERS["opentargets"]
    elif "gnomad" in url:
        return RATE_LIMITERS["gnomad"]
    elif "rcsb.org" in url:
        return RATE_LIMITERS["pdb"]
    elif "ebi.ac.uk/pdbe" in url or "alphafold" in url:
        return RATE_LIMITERS["alphafold"]
    elif "string-db.org" in url:
        return RATE_LIMITERS["string"]
    return RATE_LIMITERS["default"]


# --- Configuration & Auth Loading ---
def get_api_key(key_name: str) -> Optional[str]:
    """Retrieve API key from environment variable or local .env file."""
    val = os.environ.get(key_name)
    if val:
        return val.strip()

    search_dirs = [
        os.getcwd(),
        os.path.dirname(os.path.abspath(__file__)),
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ]
    for search_dir in search_dirs:
        env_path = os.path.join(search_dir, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(f"{key_name}="):
                            return line.split("=", 1)[1].strip().strip('"').strip("'")
            except Exception as e:
                logger.debug(f"Error reading .env from {env_path}: {e}")
    return None


# --- Async HTTP Engine with Exponential Backoff Retries ---

async def async_http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    timeout: int = 15,
    max_retries: int = 3,
    backoff_factor: float = 1.5
) -> Any:
    """
    Execute asynchronous HTTP request with non-blocking I/O and exponential backoff retry.
    Uses asyncio.to_thread for thread-pool I/O without blocking the JSON-RPC event loop.
    """
    limiter = _get_limiter_for_url(url)
    await limiter.acquire()

    req_headers = {
        "User-Agent": "BioNexus-LocalMCP/2.0.0 (OpenScience; Contact: https://agent-plugins.org/)",
        "Accept": "application/json"
    }
    if headers:
        req_headers.update(headers)

    body_bytes = None
    if json_data is not None:
        req_headers["Content-Type"] = "application/json"
        body_bytes = json.dumps(json_data).encode("utf-8")

    def _sync_request():
        req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8")
            if not content.strip():
                return {}
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return {"raw_text": content}

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            return await asyncio.to_thread(_sync_request)
        except urllib.error.HTTPError as e:
            last_exc = e
            logger.warning(f"HTTP {e.code} on {url} (attempt {attempt}/{max_retries})")
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries:
                delay = backoff_factor ** attempt
                await asyncio.sleep(delay)
            else:
                raise
        except Exception as e:
            last_exc = e
            logger.warning(f"Network error on {url} (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                delay = backoff_factor ** attempt
                await asyncio.sleep(delay)
            else:
                raise

    raise last_exc or RuntimeError(f"Failed request to {url}")


# --- Tool Implementations (Core 8 Tools) ---

async def tool_search_pubmed(
    query: str,
    max_results: int = 5,
    offset: int = 0,
    sort: str = "pub_date",
    mindate: Optional[str] = None,
    maxdate: Optional[str] = None
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
        "sort": sort
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
    search_data = await async_http_request(search_url)
    esearch = search_data.get("esearchresult", {})
    id_list = esearch.get("idlist", [])
    total_found = int(esearch.get("count", 0))

    if not id_list:
        return {
            "query": query,
            "total_found": total_found,
            "offset": offset,
            "limit": max_results,
            "articles": []
        }

    summary_params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "json"
    }
    if api_key:
        summary_params["api_key"] = api_key

    summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{urllib.parse.urlencode(summary_params)}"
    summary_data = await async_http_request(summary_url)
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
        "total_found": total_found,
        "offset": offset,
        "limit": max_results,
        "returned": len(articles),
        "articles": articles
    }


async def tool_get_pubmed_article(pmid: str) -> Dict[str, Any]:
    """Retrieve full abstract, MeSH terms, and citation metadata for a specific PubMed PMID."""
    pmid = str(pmid).strip()
    api_key = get_api_key("NCBI_API_KEY")

    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "json"
    }
    if api_key:
        params["api_key"] = api_key

    summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{urllib.parse.urlencode(params)}"
    summary_data = await async_http_request(summary_url)
    info = summary_data.get("result", {}).get(pmid, {})

    abstract_text = ""
    mesh_terms = []
    try:
        fetch_params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml"
        }
        if api_key:
            fetch_params["api_key"] = api_key
        fetch_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?{urllib.parse.urlencode(fetch_params)}"
        
        def _fetch_xml():
            req = urllib.request.Request(fetch_url, headers={"User-Agent": "BioNexus-LocalMCP/2.0.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                return resp.read()

        xml_bytes = await asyncio.to_thread(_fetch_xml)
        import xml.etree.ElementTree as ET
        root = ET.fromstring(xml_bytes)
        abstract_elem = root.findall(".//AbstractText")
        abstract_text = " ".join([elem.text or "" for elem in abstract_elem if elem.text])
        mesh_elems = root.findall(".//MeshHeading/DescriptorName")
        mesh_terms = [m.text for m in mesh_elems if m.text]
    except Exception as e:
        logger.debug(f"Could not fetch full XML abstract for PMID {pmid}: {e}")

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
        "mesh_terms": mesh_terms,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    }


async def tool_search_biorxiv(
    query: str,
    server: str = "biorxiv",
    limit: int = 5,
    page: int = 1
) -> Dict[str, Any]:
    """Search preprints on bioRxiv or medRxiv with pagination."""
    limit = min(max(1, int(limit)), 50)
    page = max(1, int(page))
    server = "medrxiv" if server.lower() == "medrxiv" else "biorxiv"

    epmc_query = f"{query} (SRC:PPR OR PUBLISHER:{server})"
    params = {
        "query": epmc_query,
        "format": "json",
        "pageSize": str(limit),
        "page": str(page),
        "resultType": "lite"
    }
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?{urllib.parse.urlencode(params)}"
    data = await async_http_request(url)

    hit_count = data.get("hitCount", 0)
    results = data.get("resultList", {}).get("result", [])
    papers = []
    for r in results:
        papers.append({
            "title": r.get("title", ""),
            "author_string": r.get("authorString", ""),
            "journal_title": r.get("journalTitle", server.upper()),
            "pub_year": r.get("pubYear", ""),
            "doi": r.get("doi", ""),
            "abstract_snippet": r.get("abstractText", ""),
            "url": f"https://doi.org/{r.get('doi')}" if r.get("doi") else ""
        })

    return {
        "query": query,
        "server": server,
        "total_hits": hit_count,
        "page": page,
        "limit": limit,
        "preprints": papers
    }


async def tool_search_chembl(
    query: str,
    entity_type: str = "molecule",
    limit: int = 5,
    offset: int = 0
) -> Dict[str, Any]:
    """Query ChEMBL database for bioactive molecules, targets, or assays with pagination."""
    limit = min(max(1, int(limit)), 50)
    offset = max(0, int(offset))
    entity_type = entity_type.lower()

    if entity_type == "target":
        url = f"https://www.ebi.ac.uk/chembl/api/data/target/search.json?q={urllib.parse.quote(query)}&limit={limit}&offset={offset}"
        data = await async_http_request(url)
        targets = []
        for t in data.get("targets", []):
            targets.append({
                "chembl_id": t.get("target_chembl_id"),
                "pref_name": t.get("pref_name"),
                "target_type": t.get("target_type"),
                "organism": t.get("organism"),
                "target_components": [c.get("component_type") for c in t.get("target_components", [])]
            })
        total = data.get("page_meta", {}).get("total_count", len(targets))
        return {"query": query, "entity_type": "target", "total_found": total, "offset": offset, "results": targets}

    elif entity_type == "assay":
        url = f"https://www.ebi.ac.uk/chembl/api/data/assay/search.json?q={urllib.parse.quote(query)}&limit={limit}&offset={offset}"
        data = await async_http_request(url)
        assays = []
        for a in data.get("assays", []):
            assays.append({
                "assay_chembl_id": a.get("assay_chembl_id"),
                "description": a.get("description"),
                "assay_type": a.get("assay_type"),
                "assay_organism": a.get("assay_organism")
            })
        total = data.get("page_meta", {}).get("total_count", len(assays))
        return {"query": query, "entity_type": "assay", "total_found": total, "offset": offset, "results": assays}

    else:
        url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/search.json?q={urllib.parse.quote(query)}&limit={limit}&offset={offset}"
        data = await async_http_request(url)
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
                "alogp": props.get("alogp"),
                "hba": props.get("hba"),
                "hbd": props.get("hbd"),
                "psa": props.get("psa"),
                "canonical_smiles": structures.get("canonical_smiles")
            })
        total = data.get("page_meta", {}).get("total_count", len(molecules))
        return {"query": query, "entity_type": "molecule", "total_found": total, "offset": offset, "results": molecules}


async def tool_search_opentargets(
    query: str,
    entity_types: Optional[List[str]] = None,
    limit: int = 5,
    page_index: int = 0
) -> Dict[str, Any]:
    """Query Open Targets Platform GraphQL API for disease-target associations."""
    limit = min(max(1, int(limit)), 50)
    page_index = max(0, int(page_index))
    if not entity_types:
        entity_types = ["target", "disease", "drug"]

    gql_query = """
    query SearchQuery($queryString: String!, $entityNames: [String!]!, $size: Int!, $index: Int!) {
      search(queryString: $queryString, entityNames: $entityNames, page: {size: $size, index: $index}) {
        total
        hits {
          id
          name
          entity
          description
          score
        }
      }
    }
    """
    payload = {
        "query": gql_query,
        "variables": {
            "queryString": query,
            "entityNames": entity_types,
            "size": limit,
            "index": page_index
        }
    }
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    data = await async_http_request(url, method="POST", json_data=payload)
    search_res = data.get("data", {}).get("search", {})
    hits = search_res.get("hits", [])
    total = search_res.get("total", len(hits))

    return {
        "query": query,
        "entity_types": entity_types,
        "total_hits": total,
        "page_index": page_index,
        "limit": limit,
        "results": hits
    }


async def tool_search_clinical_trials(
    condition: str,
    intervention: str = "",
    status: Optional[str] = None,
    limit: int = 5,
    page_token: Optional[str] = None
) -> Dict[str, Any]:
    """Query ClinicalTrials.gov API v2 with status filter and cursor pagination."""
    limit = min(max(1, int(limit)), 50)
    params = {
        "query.cond": condition,
        "pageSize": str(limit)
    }
    if intervention:
        params["query.intr"] = intervention
    if status:
        params["filter.overallStatus"] = status
    if page_token:
        params["pageToken"] = page_token

    url = f"https://clinicaltrials.gov/api/v2/studies?{urllib.parse.urlencode(params)}"
    data = await async_http_request(url)

    studies = []
    for s in data.get("studies", []):
        protocol = s.get("protocolSection", {})
        id_module = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        design_module = protocol.get("designModule", {})
        conditions_module = protocol.get("conditionsModule", {})

        nct_id = id_module.get("nctId")
        brief_title = id_module.get("briefTitle")
        overall_status = status_module.get("overallStatus")
        phases = design_module.get("phases", [])
        cond_list = conditions_module.get("conditions", [])

        studies.append({
            "nct_id": nct_id,
            "title": brief_title,
            "status": overall_status,
            "phases": phases,
            "conditions": cond_list,
            "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else ""
        })

    next_page_token = data.get("nextPageToken")
    total_count = data.get("totalCount", len(studies))

    return {
        "condition": condition,
        "intervention": intervention,
        "total_count": total_count,
        "next_page_token": next_page_token,
        "studies": studies
    }


async def tool_search_uniprot(
    query: str,
    organism: Optional[str] = "human",
    limit: int = 5
) -> Dict[str, Any]:
    """Query UniProtKB for protein functions, gene names, sequences, and accessions."""
    limit = min(max(1, int(limit)), 50)
    search_term = query
    if organism and organism.lower() == "human":
        search_term = f"{query} AND organism_id:9606"
    elif organism and organism.lower() == "mouse":
        search_term = f"{query} AND organism_id:10090"
    elif organism:
        search_term = f"{query} AND organism_name:{organism}"

    params = {
        "query": search_term,
        "format": "json",
        "size": str(limit),
        "fields": "accession,id,gene_names,protein_name,organism_name,length,cc_function"
    }
    url = f"https://rest.uniprot.org/uniprotkb/search?{urllib.parse.urlencode(params)}"
    data = await async_http_request(url)

    results = []
    for entry in data.get("results", []):
        primary_acc = entry.get("primaryAccession")
        entry_name = entry.get("uniProtkbId")
        organism_name = entry.get("organism", {}).get("scientificName")
        
        desc = entry.get("proteinDescription", {})
        recommended_name = desc.get("recommendedName", {}).get("fullName", {}).get("value", "Unknown")

        genes = []
        for g in entry.get("genes", []):
            if "geneName" in g:
                genes.append(g["geneName"].get("value"))

        functions = []
        for comment in entry.get("comments", []):
            if comment.get("commentType") == "FUNCTION":
                for text_obj in comment.get("texts", []):
                    functions.append(text_obj.get("value", ""))

        results.append({
            "accession": primary_acc,
            "id": entry_name,
            "protein_name": recommended_name,
            "genes": genes,
            "organism": organism_name,
            "sequence_length": entry.get("sequence", {}).get("length"),
            "function": " ".join(functions)[:500],
            "url": f"https://www.uniprot.org/uniprotkb/{primary_acc}"
        })

    return {
        "query": query,
        "organism": organism,
        "total_results": len(results),
        "proteins": results
    }


async def tool_search_ensembl(
    symbol: str,
    species: str = "human"
) -> Dict[str, Any]:
    """Query Ensembl REST API for gene metadata, coordinates, biotype, and transcript structures."""
    species = "homo_sapiens" if species.lower() in ("human", "homo_sapiens") else species
    url = f"https://rest.ensembl.org/lookup/symbol/{species}/{symbol}?expand=1"
    headers = {"Content-Type": "application/json"}
    try:
        data = await async_http_request(url, headers=headers)
        transcripts = []
        for t in data.get("Transcript", [])[:10]:
            transcripts.append({
                "id": t.get("id"),
                "biotype": t.get("biotype"),
                "is_canonical": bool(t.get("is_canonical")),
                "length": t.get("length")
            })
        return {
            "symbol": symbol,
            "species": species,
            "ensembl_id": data.get("id"),
            "biotype": data.get("biotype"),
            "description": data.get("description"),
            "chromosome": data.get("seq_region_name"),
            "start": data.get("start"),
            "end": data.get("end"),
            "strand": data.get("strand"),
            "transcripts": transcripts
        }
    except Exception as e:
        logger.error(f"Ensembl lookup failed for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}


# --- Tool Implementations (Phase 4 Extended 8 Tools) ---

async def tool_search_gnomad(
    gene_symbol: Optional[str] = None,
    variant_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Query gnomAD GraphQL API for population allele frequencies, pLI loss-of-function constraint,
    LOEUF scores, and missense z-scores.
    """
    url = "https://gnomad.broadinstitute.org/api"
    if gene_symbol:
        gql_query = """
        query GeneConstraint($gene_symbol: String!) {
          gene(gene_symbol: $gene_symbol, reference_genome: GRCh38) {
            gene_id
            symbol
            name
            gnomad_constraint {
              pLI
              loeuf
              oe_lof
              oe_lof_lower
              oe_lof_upper
              oe_mis
              mis_z
              syn_z
            }
          }
        }
        """
        payload = {"query": gql_query, "variables": {"gene_symbol": gene_symbol}}
        try:
            data = await async_http_request(url, method="POST", json_data=payload)
            gene_info = data.get("data", {}).get("gene", {})
            return {
                "query_type": "gene_constraint",
                "symbol": gene_symbol,
                "gene_id": gene_info.get("gene_id"),
                "name": gene_info.get("name"),
                "constraint": gene_info.get("gnomad_constraint", {})
            }
        except Exception as e:
            logger.error(f"gnomAD gene constraint query failed for {gene_symbol}: {e}")
            return {"symbol": gene_symbol, "error": str(e)}

    elif variant_id:
        gql_query = """
        query VariantFrequency($variantId: String!) {
          variant(variantId: $variantId, dataset: gnomad_r4) {
            variantId
            chrom
            pos
            ref
            alt
            genome {
              ac
              an
              af
              homozygote_count
            }
            exome {
              ac
              an
              af
              homozygote_count
            }
          }
        }
        """
        payload = {"query": gql_query, "variables": {"variantId": variant_id}}
        try:
            data = await async_http_request(url, method="POST", json_data=payload)
            var_info = data.get("data", {}).get("variant", {})
            return {
                "query_type": "variant_frequency",
                "variant_id": variant_id,
                "variant": var_info
            }
        except Exception as e:
            logger.error(f"gnomAD variant frequency query failed for {variant_id}: {e}")
            return {"variant_id": variant_id, "error": str(e)}
    else:
        return {"error": "Must provide either gene_symbol or variant_id"}


async def tool_search_pdb(
    query: str,
    limit: int = 5
) -> Dict[str, Any]:
    """
    Search RCSB Protein Data Bank (PDB) for experimentally solved 3D structures,
    experimental method, resolution, and bound ligands.
    """
    limit = min(max(1, int(limit)), 50)
    search_url = "https://search.rcsb.org/rcsbsearch/v2/query"
    search_payload = {
        "query": {
            "type": "terminal",
            "service": "full_text",
            "parameters": {
                "value": query
            }
        },
        "return_type": "entry",
        "request_options": {
            "paginate": {
                "start": 0,
                "rows": limit
            }
        }
    }
    try:
        search_data = await async_http_request(search_url, method="POST", json_data=search_payload)
        result_set = search_data.get("result_set", [])
        total_count = search_data.get("total_count", len(result_set))
        
        entries = []
        for item in result_set:
            pdb_id = item.get("identifier")
            score = item.get("score")
            detail_url = f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}"
            try:
                detail_data = await async_http_request(detail_url)
                struct = detail_data.get("struct", {})
                title = struct.get("title", "")
                exptl = detail_data.get("exptl", [{}])[0]
                method = exptl.get("method", "Unknown")
                rcsb_entry = detail_data.get("rcsb_entry_info", {})
                resolution = rcsb_entry.get("resolution_combined", [None])[0]
                release_date = detail_data.get("rcsb_accession_info", {}).get("initial_release_date", "")

                entries.append({
                    "pdb_id": pdb_id,
                    "title": title,
                    "method": method,
                    "resolution_angstrom": resolution,
                    "release_date": release_date,
                    "relevance_score": score,
                    "pdb_url": f"https://www.rcsb.org/structure/{pdb_id}",
                    "cif_download_url": f"https://files.rcsb.org/download/{pdb_id}.cif"
                })
            except Exception:
                entries.append({
                    "pdb_id": pdb_id,
                    "relevance_score": score,
                    "pdb_url": f"https://www.rcsb.org/structure/{pdb_id}"
                })

        return {
            "query": query,
            "total_found": total_count,
            "limit": limit,
            "structures": entries
        }
    except Exception as e:
        logger.error(f"PDB search failed for {query}: {e}")
        return {"query": query, "error": str(e)}


async def tool_search_alphafold(
    uniprot_id: str
) -> Dict[str, Any]:
    """
    Query AlphaFold Protein Structure Database API for predicted 3D structures,
    per-residue pLDDT confidence metrics, and download links.
    """
    uniprot_id = uniprot_id.strip().upper()
    url = f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id}"
    try:
        data = await async_http_request(url)
        if isinstance(data, list) and data:
            entry = data[0]
        elif isinstance(data, dict):
            entry = data
        else:
            return {"uniprot_id": uniprot_id, "error": "Structure prediction not found"}

        return {
            "uniprot_id": uniprot_id,
            "entry_id": entry.get("entryId"),
            "gene": entry.get("gene"),
            "organism_scientific_name": entry.get("organismScientificName"),
            "uniprot_sequence_length": entry.get("uniprotSequenceLength"),
            "global_plddt": entry.get("globalPlddt"),
            "pdb_url": entry.get("pdbUrl"),
            "cif_url": entry.get("cifUrl"),
            "pae_image_url": entry.get("paeImageUrl"),
            "pae_doc_url": entry.get("paeDocUrl"),
            "model_created_date": entry.get("modelCreatedDate")
        }
    except Exception as e:
        logger.error(f"AlphaFold lookup failed for {uniprot_id}: {e}")
        return {"uniprot_id": uniprot_id, "error": str(e)}


async def tool_search_reactome(
    query: str,
    species: str = "Homo sapiens",
    limit: int = 5
) -> Dict[str, Any]:
    """
    Query Reactome Content Service for biological pathways, reactions,
    pathway hierarchies, and participating molecules.
    """
    limit = min(max(1, int(limit)), 50)
    params = {
        "query": query,
        "species": species,
        "types": "Pathway",
        "rows": str(limit)
    }
    url = f"https://reactome.org/ContentService/search/query?{urllib.parse.urlencode(params)}"
    try:
        data = await async_http_request(url)
        results = data.get("results", [])
        pathways = []
        for r in results:
            entries = r.get("entries", [])
            for e in entries[:limit]:
                pathways.append({
                    "stId": e.get("stId"),
                    "name": e.get("name"),
                    "species": e.get("species", [species])[0] if isinstance(e.get("species"), list) else e.get("species"),
                    "type": e.get("exactType"),
                    "url": f"https://reactome.org/PathwayBrowser/#/{e.get('stId')}"
                })
        return {
            "query": query,
            "species": species,
            "total_found": len(pathways),
            "pathways": pathways[:limit]
        }
    except Exception as e:
        logger.error(f"Reactome search failed for {query}: {e}")
        return {"query": query, "error": str(e)}


async def tool_search_string(
    gene_symbol: str,
    species: int = 9606,
    limit: int = 10,
    required_score: int = 400
) -> Dict[str, Any]:
    """
    Query STRING DB API v12 for protein-protein physical and functional interaction networks
    with confidence scores and evidence breakdown.
    """
    limit = min(max(1, int(limit)), 50)
    params = {
        "identifiers": gene_symbol,
        "species": str(species),
        "limit": str(limit),
        "required_score": str(required_score),
        "caller_identity": "bionexus_plugin"
    }
    url = f"https://string-db.org/api/json/interaction_partners?{urllib.parse.urlencode(params)}"
    try:
        data = await async_http_request(url)
        interactions = []
        if isinstance(data, list):
            for row in data:
                interactions.append({
                    "preferred_name_a": row.get("preferredName_A"),
                    "preferred_name_b": row.get("preferredName_B"),
                    "combined_score": row.get("score"),
                    "experimental_score": row.get("escore"),
                    "database_score": row.get("dscore"),
                    "coexpression_score": row.get("ascore"),
                    "textmining_score": row.get("tscore")
                })
        return {
            "gene_symbol": gene_symbol,
            "species": species,
            "interaction_count": len(interactions),
            "interactions": interactions[:limit]
        }
    except Exception as e:
        logger.error(f"STRING search failed for {gene_symbol}: {e}")
        return {"gene_symbol": gene_symbol, "error": str(e)}


# Small well-known CGC subset for local hints only. Not the COSMIC API.
_LOCAL_CGC_HINTS = {
    "TP53", "KRAS", "BRAF", "EGFR", "PIK3CA", "PTEN", "BRCA1", "BRCA2",
    "MYC", "ALK", "ABL1", "BCR", "APC", "RB1", "VHL", "NF1", "IDH1",
}


async def tool_search_cosmic(
    gene_symbol: str
) -> Dict[str, Any]:
    """Ensembl lookup plus a local CGC hint. This is not the COSMIC REST API."""
    gene = gene_symbol.strip().upper()
    url = f"https://rest.ensembl.org/lookup/symbol/homo_sapiens/{gene}?expand=1"
    try:
        ens_data = await async_http_request(url, headers={"Content-Type": "application/json"})
        desc = ens_data.get("description", "")
        in_local = gene in _LOCAL_CGC_HINTS
        return {
            "gene_symbol": gene,
            "ensembl_id": ens_data.get("id"),
            "description": desc,
            "chromosome": ens_data.get("seq_region_name"),
            "start": ens_data.get("start"),
            "end": ens_data.get("end"),
            "cosmic_url": f"https://cancer.sanger.ac.uk/cosmic/gene/analysis?ln={gene}",
            "cgc_tier_check": None,
            "local_cgc_hint": in_local,
            "method": "ensembl_lookup_plus_local_cgc_hint",
            "backend": "ensembl_rest",
            "evidence_grade": "C",
            "limitations": [
                "Not the COSMIC API (license-restricted).",
                "local_cgc_hint is a tiny curated subset, not Census membership.",
            ],
        }
    except Exception as e:
        logger.error(f"Ensembl cancer-context lookup failed for {gene_symbol}: {e}")
        return {"gene_symbol": gene_symbol, "error": str(e), "cgc_tier_check": None}


async def tool_search_geo(
    query: str,
    max_results: int = 5
) -> Dict[str, Any]:
    """
    Search NCBI Gene Expression Omnibus (GEO) datasets (GSE) and samples (GSM) via E-utilities.
    """
    max_results = min(max(1, int(max_results)), 50)
    api_key = get_api_key("NCBI_API_KEY")
    term = f"{query} AND gds[Entry Type]"
    params = {
        "db": "gds",
        "term": term,
        "retmode": "json",
        "retmax": str(max_results)
    }
    if api_key:
        params["api_key"] = api_key

    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{urllib.parse.urlencode(params)}"
    try:
        search_data = await async_http_request(search_url)
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        total_found = int(search_data.get("esearchresult", {}).get("count", 0))

        if not id_list:
            return {"query": query, "total_found": total_found, "datasets": []}

        summary_params = {
            "db": "gds",
            "id": ",".join(id_list),
            "retmode": "json"
        }
        if api_key:
            summary_params["api_key"] = api_key

        summary_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{urllib.parse.urlencode(summary_params)}"
        summary_data = await async_http_request(summary_url)
        results = summary_data.get("result", {})

        datasets = []
        for gds_id in id_list:
            info = results.get(gds_id, {})
            accession = info.get("accession", f"GDS{gds_id}")
            title = info.get("title", "")
            summary = info.get("summary", "")
            taxon = info.get("taxon", "")
            n_samples = info.get("nsamples", 0)

            datasets.append({
                "accession": accession,
                "title": title,
                "organism": taxon,
                "sample_count": n_samples,
                "summary": summary[:300] + ("..." if len(summary) > 300 else ""),
                "url": f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}"
            })

        return {
            "query": query,
            "total_found": total_found,
            "returned": len(datasets),
            "datasets": datasets
        }
    except Exception as e:
        logger.error(f"GEO search failed for {query}: {e}")
        return {"query": query, "error": str(e)}


async def tool_get_gene_expression(
    gene_symbol: str,
    tissue_site: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve tissue-specific RNA expression (median TPM) and eQTL associations across
    54 non-diseased human tissues from GTEx Portal.
    """
    symbol = gene_symbol.strip().upper()
    url = f"https://gtexportal.org/api/v2/expression/medianGeneExpression?geneId={symbol}&pageSize=100"
    try:
        data = await async_http_request(url)
        records = data.get("data", [])
        expression_profiles = []
        for rec in records:
            tissue = rec.get("tissueSiteDetailId") or rec.get("tissue")
            median_tpm = rec.get("median")
            unit = rec.get("unit", "TPM")
            if tissue_site and tissue_site.lower() not in str(tissue).lower():
                continue
            expression_profiles.append({
                "tissue": tissue,
                "median_tpm": median_tpm,
                "unit": unit
            })

        expression_profiles.sort(key=lambda x: (x["median_tpm"] or 0), reverse=True)

        return {
            "gene_symbol": symbol,
            "filtered_tissue": tissue_site,
            "tissue_count": len(expression_profiles),
            "expression": expression_profiles[:20],
            "gtex_url": f"https://gtexportal.org/home/gene/{symbol}"
        }
    except Exception as e:
        logger.error(f"GTEx expression query failed for {gene_symbol}: {e}")
        return {"gene_symbol": symbol, "error": str(e)}


# --- MCP Tool Schemas (16 Total Tools) ---

_HOSTED_FALLBACK_TOOLS = {
    "search_pubmed",
    "get_pubmed_article",
    "search_biorxiv",
    "search_chembl",
    "search_opentargets",
    "search_clinical_trials",
}

TOOLS_SCHEMA = [
    {
        "name": "search_pubmed",
        "description": "Search PubMed database for biomedical literature via NCBI E-utilities API with pagination and date filtering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords, gene symbols, disease names, or MeSH terms (e.g. 'KRAS G12D inhibitor', 'scRNA-seq batch correction')."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum articles to return (1-50, default 5).",
                    "default": 5
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset / starting index (default: 0).",
                    "default": 0
                },
                "sort": {
                    "type": "string",
                    "enum": ["pub_date", "relevance"],
                    "description": "Sort order ('pub_date' or 'relevance'). Default is 'pub_date'.",
                    "default": "pub_date"
                },
                "mindate": {
                    "type": "string",
                    "description": "Earliest publication date (YYYY/MM/DD or YYYY, optional)."
                },
                "maxdate": {
                    "type": "string",
                    "description": "Latest publication date (YYYY/MM/DD or YYYY, optional)."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_pubmed_article",
        "description": "Fetch complete abstract, author affiliations, MeSH terms, and citation metadata for a specific PubMed PMID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pmid": {
                    "type": "string",
                    "description": "PubMed Identifier (PMID, e.g. '37123456')."
                }
            },
            "required": ["pmid"]
        }
    },
    {
        "name": "search_biorxiv",
        "description": "Search life science preprints on bioRxiv or medRxiv via Europe PMC API with pagination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Preprint search keywords or topics."
                },
                "server": {
                    "type": "string",
                    "enum": ["biorxiv", "medrxiv"],
                    "description": "Preprint server ('biorxiv' or 'medrxiv'). Default is 'biorxiv'.",
                    "default": "biorxiv"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum preprints to return (1-50, default 5).",
                    "default": 5
                },
                "page": {
                    "type": "integer",
                    "description": "Page number (default 1).",
                    "default": 1
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_chembl",
        "description": "Query ChEMBL database for bioactive molecules, targets, or bioactivity assays with molecular properties and structures.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Molecule name, SMILES string, or target name (e.g. 'Aspirin', 'EGFR', 'Gefitinib')."
                },
                "entity_type": {
                    "type": "string",
                    "enum": ["molecule", "target", "assay"],
                    "description": "Entity category to query ('molecule', 'target', or 'assay'). Default is 'molecule'.",
                    "default": "molecule"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum records to return (1-50, default 5).",
                    "default": 5
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset (default 0).",
                    "default": 0
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_opentargets",
        "description": "Query Open Targets Platform GraphQL API for disease-target associations, tractability, and drug mechanisms.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Disease name, gene target, or drug (e.g. 'lung adenocarcinoma', 'BRAF', 'Imatinib')."
                },
                "entity_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entity types to include ('target', 'disease', 'drug'). Default is all.",
                    "default": ["target", "disease", "drug"]
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (1-50, default 5).",
                    "default": 5
                },
                "page_index": {
                    "type": "integer",
                    "description": "Page index (default 0).",
                    "default": 0
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_clinical_trials",
        "description": "Query ClinicalTrials.gov API v2 for active or completed clinical trials, interventions, study phases, and protocols.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "condition": {
                    "type": "string",
                    "description": "Disease or medical condition (e.g. 'Melanoma', 'Triple Negative Breast Cancer')."
                },
                "intervention": {
                    "type": "string",
                    "description": "Optional drug or therapy intervention (e.g. 'Pembrolizumab').",
                    "default": ""
                },
                "status": {
                    "type": "string",
                    "description": "Recruitment status filter (e.g. 'RECRUITING', 'COMPLETED', 'ACTIVE_NOT_RECRUITING')."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum trials to return (1-50, default 5).",
                    "default": 5
                },
                "page_token": {
                    "type": "string",
                    "description": "Next page token for cursor pagination."
                }
            },
            "required": ["condition"]
        }
    },
    {
        "name": "search_uniprot",
        "description": "Query UniProtKB for curated protein details, sequence length, biological function, and gene associations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Protein name, gene symbol, or accession ID (e.g. 'TP53', 'P04637', 'EGFR')."
                },
                "organism": {
                    "type": "string",
                    "description": "Organism filter ('human', 'mouse', or scientific name). Default is 'human'.",
                    "default": "human"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum proteins to return (1-50, default 5).",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_ensembl",
        "description": "Query Ensembl REST API for gene genomic coordinates, chromosome, biotype, and canonical transcripts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Gene symbol (e.g. 'BRCA1', 'GAPDH', 'TNF')."
                },
                "species": {
                    "type": "string",
                    "description": "Species name ('human', 'mouse', 'rat', etc.). Default is 'human'.",
                    "default": "human"
                }
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "search_gnomad",
        "description": "Query gnomAD API for population allele frequencies, loss-of-function intolerance (pLI, LOEUF), and missense constraint z-scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gene_symbol": {
                    "type": "string",
                    "description": "Gene symbol to query constraint metrics for (e.g. 'BRCA1', 'SCN1A')."
                },
                "variant_id": {
                    "type": "string",
                    "description": "Variant coordinate ID in chr-pos-ref-alt format (e.g. '13-32315508-C-T')."
                }
            }
        }
    },
    {
        "name": "search_pdb",
        "description": "Search RCSB Protein Data Bank (PDB) for experimentally solved 3D structures, resolution, experimental methods, and ligands.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Protein name, PDB ID, macromolecule name, or ligand (e.g. 'CRISPR Cas9', '7K43', 'Kinase')."
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum structures to return (1-50, default 5).",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_alphafold",
        "description": "Query AlphaFold Protein Structure Database API for AI predicted 3D structures, pLDDT confidence scores, and CIF/PDB download links.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uniprot_id": {
                    "type": "string",
                    "description": "UniProt Accession ID (e.g. 'P04637', 'Q9BYF1', 'P38398')."
                }
            },
            "required": ["uniprot_id"]
        }
    },
    {
        "name": "search_reactome",
        "description": "Query Reactome Content Service for biological pathways, reactions, pathway hierarchies, and participating molecules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pathway name, gene symbol, or biological process (e.g. 'Apoptosis', 'EGFR signaling', 'Glycolysis')."
                },
                "species": {
                    "type": "string",
                    "description": "Species name (default: 'Homo sapiens').",
                    "default": "Homo sapiens"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum pathways to return (1-50, default 5).",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_string",
        "description": "Query STRING DB API v12 for protein-protein physical and functional interaction networks with confidence scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gene_symbol": {
                    "type": "string",
                    "description": "Gene symbol or protein identifier (e.g. 'TP53', 'CDK4', 'MDM2')."
                },
                "species": {
                    "type": "integer",
                    "description": "NCBI taxonomy ID (default 9606 for Homo sapiens).",
                    "default": 9606
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum interaction partners to return (1-50, default 10).",
                    "default": 10
                },
                "required_score": {
                    "type": "integer",
                    "description": "Minimum interaction confidence score (0-1000, default 400 for medium confidence).",
                    "default": 400
                }
            },
            "required": ["gene_symbol"]
        }
    },
    {
        "name": "search_cosmic",
        "description": "Ensembl gene lookup plus a tiny local Cancer Gene Census hint. Not the COSMIC API; does not assign CGC tier.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gene_symbol": {
                    "type": "string",
                    "description": "Gene symbol (e.g. 'KRAS', 'PIK3CA', 'PTEN')."
                }
            },
            "required": ["gene_symbol"]
        }
    },
    {
        "name": "search_geo",
        "description": "Search NCBI Gene Expression Omnibus (GEO) datasets (GSE) and samples (GSM) via E-utilities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Genomics study keywords, disease condition, or cell type (e.g. 'Glioblastoma scRNA-seq', 'Immunotherapy resistance')."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum datasets to return (1-50, default 5).",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "get_gene_expression",
        "description": "Retrieve tissue-specific RNA expression (median TPM) and eQTLs across 54 human tissues from GTEx Portal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gene_symbol": {
                    "type": "string",
                    "description": "Gene symbol (e.g. 'INS', 'GAPDH', 'HER2')."
                },
                "tissue_site": {
                    "type": "string",
                    "description": "Optional tissue filter (e.g. 'Liver', 'Brain', 'Lung', 'Pancreas')."
                }
            },
            "required": ["gene_symbol"]
        }
    }
]


def _annotate_local_mcp_roles() -> None:
    """Mark hosted-overlap tools as fallbacks so agents prefer mcp.json remotes."""
    for tool in TOOLS_SCHEMA:
        name = tool["name"]
        if name in _HOSTED_FALLBACK_TOOLS:
            tool["annotations"] = {"bionexus_role": "hosted_fallback"}
            desc = tool.get("description", "")
            if not desc.startswith("[local fallback"):
                tool["description"] = "[local fallback — prefer hosted MCP if connected] " + desc
        else:
            tool["annotations"] = {"bionexus_role": "local_unique"}
            if name == "search_cosmic":
                continue
            desc = tool.get("description", "")
            if not desc.startswith("[local unique]"):
                tool["description"] = "[local unique] " + desc


_annotate_local_mcp_roles()

_DEFAULT_HIDDEN_LOCAL_TOOLS = _HOSTED_FALLBACK_TOOLS | {"search_cosmic"}


def public_tools_schema():
    """Default: unique local tools only. Set BIONEXUS_LOCAL_HOSTED_FALLBACKS=1 for all 16."""
    flag = os.environ.get("BIONEXUS_LOCAL_HOSTED_FALLBACKS", "").strip().lower()
    if flag in {"1", "true", "yes"}:
        return TOOLS_SCHEMA
    return [tool for tool in TOOLS_SCHEMA if tool["name"] not in _DEFAULT_HIDDEN_LOCAL_TOOLS]


# --- MCP Resources & Prompts Specifications (Phase 4F) ---

RESOURCES_SCHEMA = [
    {
        "uri": "bionexus://workflows/drug_target_discovery",
        "name": "Drug Target Discovery Workflow Template",
        "description": "Production YAML DAG for multi-criteria drug target ranking and validation.",
        "mimeType": "text/yaml"
    },
    {
        "uri": "bionexus://workflows/single_cell_atlas",
        "name": "Single Cell Atlas Workflow Template",
        "description": "Production YAML DAG for single-cell preprocessing, VAE training, and clustering.",
        "mimeType": "text/yaml"
    },
    {
        "uri": "bionexus://workflows/variant_interpretation",
        "name": "Variant Interpretation Workflow Template",
        "description": "Production YAML DAG for ACMG/AMP clinical variant interpretation.",
        "mimeType": "text/yaml"
    },
    {
        "uri": "bionexus://configs/acmg_rules",
        "name": "ACMG Classification Rules Configuration",
        "description": "28 ACMG/AMP evidence rules with likelihood ratios and Bayesian priors.",
        "mimeType": "text/yaml"
    },
    {
        "uri": "bionexus://configs/germline_vgenes",
        "name": "Human Germline V-Gene Consensus Configuration",
        "description": "Human immunoglobulin heavy and light chain framework anchors and developability criteria.",
        "mimeType": "text/yaml"
    },
    {
        "uri": "bionexus://configs/docking_params",
        "name": "Molecular Docking Parameters Configuration",
        "description": "AutoDock Vina and DiffDock parameter presets and drug-likeness rules.",
        "mimeType": "text/yaml"
    }
]

PROMPTS_SCHEMA = [
    {
        "name": "drug_target_analysis",
        "description": "Comprehensive drug target identification, tractability, and druggability evaluation prompt.",
        "arguments": [
            {"name": "disease", "description": "Target disease indication (e.g. 'Non-small cell lung cancer')", "required": True},
            {"name": "target_gene", "description": "Candidate target gene symbol (e.g. 'EGFR')", "required": True}
        ]
    },
    {
        "name": "variant_pathogenicity",
        "description": "Clinical genomic variant pathogenicity assessment adhering to ACMG/AMP guidelines.",
        "arguments": [
            {"name": "variant", "description": "Genomic variant in HGVS or chr-pos-ref-alt format", "required": True},
            {"name": "disease", "description": "Associated clinical phenotype / condition", "required": True}
        ]
    },
    {
        "name": "antibody_developability_audit",
        "description": "Biophysical developability, CDR-H3 aggregation propensity, and humanness audit prompt for therapeutic antibodies.",
        "arguments": [
            {"name": "antibody_name", "description": "Antibody or clone identifier", "required": True},
            {"name": "target_antigen", "description": "Target antigen symbol", "required": True}
        ]
    },
    {
        "name": "survival_biomarker_screening",
        "description": "Pan-cancer clinical cohort survival analysis, Kaplan-Meier stratification, and Cox HR modeling prompt.",
        "arguments": [
            {"name": "biomarker_gene", "description": "Candidate biomarker gene symbol", "required": True},
            {"name": "cancer_cohort", "description": "Cancer cohort (e.g. 'TCGA-LUAD')", "required": True}
        ]
    },
    {
        "name": "spatial_niche_discovery",
        "description": "Spatial transcriptomics tumor microenvironment niche and ligand-receptor analysis prompt.",
        "arguments": [
            {"name": "tissue_type", "description": "Tissue sample type (e.g. 'Colorectal tumor slice')", "required": True}
        ]
    },
    {
        "name": "single_cell_integration",
        "description": "Multi-batch scRNA-seq integration, VAE hyperparameter tuning, and marker gene analysis prompt.",
        "arguments": [
            {"name": "dataset_summary", "description": "Summary of batches, cell count, and platform", "required": True}
        ]
    }
]


# --- Async JSON-RPC Dispatcher ---

async def handle_rpc_request_async(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Dispatch incoming JSON-RPC request asynchronously."""
    msg_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})

    logger.debug(f"Handling method: {method}, id: {msg_id}")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {},
                    "resources": {},
                    "prompts": {}
                },
                "serverInfo": {
                    "name": "bio-research-local-mcp",
                    "version": "2.0.0"
                }
            }
        }
    elif method in ("notifications/initialized", "initialized"):
        return None
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
                "tools": public_tools_schema()
            }
        }
    elif method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "resources": RESOURCES_SCHEMA
            }
        }
    elif method == "resources/read":
        uri = params.get("uri", "")
        resource_map = {
            "bionexus://workflows/drug_target_discovery": os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "skills", "research-workflow-orchestrator", "templates", "drug_target_discovery.yml",
            ),
            "bionexus://workflows/single_cell_atlas": os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "skills", "research-workflow-orchestrator", "templates", "single_cell_atlas.yml",
            ),
            "bionexus://workflows/variant_interpretation": os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "skills", "research-workflow-orchestrator", "templates", "variant_interpretation.yml",
            ),
            "bionexus://configs/acmg_rules": os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "skills", "variant-interpretation", "configs", "acmg_rules.yml",
            ),
            "bionexus://configs/germline_vgenes": os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "skills", "biologics-design", "configs", "germline_vgenes.yml",
            ),
            "bionexus://configs/docking_params": os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "skills", "protein-structure-analysis", "configs", "docking_params.yml",
            ),
        }
        path = resource_map.get(uri)
        if path and os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read()
        else:
            content = f"# Resource not found on disk\nuri: {uri}\nstatus: missing\n"
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "contents": [
                    {
                        "uri": uri,
                        "mimeType": "text/yaml",
                        "text": content
                    }
                ]
            }
        }
    elif method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "prompts": PROMPTS_SCHEMA
            }
        }
    elif method == "prompts/get":
        prompt_name = params.get("name")
        p_args = params.get("arguments", {})
        if prompt_name == "drug_target_analysis":
            disease = p_args.get("disease", "Unknown Disease")
            target = p_args.get("target_gene", "Unknown Target")
            prompt_text = (
                f"Research-use target scan for '{target}' in '{disease}'.\n"
                f"1. If hosted Open Targets/ChEMBL/UniProt/ClinicalTrials tools are connected, query them.\n"
                f"2. Record each score with its source. Do not invent missing values.\n"
                f"3. Do not emit a Bayesian go/no-go unless the user supplied calibrated scores."
            )
        elif prompt_name == "variant_pathogenicity":
            variant = p_args.get("variant", "Unknown Variant")
            disease = p_args.get("disease", "Unknown Condition")
            prompt_text = (
                f"Research-use ACMG combination for '{variant}' ({disease}).\n"
                f"You are not a clinical laboratory and not board-certified.\n"
                f"1. Parse the variant string.\n"
                f"2. Query gnomAD/ClinVar only if those tools are connected; otherwise leave AF unknown.\n"
                f"3. Do not apply PM2, PP3, or PVS1 unless the corresponding evidence field is present.\n"
                f"4. Pass only supplied codes into evaluate_variant_acmg. Research-use only."
            )
        else:
            prompt_text = f"Expert bioinformatics prompt for {prompt_name}."

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
                            "text": prompt_text
                        }
                    }
                ]
            }
        }
    elif method == "tools/call":
        tool_name = params.get("name")
        args = params.get("arguments", {})
        try:
            # Core 8 Tools
            if tool_name == "search_pubmed":
                res = await tool_search_pubmed(
                    args.get("query", ""),
                    args.get("max_results", 5),
                    args.get("offset", 0),
                    args.get("sort", "pub_date"),
                    args.get("mindate"),
                    args.get("maxdate")
                )
            elif tool_name == "get_pubmed_article":
                res = await tool_get_pubmed_article(args.get("pmid", ""))
            elif tool_name == "search_biorxiv":
                res = await tool_search_biorxiv(
                    args.get("query", ""),
                    args.get("server", "biorxiv"),
                    args.get("limit", 5),
                    args.get("page", 1)
                )
            elif tool_name == "search_chembl":
                res = await tool_search_chembl(
                    args.get("query", ""),
                    args.get("entity_type", "molecule"),
                    args.get("limit", 5),
                    args.get("offset", 0)
                )
            elif tool_name == "search_opentargets":
                res = await tool_search_opentargets(
                    args.get("query", ""),
                    args.get("entity_types"),
                    args.get("limit", 5),
                    args.get("page_index", 0)
                )
            elif tool_name == "search_clinical_trials":
                res = await tool_search_clinical_trials(
                    args.get("condition", ""),
                    args.get("intervention", ""),
                    args.get("status"),
                    args.get("limit", 5),
                    args.get("page_token")
                )
            elif tool_name == "search_uniprot":
                res = await tool_search_uniprot(
                    args.get("query", ""),
                    args.get("organism", "human"),
                    args.get("limit", 5)
                )
            elif tool_name == "search_ensembl":
                res = await tool_search_ensembl(
                    args.get("symbol", ""),
                    args.get("species", "human")
                )
            # Phase 4 Extended 8 Tools
            elif tool_name == "search_gnomad":
                res = await tool_search_gnomad(
                    args.get("gene_symbol"),
                    args.get("variant_id")
                )
            elif tool_name == "search_pdb":
                res = await tool_search_pdb(
                    args.get("query", ""),
                    args.get("limit", 5)
                )
            elif tool_name == "search_alphafold":
                res = await tool_search_alphafold(
                    args.get("uniprot_id", "")
                )
            elif tool_name == "search_reactome":
                res = await tool_search_reactome(
                    args.get("query", ""),
                    args.get("species", "Homo sapiens"),
                    args.get("limit", 5)
                )
            elif tool_name == "search_string":
                res = await tool_search_string(
                    args.get("gene_symbol", ""),
                    args.get("species", 9606),
                    args.get("limit", 10),
                    args.get("required_score", 400)
                )
            elif tool_name == "search_cosmic":
                res = await tool_search_cosmic(
                    args.get("gene_symbol", "")
                )
            elif tool_name == "search_geo":
                res = await tool_search_geo(
                    args.get("query", ""),
                    args.get("max_results", 5)
                )
            elif tool_name == "get_gene_expression":
                res = await tool_get_gene_expression(
                    args.get("gene_symbol", ""),
                    args.get("tissue_site")
                )
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
            logger.error(f"Error executing {tool_name}: {e}", exc_info=True)
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


# --- Async Stdio Main Loop ---

async def async_stdio_reader():
    """Asynchronous stdin reader supporting standard input lines."""
    loop = asyncio.get_running_loop()
    
    while True:
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            asyncio.create_task(process_single_rpc(req))
        except Exception as e:
            logger.error(f"JSON-RPC parse error: {e}")
            err_resp = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {str(e)}"
                }
            }
            write_json_response(err_resp)


def write_json_response(resp: Dict[str, Any]):
    """Safely serialize and write JSON response to standard output."""
    output = json.dumps(resp, ensure_ascii=False) + "\n"
    sys.stdout.write(output)
    sys.stdout.flush()


async def process_single_rpc(req: Dict[str, Any]):
    """Process a single JSON-RPC request and emit the response."""
    try:
        resp = await handle_rpc_request_async(req)
        if resp is not None:
            write_json_response(resp)
    except Exception as e:
        logger.error(f"Unexpected error processing RPC request: {e}")
        if "id" in req:
            write_json_response({
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "error": {
                    "code": -32603,
                    "message": f"Internal RPC error: {str(e)}"
                }
            })


def main():
    """Main process entry point."""
    logger.info("BioNexus Local MCP Server v2.0.0 starting...")
    try:
        asyncio.run(async_stdio_reader())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Server shutting down.")
    except Exception as e:
        logger.critical(f"Fatal server crash: {e}", exc_info=True)


if __name__ == "__main__":
    main()
