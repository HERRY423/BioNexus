from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Awaitable, Callable, Dict, Optional

from bionexus.mcp.client import get_api_key

try:
    from bionexus.local_cache import BioLocalCache
    from bionexus.local_cache import default_local_cache as _cache

    default_local_cache: BioLocalCache | None = _cache
except ImportError:
    default_local_cache = None

logger = logging.getLogger("bionexus.mcp.tools")

def _get_http() -> Callable[..., Awaitable[Any]]:
    import bionexus.mcp_server as _srv
    return _srv.async_http_request

async def tool_search_uniprot(query: str, organism: Optional[str] = "human", limit: int = 5) -> Dict[str, Any]:
    """Query UniProtKB for protein functions, gene names, sequences, and accessions."""
    limit = min(max(1, int(limit)), 50)

    # Check local offline cache first if in offline mode
    if default_local_cache and default_local_cache.is_offline_mode():
        cached_gene = default_local_cache.get_gene(query)
        if cached_gene:
            return {
                "query": query,
                "organism": organism,
                "total_results": 1,
                "source": "BioNexusLocalCache (Offline)",
                "proteins": [
                    {
                        "accession": cached_gene["uniprot_id"],
                        "id": f"{cached_gene['symbol']}_HUMAN",
                        "protein_name": cached_gene["name"],
                        "genes": [cached_gene["symbol"]],
                        "organism": cached_gene["species"],
                        "function": cached_gene["summary"],
                        "url": f"https://www.uniprot.org/uniprotkb/{cached_gene['uniprot_id']}",
                    }
                ],
            }

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
        "fields": "accession,id,gene_names,protein_name,organism_name,length,cc_function",
    }
    url = f"https://rest.uniprot.org/uniprotkb/search?{urllib.parse.urlencode(params)}"
    try:
        data = await _get_http()(url)

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

            results.append(
                {
                    "accession": primary_acc,
                    "id": entry_name,
                    "protein_name": recommended_name,
                    "genes": genes,
                    "organism": organism_name,
                    "sequence_length": entry.get("sequence", {}).get("length"),
                    "function": " ".join(functions)[:500],
                    "url": f"https://www.uniprot.org/uniprotkb/{primary_acc}",
                }
            )

        return {"query": query, "organism": organism, "total_results": len(results), "proteins": results}
    except Exception as e:
        logger.warning(f"UniProt network request failed for {query}: {e}. Trying local cache...")
        if default_local_cache:
            cached_gene = default_local_cache.get_gene(query)
            if cached_gene:
                return {
                    "query": query,
                    "organism": organism,
                    "total_results": 1,
                    "source": "BioNexusLocalCache (Fallback)",
                    "proteins": [
                        {
                            "accession": cached_gene["uniprot_id"],
                            "id": f"{cached_gene['symbol']}_HUMAN",
                            "protein_name": cached_gene["name"],
                            "genes": [cached_gene["symbol"]],
                            "organism": cached_gene["species"],
                            "function": cached_gene["summary"],
                            "url": f"https://www.uniprot.org/uniprotkb/{cached_gene['uniprot_id']}",
                        }
                    ],
                }
        return {"query": query, "organism": organism, "error": str(e)}


async def tool_search_ensembl(symbol: str, species: str = "human") -> Dict[str, Any]:
    """Query Ensembl REST API for gene metadata, coordinates, biotype, and transcript structures."""
    species = "homo_sapiens" if species.lower() in ("human", "homo_sapiens") else species

    # Check local offline cache first if in offline mode
    if default_local_cache and default_local_cache.is_offline_mode():
        cached_gene = default_local_cache.get_gene(symbol)
        if cached_gene:
            return {
                "symbol": symbol,
                "species": species,
                "ensembl_id": cached_gene["ensembl_id"],
                "biotype": "protein_coding",
                "description": cached_gene["summary"],
                "chromosome": cached_gene["chromosome"],
                "transcripts": [],
                "source": "BioNexusLocalCache (Offline)",
            }

    url = f"https://rest.ensembl.org/lookup/symbol/{species}/{symbol}?expand=1"
    headers = {"Content-Type": "application/json"}
    try:
        data = await _get_http()(url, headers=headers)
        transcripts = []
        for t in data.get("Transcript", [])[:10]:
            transcripts.append(
                {
                    "id": t.get("id"),
                    "biotype": t.get("biotype"),
                    "is_canonical": bool(t.get("is_canonical")),
                    "length": t.get("length"),
                }
            )
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
            "transcripts": transcripts,
        }
    except Exception as e:
        logger.warning(f"Ensembl lookup failed for {symbol}: {e}. Trying local cache...")
        if default_local_cache:
            cached_gene = default_local_cache.get_gene(symbol)
            if cached_gene:
                return {
                    "symbol": symbol,
                    "species": species,
                    "ensembl_id": cached_gene["ensembl_id"],
                    "biotype": "protein_coding",
                    "description": cached_gene["summary"],
                    "chromosome": cached_gene["chromosome"],
                    "transcripts": [],
                    "source": "BioNexusLocalCache (Fallback)",
                }
        return {"symbol": symbol, "error": str(e)}


# --- Tool Implementations (Phase 4 Extended 8 Tools) ---


async def tool_search_gnomad(gene_symbol: Optional[str] = None, variant_id: Optional[str] = None) -> Dict[str, Any]:
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
            data = await _get_http()(url, method="POST", json_data=payload)
            gene_info = data.get("data", {}).get("gene", {})
            return {
                "query_type": "gene_constraint",
                "symbol": gene_symbol,
                "gene_id": gene_info.get("gene_id"),
                "name": gene_info.get("name"),
                "constraint": gene_info.get("gnomad_constraint", {}),
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
            data = await _get_http()(url, method="POST", json_data=payload)
            var_info = data.get("data", {}).get("variant", {})
            return {"query_type": "variant_frequency", "variant_id": variant_id, "variant": var_info}
        except Exception as e:
            logger.error(f"gnomAD variant frequency query failed for {variant_id}: {e}")
            return {"variant_id": variant_id, "error": str(e)}
    else:
        return {"error": "Must provide either gene_symbol or variant_id"}


async def tool_search_pdb(query: str, limit: int = 5) -> Dict[str, Any]:
    """
    Search RCSB Protein Data Bank (PDB) for experimentally solved 3D structures,
    experimental method, resolution, and bound ligands.
    """
    limit = min(max(1, int(limit)), 50)

    # Check local offline cache first if in offline mode
    if default_local_cache and default_local_cache.is_offline_mode():
        pdb = default_local_cache.get_pdb_summary(query)
        if pdb:
            return {
                "query": query,
                "total_found": 1,
                "limit": limit,
                "source": "BioNexusLocalCache (Offline)",
                "structures": [
                    {
                        "pdb_id": pdb["pdb_id"],
                        "title": pdb["title"],
                        "resolution_angstrom": pdb["resolution"],
                        "pdb_url": f"https://www.rcsb.org/structure/{pdb['pdb_id']}",
                    }
                ],
            }

    search_url = "https://search.rcsb.org/rcsbsearch/v2/query"
    search_payload = {
        "query": {"type": "terminal", "service": "full_text", "parameters": {"value": query}},
        "return_type": "entry",
        "request_options": {"paginate": {"start": 0, "rows": limit}},
    }
    try:
        search_data = await _get_http()(search_url, method="POST", json_data=search_payload)
        result_set = search_data.get("result_set", [])
        total_count = search_data.get("total_count", len(result_set))

        entries = []
        for item in result_set:
            pdb_id = item.get("identifier")
            score = item.get("score")
            detail_url = f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}"
            try:
                detail_data = await _get_http()(detail_url)
                struct = detail_data.get("struct", {})
                title = struct.get("title", "")
                exptl = detail_data.get("exptl", [{}])[0]
                method = exptl.get("method", "Unknown")
                rcsb_entry = detail_data.get("rcsb_entry_info", {})
                resolution = rcsb_entry.get("resolution_combined", [None])[0]
                release_date = detail_data.get("rcsb_accession_info", {}).get("initial_release_date", "")

                entries.append(
                    {
                        "pdb_id": pdb_id,
                        "title": title,
                        "method": method,
                        "resolution_angstrom": resolution,
                        "release_date": release_date,
                        "relevance_score": score,
                        "pdb_url": f"https://www.rcsb.org/structure/{pdb_id}",
                        "cif_download_url": f"https://files.rcsb.org/download/{pdb_id}.cif",
                    }
                )
            except Exception:
                entries.append(
                    {"pdb_id": pdb_id, "relevance_score": score, "pdb_url": f"https://www.rcsb.org/structure/{pdb_id}"}
                )

        return {"query": query, "total_found": total_count, "limit": limit, "structures": entries}
    except Exception as e:
        logger.warning(f"PDB search network failed for {query}: {e}. Trying local cache...")
        if default_local_cache:
            pdb = default_local_cache.get_pdb_summary(query)
            if pdb:
                return {
                    "query": query,
                    "total_found": 1,
                    "limit": limit,
                    "source": "BioNexusLocalCache (Fallback)",
                    "structures": [
                        {
                            "pdb_id": pdb["pdb_id"],
                            "title": pdb["title"],
                            "resolution_angstrom": pdb["resolution"],
                            "pdb_url": f"https://www.rcsb.org/structure/{pdb['pdb_id']}",
                        }
                    ],
                }
        return {"query": query, "error": str(e)}


async def tool_search_alphafold(uniprot_id: str) -> Dict[str, Any]:
    """
    Query AlphaFold Protein Structure Database API for predicted 3D structures,
    per-residue pLDDT confidence metrics, and download links.
    """
    uniprot_id = uniprot_id.strip().upper()
    url = f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id}"
    try:
        data = await _get_http()(url)
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
            "model_created_date": entry.get("modelCreatedDate"),
        }
    except Exception as e:
        logger.error(f"AlphaFold lookup failed for {uniprot_id}: {e}")
        return {"uniprot_id": uniprot_id, "error": str(e)}


async def tool_search_reactome(query: str, species: str = "Homo sapiens", limit: int = 5) -> Dict[str, Any]:
    """
    Query Reactome Content Service for biological pathways, reactions,
    pathway hierarchies, and participating molecules.
    """
    limit = min(max(1, int(limit)), 50)

    # Check local offline cache first if in offline mode
    if default_local_cache and default_local_cache.is_offline_mode():
        pathways = default_local_cache.get_pathways_for_gene(query)
        return {
            "query": query,
            "species": species,
            "total_found": len(pathways),
            "pathways": pathways[:limit],
            "source": "BioNexusLocalCache (Offline)",
        }

    params = {"query": query, "species": species, "types": "Pathway", "rows": str(limit)}
    url = f"https://reactome.org/ContentService/search/query?{urllib.parse.urlencode(params)}"
    try:
        data = await _get_http()(url)
        results = data.get("results", [])
        pathways = []
        for r in results:
            entries = r.get("entries", [])
            for e in entries[:limit]:
                pathways.append(
                    {
                        "stId": e.get("stId"),
                        "name": e.get("name"),
                        "species": e.get("species", [species])[0]
                        if isinstance(e.get("species"), list)
                        else e.get("species"),
                        "type": e.get("exactType"),
                        "url": f"https://reactome.org/PathwayBrowser/#/{e.get('stId')}",
                    }
                )
        return {"query": query, "species": species, "total_found": len(pathways), "pathways": pathways[:limit]}
    except Exception as e:
        logger.warning(f"Reactome search network failed for {query}: {e}. Trying local cache...")
        if default_local_cache:
            pathways = default_local_cache.get_pathways_for_gene(query)
            if pathways:
                return {
                    "query": query,
                    "species": species,
                    "total_found": len(pathways),
                    "pathways": pathways[:limit],
                    "source": "BioNexusLocalCache (Fallback)",
                }
        return {"query": query, "error": str(e)}


async def tool_search_string(
    gene_symbol: str, species: int = 9606, limit: int = 10, required_score: int = 400
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
        "caller_identity": "bionexus_plugin",
    }
    url = f"https://string-db.org/api/json/interaction_partners?{urllib.parse.urlencode(params)}"
    try:
        data = await _get_http()(url)
        interactions = []
        if isinstance(data, list):
            for row in data:
                interactions.append(
                    {
                        "preferred_name_a": row.get("preferredName_A"),
                        "preferred_name_b": row.get("preferredName_B"),
                        "combined_score": row.get("score"),
                        "experimental_score": row.get("escore"),
                        "database_score": row.get("dscore"),
                        "coexpression_score": row.get("ascore"),
                        "textmining_score": row.get("tscore"),
                    }
                )
        return {
            "gene_symbol": gene_symbol,
            "species": species,
            "interaction_count": len(interactions),
            "interactions": interactions[:limit],
        }
    except Exception as e:
        logger.error(f"STRING search failed for {gene_symbol}: {e}")
        return {"gene_symbol": gene_symbol, "error": str(e)}


# Small well-known CGC subset for local hints only. Not the COSMIC API.
_LOCAL_CGC_HINTS = {
    "TP53",
    "KRAS",
    "BRAF",
    "EGFR",
    "PIK3CA",
    "PTEN",
    "BRCA1",
    "BRCA2",
    "MYC",
    "ALK",
    "ABL1",
    "BCR",
    "APC",
    "RB1",
    "VHL",
    "NF1",
    "IDH1",
}


async def tool_search_cosmic(gene_symbol: str) -> Dict[str, Any]:
    """Ensembl lookup plus a local CGC hint. This is not the COSMIC REST API."""
    gene = gene_symbol.strip().upper()
    url = f"https://rest.ensembl.org/lookup/symbol/homo_sapiens/{gene}?expand=1"
    try:
        ens_data = await _get_http()(url, headers={"Content-Type": "application/json"})
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


async def tool_search_geo(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search NCBI Gene Expression Omnibus (GEO) datasets (GSE) and samples (GSM) via E-utilities.
    """
    max_results = min(max(1, int(max_results)), 50)
    api_key = get_api_key("NCBI_API_KEY")
    term = f"{query} AND gds[Entry Type]"
    params = {"db": "gds", "term": term, "retmode": "json", "retmax": str(max_results)}
    if api_key:
        params["api_key"] = api_key

    search_url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?{urllib.parse.urlencode(params)}"
    try:
        search_data = await _get_http()(search_url)
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        total_found = int(search_data.get("esearchresult", {}).get("count", 0))

        if not id_list:
            return {"query": query, "total_found": total_found, "datasets": []}

        summary_params = {"db": "gds", "id": ",".join(id_list), "retmode": "json"}
        if api_key:
            summary_params["api_key"] = api_key

        summary_url = (
            f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?{urllib.parse.urlencode(summary_params)}"
        )
        summary_data = await _get_http()(summary_url)
        results = summary_data.get("result", {})

        datasets = []
        for gds_id in id_list:
            info = results.get(gds_id, {})
            accession = info.get("accession", f"GDS{gds_id}")
            title = info.get("title", "")
            summary = info.get("summary", "")
            taxon = info.get("taxon", "")
            n_samples = info.get("nsamples", 0)

            datasets.append(
                {
                    "accession": accession,
                    "title": title,
                    "organism": taxon,
                    "sample_count": n_samples,
                    "summary": summary[:300] + ("..." if len(summary) > 300 else ""),
                    "url": f"https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={accession}",
                }
            )

        return {"query": query, "total_found": total_found, "returned": len(datasets), "datasets": datasets}
    except Exception as e:
        logger.error(f"GEO search failed for {query}: {e}")
        return {"query": query, "error": str(e)}


async def tool_get_gene_expression(gene_symbol: str, tissue_site: Optional[str] = None) -> Dict[str, Any]:
    """
    Retrieve tissue-specific RNA expression (median TPM) and eQTL associations across
    54 non-diseased human tissues from GTEx Portal.
    """
    symbol = gene_symbol.strip().upper()
    url = f"https://gtexportal.org/api/v2/expression/medianGeneExpression?geneId={symbol}&pageSize=100"
    try:
        data = await _get_http()(url)
        records = data.get("data", [])
        expression_profiles = []
        for rec in records:
            tissue = rec.get("tissueSiteDetailId") or rec.get("tissue")
            median_tpm = rec.get("median")
            unit = rec.get("unit", "TPM")
            if tissue_site and tissue_site.lower() not in str(tissue).lower():
                continue
            expression_profiles.append({"tissue": tissue, "median_tpm": median_tpm, "unit": unit})

        expression_profiles.sort(key=lambda x: x["median_tpm"] or 0, reverse=True)

        return {
            "gene_symbol": symbol,
            "filtered_tissue": tissue_site,
            "tissue_count": len(expression_profiles),
            "expression": expression_profiles[:20],
            "gtex_url": f"https://gtexportal.org/home/gene/{symbol}",
        }
    except Exception as e:
        logger.error(f"GTEx expression query failed for {gene_symbol}: {e}")
        return {"gene_symbol": symbol, "error": str(e)}


