from __future__ import annotations

import logging
import urllib.parse
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("bionexus.mcp.tools")

def _get_http() -> Callable[..., Awaitable[Any]]:
    import bionexus.mcp_server as _srv
    return _srv.async_http_request

async def tool_search_chembl(
    query: str, entity_type: str = "molecule", limit: int = 5, offset: int = 0
) -> Dict[str, Any]:
    """Query ChEMBL database for bioactive molecules, targets, or assays with pagination."""
    limit = min(max(1, int(limit)), 50)
    offset = max(0, int(offset))
    entity_type = entity_type.lower()

    if entity_type == "target":
        url = f"https://www.ebi.ac.uk/chembl/api/data/target/search.json?q={urllib.parse.quote(query)}&limit={limit}&offset={offset}"
        data = await _get_http()(url)
        targets = []
        for t in data.get("targets", []):
            targets.append(
                {
                    "chembl_id": t.get("target_chembl_id"),
                    "pref_name": t.get("pref_name"),
                    "target_type": t.get("target_type"),
                    "organism": t.get("organism"),
                    "target_components": [c.get("component_type") for c in t.get("target_components", [])],
                }
            )
        total = data.get("page_meta", {}).get("total_count", len(targets))
        return {"query": query, "entity_type": "target", "total_found": total, "offset": offset, "results": targets}

    elif entity_type == "assay":
        url = f"https://www.ebi.ac.uk/chembl/api/data/assay/search.json?q={urllib.parse.quote(query)}&limit={limit}&offset={offset}"
        data = await _get_http()(url)
        assays = []
        for a in data.get("assays", []):
            assays.append(
                {
                    "assay_chembl_id": a.get("assay_chembl_id"),
                    "description": a.get("description"),
                    "assay_type": a.get("assay_type"),
                    "assay_organism": a.get("assay_organism"),
                }
            )
        total = data.get("page_meta", {}).get("total_count", len(assays))
        return {"query": query, "entity_type": "assay", "total_found": total, "offset": offset, "results": assays}

    else:
        url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/search.json?q={urllib.parse.quote(query)}&limit={limit}&offset={offset}"
        data = await _get_http()(url)
        molecules = []
        for m in data.get("molecules", []):
            props = m.get("molecule_properties") or {}
            structures = m.get("molecule_structures") or {}
            molecules.append(
                {
                    "chembl_id": m.get("molecule_chembl_id"),
                    "pref_name": m.get("pref_name"),
                    "max_phase": m.get("max_phase"),
                    "molecule_type": m.get("molecule_type"),
                    "molecular_weight": props.get("full_mwt"),
                    "alogp": props.get("alogp"),
                    "hba": props.get("hba"),
                    "hbd": props.get("hbd"),
                    "psa": props.get("psa"),
                    "canonical_smiles": structures.get("canonical_smiles"),
                }
            )
        total = data.get("page_meta", {}).get("total_count", len(molecules))
        return {"query": query, "entity_type": "molecule", "total_found": total, "offset": offset, "results": molecules}


async def tool_search_opentargets(
    query: str, entity_types: Optional[List[str]] = None, limit: int = 5, page_index: int = 0
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
        "variables": {"queryString": query, "entityNames": entity_types, "size": limit, "index": page_index},
    }
    url = "https://api.platform.opentargets.org/api/v4/graphql"
    data = await _get_http()(url, method="POST", json_data=payload)
    search_res = data.get("data", {}).get("search", {})
    hits = search_res.get("hits", [])
    total = search_res.get("total", len(hits))

    return {
        "query": query,
        "entity_types": entity_types,
        "total_hits": total,
        "page_index": page_index,
        "limit": limit,
        "results": hits,
    }


async def tool_search_clinical_trials(
    condition: str,
    intervention: str = "",
    status: Optional[str] = None,
    limit: int = 5,
    page_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Query ClinicalTrials.gov API v2 with status filter and cursor pagination."""
    limit = min(max(1, int(limit)), 50)
    params = {"query.cond": condition, "pageSize": str(limit)}
    if intervention:
        params["query.intr"] = intervention
    if status:
        params["filter.overallStatus"] = status
    if page_token:
        params["pageToken"] = page_token

    url = f"https://clinicaltrials.gov/api/v2/studies?{urllib.parse.urlencode(params)}"
    data = await _get_http()(url)

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

        studies.append(
            {
                "nct_id": nct_id,
                "title": brief_title,
                "status": overall_status,
                "phases": phases,
                "conditions": cond_list,
                "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
            }
        )

    next_page_token = data.get("nextPageToken")
    total_count = data.get("totalCount", len(studies))

    return {
        "condition": condition,
        "intervention": intervention,
        "total_count": total_count,
        "next_page_token": next_page_token,
        "studies": studies,
    }


