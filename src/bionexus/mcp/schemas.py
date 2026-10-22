"""
Tool, Resource, and Prompt schemas and adapter definitions for BioNexus MCP.
"""

from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Dict, List, Optional

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

_HOSTED_FALLBACK_TOOLS = {
    "search_pubmed",
    "get_pubmed_article",
    "search_biorxiv",
    "search_chembl",
    "search_opentargets",
    "search_clinical_trials",
}

TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "name": "search_pubmed",
        "description": "Search PubMed database for biomedical literature via NCBI E-utilities API with pagination and date filtering.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords, gene symbols, disease names, or MeSH terms (e.g. 'KRAS G12D inhibitor', 'scRNA-seq batch correction').",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum articles to return (1-50, default 5).",
                    "default": 5,
                },
                "offset": {
                    "type": "integer",
                    "description": "Pagination offset / starting index (default: 0).",
                    "default": 0,
                },
                "sort": {
                    "type": "string",
                    "enum": ["pub_date", "relevance"],
                    "description": "Sort order ('pub_date' or 'relevance'). Default is 'pub_date'.",
                    "default": "pub_date",
                },
                "mindate": {
                    "type": "string",
                    "description": "Earliest publication date (YYYY/MM/DD or YYYY, optional).",
                },
                "maxdate": {"type": "string", "description": "Latest publication date (YYYY/MM/DD or YYYY, optional)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_pubmed_article",
        "description": "Fetch complete abstract, author affiliations, MeSH terms, and citation metadata for a specific PubMed PMID.",
        "inputSchema": {
            "type": "object",
            "properties": {"pmid": {"type": "string", "description": "PubMed Identifier (PMID, e.g. '37123456')."}},
            "required": ["pmid"],
        },
    },
    {
        "name": "search_biorxiv",
        "description": "Search life science preprints on bioRxiv or medRxiv via Europe PMC API with pagination.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Preprint search keywords or topics."},
                "server": {
                    "type": "string",
                    "enum": ["biorxiv", "medrxiv"],
                    "description": "Preprint server ('biorxiv' or 'medrxiv'). Default is 'biorxiv'.",
                    "default": "biorxiv",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum preprints to return (1-50, default 5).",
                    "default": 5,
                },
                "page": {"type": "integer", "description": "Page number (default 1).", "default": 1},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_chembl",
        "description": "Query ChEMBL database for bioactive molecules, targets, or bioactivity assays with molecular properties and structures.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Molecule name, SMILES string, or target name (e.g. 'Aspirin', 'EGFR', 'Gefitinib').",
                },
                "entity_type": {
                    "type": "string",
                    "enum": ["molecule", "target", "assay"],
                    "description": "Entity category to query ('molecule', 'target', or 'assay'). Default is 'molecule'.",
                    "default": "molecule",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum records to return (1-50, default 5).",
                    "default": 5,
                },
                "offset": {"type": "integer", "description": "Pagination offset (default 0).", "default": 0},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_opentargets",
        "description": "Query Open Targets Platform GraphQL API for disease-target associations, tractability, and drug mechanisms.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Disease name, gene target, or drug (e.g. 'lung adenocarcinoma', 'BRAF', 'Imatinib').",
                },
                "entity_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Entity types to include ('target', 'disease', 'drug'). Default is all.",
                    "default": ["target", "disease", "drug"],
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (1-50, default 5).",
                    "default": 5,
                },
                "page_index": {"type": "integer", "description": "Page index (default 0).", "default": 0},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_clinical_trials",
        "description": "Query ClinicalTrials.gov API v2 for active or completed clinical trials, interventions, study phases, and protocols.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "condition": {
                    "type": "string",
                    "description": "Disease or medical condition (e.g. 'Melanoma', 'Triple Negative Breast Cancer').",
                },
                "intervention": {
                    "type": "string",
                    "description": "Optional drug or therapy intervention (e.g. 'Pembrolizumab').",
                    "default": "",
                },
                "status": {
                    "type": "string",
                    "description": "Recruitment status filter (e.g. 'RECRUITING', 'COMPLETED', 'ACTIVE_NOT_RECRUITING').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum trials to return (1-50, default 5).",
                    "default": 5,
                },
                "page_token": {"type": "string", "description": "Next page token for cursor pagination."},
            },
            "required": ["condition"],
        },
    },
    {
        "name": "search_uniprot",
        "description": "Query UniProtKB for curated protein details, sequence length, biological function, and gene associations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Protein name, gene symbol, or accession ID (e.g. 'TP53', 'P04637', 'EGFR').",
                },
                "organism": {
                    "type": "string",
                    "description": "Organism filter ('human', 'mouse', or scientific name). Default is 'human'.",
                    "default": "human",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum proteins to return (1-50, default 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_ensembl",
        "description": "Query Ensembl REST API for gene genomic coordinates, chromosome, biotype, and canonical transcripts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Gene symbol (e.g. 'BRCA1', 'GAPDH', 'TNF')."},
                "species": {
                    "type": "string",
                    "description": "Species name ('human', 'mouse', 'rat', etc.). Default is 'human'.",
                    "default": "human",
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "search_gnomad",
        "description": "Query gnomAD API for population allele frequencies, loss-of-function intolerance (pLI, LOEUF), and missense constraint z-scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gene_symbol": {
                    "type": "string",
                    "description": "Gene symbol to query constraint metrics for (e.g. 'BRCA1', 'SCN1A').",
                },
                "variant_id": {
                    "type": "string",
                    "description": "Variant coordinate ID in chr-pos-ref-alt format (e.g. '13-32315508-C-T').",
                },
            },
        },
    },
    {
        "name": "search_pdb",
        "description": "Search RCSB Protein Data Bank (PDB) for experimentally solved 3D structures, resolution, experimental methods, and ligands.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Protein name, PDB ID, macromolecule name, or ligand (e.g. 'CRISPR Cas9', '7K43', 'Kinase').",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum structures to return (1-50, default 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_alphafold",
        "description": "Query AlphaFold Protein Structure Database API for AI predicted 3D structures, pLDDT confidence scores, and CIF/PDB download links.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "uniprot_id": {
                    "type": "string",
                    "description": "UniProt Accession ID (e.g. 'P04637', 'Q9BYF1', 'P38398').",
                }
            },
            "required": ["uniprot_id"],
        },
    },
    {
        "name": "search_reactome",
        "description": "Query Reactome Content Service for biological pathways, reactions, pathway hierarchies, and participating molecules.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Pathway name, gene symbol, or biological process (e.g. 'Apoptosis', 'EGFR signaling', 'Glycolysis').",
                },
                "species": {
                    "type": "string",
                    "description": "Species name (default: 'Homo sapiens').",
                    "default": "Homo sapiens",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum pathways to return (1-50, default 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_string",
        "description": "Query STRING DB API v12 for protein-protein physical and functional interaction networks with confidence scores.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gene_symbol": {
                    "type": "string",
                    "description": "Gene symbol or protein identifier (e.g. 'TP53', 'CDK4', 'MDM2').",
                },
                "species": {
                    "type": "integer",
                    "description": "NCBI taxonomy ID (default 9606 for Homo sapiens).",
                    "default": 9606,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum interaction partners to return (1-50, default 10).",
                    "default": 10,
                },
                "required_score": {
                    "type": "integer",
                    "description": "Minimum interaction confidence score (0-1000, default 400 for medium confidence).",
                    "default": 400,
                },
            },
            "required": ["gene_symbol"],
        },
    },
    {
        "name": "search_cosmic",
        "description": "Ensembl gene lookup plus a tiny local Cancer Gene Census hint. Not the COSMIC API; does not assign CGC tier.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gene_symbol": {"type": "string", "description": "Gene symbol (e.g. 'KRAS', 'PIK3CA', 'PTEN')."}
            },
            "required": ["gene_symbol"],
        },
    },
    {
        "name": "search_geo",
        "description": "Search NCBI Gene Expression Omnibus (GEO) datasets (GSE) and samples (GSM) via E-utilities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Genomics study keywords, disease condition, or cell type (e.g. 'Glioblastoma scRNA-seq', 'Immunotherapy resistance').",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum datasets to return (1-50, default 5).",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_gene_expression",
        "description": "Retrieve tissue-specific RNA expression (median TPM) and eQTLs across 54 human tissues from GTEx Portal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gene_symbol": {"type": "string", "description": "Gene symbol (e.g. 'INS', 'GAPDH', 'HER2')."},
                "tissue_site": {
                    "type": "string",
                    "description": "Optional tissue filter (e.g. 'Liver', 'Brain', 'Lung', 'Pancreas').",
                },
            },
            "required": ["gene_symbol"],
        },
    },
    {
        "name": "bionexus_warrant_check",
        "description": (
            "Pre-execution scientific warrant gate: evaluate a natural-language analysis intent "
            "against BioNexus invariants and evidence rules BEFORE running AI-generated code. "
            "Returns the routing verdict (PERMITTED / PERMITTED_WITH_LIMITS / NEEDS_DATA / ABSTAIN), "
            "matched capability, blocked claims, remedies, and evidence ceiling. "
            "Designed for full-privilege hosts such as Biomni, Claude Code, Codex, and Cursor."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Natural-language analytical intent, e.g. 'Run differential expression "
                        "between condition A and B' or 'Cluster my single-cell dataset'."
                    ),
                },
                "data_metadata": {
                    "type": "object",
                    "description": (
                        "Optional caller-declared dataset premises, not verified facts, "
                        "e.g. {'donors_per_condition': 2, 'conditions': 2, 'has_spatial_coords': false}. "
                        "independent_validation, clinical_ground_truth and regulatory_certification "
                        "remain unauthenticated declarations; omitted values fail closed."
                    ),
                },
                "research_purpose": {
                    "type": "string",
                    "enum": ["exploratory", "screening", "confirmatory", "causal", "clinical"],
                    "description": (
                        "Intended research purpose. Sets the evidence REQUIREMENT, never the "
                        "evidence value. Omitted = inferred from the query."
                    ),
                },
                "lab_policy": {
                    "type": "string",
                    "enum": ["shadow_audit", "discovery_lab", "enforced_lab"],
                    "description": (
                        "Laboratory enforcement profile modulating intervention only "
                        "(default advisory 'discovery_lab'); execution invariants hold under every profile."
                    ),
                },
                "intent_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional hint keywords to bias capability matching.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "bionexus_host_probe",
        "description": (
            "Record a server-side, tamper-evident receipt proving that a named host reached this local MCP server. "
            "This is integration evidence only and never biological or clinical evidence."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "host_name": {"type": "string", "description": "Lowercase host identifier, e.g. antigravity."},
                "host_version": {"type": "string", "description": "Visible host application version."},
                "model": {"type": "string", "description": "Model selected by the host for this run."},
                "session_id": {"type": "string", "description": "Unique acceptance-run session identifier."},
                "challenge": {"type": "string", "description": "Unique 16-256 character challenge for this run."},
                "human_approved": {
                    "type": "boolean",
                    "description": "Whether the researcher explicitly approved this bounded acceptance run.",
                },
            },
            "required": ["host_name", "host_version", "model", "session_id", "challenge", "human_approved"],
        },
    },
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


def public_tools_schema() -> List[Dict[str, Any]]:
    """Default: unique local tools only. Set BIONEXUS_LOCAL_HOSTED_FALLBACKS=1 for all 16."""
    flag = os.environ.get("BIONEXUS_LOCAL_HOSTED_FALLBACKS", "").strip().lower()
    tools = deepcopy([tool for tool in TOOLS_SCHEMA
                      if flag in {"1", "true", "yes"} or tool['name'] not in _DEFAULT_HIDDEN_LOCAL_TOOLS])
    for tool in tools:
        schema = tool['inputSchema']
        schema['additionalProperties'] = False
        # Optional None is part of the SDK's existing public call signature.
        nullable = {'data_metadata', 'research_purpose', 'lab_policy', 'intent_keywords',
                    'gene_symbol', 'variant_id', 'tissue_site', 'mindate', 'maxdate',
                    'entity_types', 'status', 'page_token'}
        for name, prop in schema['properties'].items():
            if name in nullable and name not in schema.get('required', []):
                prop['type'] = [prop['type'], 'null']
                if 'enum' in prop:
                    prop['enum'].append(None)
        tool['outputSchema'] = {'type': 'object', 'properties': {'result': {'type': 'string'}},
                                'required': ['result'], 'additionalProperties': False}
    return tools


# --- MCP Resources & Prompts Specifications (Phase 4F) ---

RESOURCES_SCHEMA = [
    {
        "uri": "bionexus://workflows/drug_target_discovery",
        "name": "Drug Target Discovery Workflow Template",
        "description": "Production YAML DAG for multi-criteria drug target ranking and validation.",
        "mimeType": "text/yaml",
    },
    {
        "uri": "bionexus://workflows/single_cell_atlas",
        "name": "Single Cell Atlas Workflow Template",
        "description": "Production YAML DAG for single-cell preprocessing, VAE training, and clustering.",
        "mimeType": "text/yaml",
    },
    {
        "uri": "bionexus://workflows/variant_interpretation",
        "name": "Variant Interpretation Workflow Template",
        "description": "Production YAML DAG for ACMG/AMP clinical variant interpretation.",
        "mimeType": "text/yaml",
    },
    {
        "uri": "bionexus://configs/acmg_rules",
        "name": "ACMG Classification Rules Configuration",
        "description": "28 ACMG/AMP evidence rules with likelihood ratios and Bayesian priors.",
        "mimeType": "text/yaml",
    },
    {
        "uri": "bionexus://configs/germline_vgenes",
        "name": "Human Germline V-Gene Consensus Configuration",
        "description": "Human immunoglobulin heavy and light chain framework anchors and developability criteria.",
        "mimeType": "text/yaml",
    },
    {
        "uri": "bionexus://configs/docking_params",
        "name": "Molecular Docking Parameters Configuration",
        "description": "AutoDock Vina and DiffDock parameter presets and drug-likeness rules.",
        "mimeType": "text/yaml",
    },
]

PROMPTS_SCHEMA = [
    {
        "name": "drug_target_analysis",
        "description": "Comprehensive drug target identification, tractability, and druggability evaluation prompt.",
        "arguments": [
            {
                "name": "disease",
                "description": "Target disease indication (e.g. 'Non-small cell lung cancer')",
                "required": True,
            },
            {"name": "target_gene", "description": "Candidate target gene symbol (e.g. 'EGFR')", "required": True},
        ],
    },
    {
        "name": "variant_pathogenicity",
        "description": "Clinical genomic variant pathogenicity assessment adhering to ACMG/AMP guidelines.",
        "arguments": [
            {"name": "variant", "description": "Genomic variant in HGVS or chr-pos-ref-alt format", "required": True},
            {"name": "disease", "description": "Associated clinical phenotype / condition", "required": True},
        ],
    },
    {
        "name": "antibody_developability_audit",
        "description": "Biophysical developability, CDR-H3 aggregation propensity, and humanness audit prompt for therapeutic antibodies.",
        "arguments": [
            {"name": "antibody_name", "description": "Antibody or clone identifier", "required": True},
            {"name": "target_antigen", "description": "Target antigen symbol", "required": True},
        ],
    },
    {
        "name": "survival_biomarker_screening",
        "description": "Pan-cancer clinical cohort survival analysis, Kaplan-Meier stratification, and Cox HR modeling prompt.",
        "arguments": [
            {"name": "biomarker_gene", "description": "Candidate biomarker gene symbol", "required": True},
            {"name": "cancer_cohort", "description": "Cancer cohort (e.g. 'TCGA-LUAD')", "required": True},
        ],
    },
    {
        "name": "spatial_niche_discovery",
        "description": "Spatial transcriptomics tumor microenvironment niche and ligand-receptor analysis prompt.",
        "arguments": [
            {
                "name": "tissue_type",
                "description": "Tissue sample type (e.g. 'Colorectal tumor slice')",
                "required": True,
            }
        ],
    },
    {
        "name": "single_cell_integration",
        "description": "Multi-batch scRNA-seq integration, VAE hyperparameter tuning, and marker gene analysis prompt.",
        "arguments": [
            {"name": "dataset_summary", "description": "Summary of batches, cell count, and platform", "required": True}
        ],
    },
]


# --- BioNexus Tool Adapters & Dispatch Registry ---

TOOL_ADAPTER_MAP = {
    "search_pubmed": lambda args: tool_search_pubmed(
        args.get("query", ""),
        args.get("max_results", 5),
        args.get("offset", 0),
        args.get("sort", "pub_date"),
        args.get("mindate"),
        args.get("maxdate"),
    ),
    "get_pubmed_article": lambda args: tool_get_pubmed_article(args.get("pmid", "")),
    "search_biorxiv": lambda args: tool_search_biorxiv(
        args.get("query", ""),
        args.get("server", "biorxiv"),
        args.get("limit", 5),
        args.get("page", 1),
    ),
    "search_chembl": lambda args: tool_search_chembl(
        args.get("query", ""),
        args.get("entity_type", "molecule"),
        args.get("limit", 5),
        args.get("offset", 0),
    ),
    "search_opentargets": lambda args: tool_search_opentargets(
        args.get("query", ""),
        args.get("entity_types"),
        args.get("limit", 5),
        args.get("page_index", 0),
    ),
    "search_clinical_trials": lambda args: tool_search_clinical_trials(
        args.get("condition", ""),
        args.get("intervention", ""),
        args.get("status"),
        args.get("limit", 5),
        args.get("page_token"),
    ),
    "search_uniprot": lambda args: tool_search_uniprot(
        args.get("query", ""),
        args.get("organism", "human"),
        args.get("limit", 5),
    ),
    "search_ensembl": lambda args: tool_search_ensembl(
        args.get("symbol", ""),
        args.get("species", "human"),
    ),
    "search_gnomad": lambda args: tool_search_gnomad(
        args.get("gene_symbol"),
        args.get("variant_id"),
    ),
    "search_pdb": lambda args: tool_search_pdb(
        args.get("query", ""),
        args.get("limit", 5),
    ),
    "search_alphafold": lambda args: tool_search_alphafold(
        args.get("uniprot_id", ""),
    ),
    "search_reactome": lambda args: tool_search_reactome(
        args.get("query", ""),
        args.get("species", "Homo sapiens"),
        args.get("limit", 5),
    ),
    "search_string": lambda args: tool_search_string(
        args.get("gene_symbol", ""),
        args.get("species", 9606),
        args.get("limit", 10),
        args.get("required_score", 400),
    ),
    "search_cosmic": lambda args: tool_search_cosmic(
        args.get("gene_symbol", ""),
    ),
    "search_geo": lambda args: tool_search_geo(
        args.get("query", ""),
        args.get("max_results", 5),
    ),
    "get_gene_expression": lambda args: tool_get_gene_expression(
        args.get("gene_symbol", ""),
        args.get("tissue_site"),
    ),
    "bionexus_warrant_check": lambda args: tool_bionexus_warrant_check(
        args.get("query", ""),
        args.get("data_metadata"),
        args.get("research_purpose"),
        args.get("lab_policy"),
        args.get("intent_keywords"),
    ),
    "bionexus_host_probe": lambda args: tool_bionexus_host_probe(
        args.get("host_name", ""),
        args.get("host_version", ""),
        args.get("model", ""),
        args.get("session_id", ""),
        args.get("challenge", ""),
        args.get("human_approved"),
    ),
}


def get_resource_content(uri: str) -> str:
    """Resolve and read local BioNexus resource files."""
    resource_map = {
        "bionexus://workflows/drug_target_discovery": os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "skills",
            "research-workflow-orchestrator",
            "templates",
            "drug_target_discovery.yml",
        ),
        "bionexus://workflows/single_cell_atlas": os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "skills",
            "research-workflow-orchestrator",
            "templates",
            "single_cell_atlas.yml",
        ),
        "bionexus://workflows/variant_interpretation": os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "skills",
            "research-workflow-orchestrator",
            "templates",
            "variant_interpretation.yml",
        ),
        "bionexus://configs/acmg_rules": os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "skills",
            "variant-interpretation",
            "configs",
            "acmg_rules.yml",
        ),
        "bionexus://configs/germline_vgenes": os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "skills",
            "biologics-design",
            "configs",
            "germline_vgenes.yml",
        ),
        "bionexus://configs/docking_params": os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "skills",
            "protein-structure-analysis",
            "configs",
            "docking_params.yml",
        ),
    }
    path = resource_map.get(uri)
    if path and os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read()
    return f"# Resource not found on disk\nuri: {uri}\nstatus: missing\n"


def get_prompt_content(name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
    """Format prompt message template for BioNexus prompt."""
    p_args = arguments or {}
    if name == "drug_target_analysis":
        disease = p_args.get("disease", "Unknown Disease")
        target = p_args.get("target_gene", "Unknown Target")
        return (
            f"Research-use target scan for '{target}' in '{disease}'.\n"
            f"1. If hosted Open Targets/ChEMBL/UniProt/ClinicalTrials tools are connected, query them.\n"
            f"2. Record each score with its source. Do not invent missing values.\n"
            f"3. Do not emit a Bayesian go/no-go unless the user supplied calibrated scores."
        )
    elif name == "variant_pathogenicity":
        variant = p_args.get("variant", "Unknown Variant")
        disease = p_args.get("disease", "Unknown Condition")
        return (
            f"Research-use ACMG combination for '{variant}' ({disease}).\n"
            f"You are not a clinical laboratory and not board-certified.\n"
            f"1. Parse the variant string.\n"
            f"2. Query gnomAD/ClinVar only if those tools are connected; otherwise leave AF unknown.\n"
            f"3. Do not apply PM2, PP3, or PVS1 unless the corresponding evidence field is present.\n"
            f"4. Pass only supplied codes into evaluate_variant_acmg. Research-use only."
        )
    elif name == "antibody_developability_audit":
        ab_name = p_args.get("antibody_name", "Unknown Antibody")
        seq = p_args.get("sequence", "")
        return f"Antibody developability and sequence liability audit for '{ab_name}' (Sequence: {seq})."
    elif name == "survival_biomarker_screening":
        biomarker = p_args.get("biomarker_gene", "Unknown Gene")
        cohort = p_args.get("cancer_cohort", "Unknown Cohort")
        return f"Pan-cancer clinical cohort survival screening for biomarker '{biomarker}' in cohort '{cohort}'."
    elif name == "spatial_niche_discovery":
        tissue = p_args.get("tissue_type", "Unknown Tissue")
        return f"Spatial transcriptomics tumor microenvironment niche and ligand-receptor signaling analysis for '{tissue}'."
    elif name == "single_cell_integration":
        summary = p_args.get("dataset_summary", "Unknown Summary")
        return f"Multi-batch scRNA-seq integration, VAE hyperparameter tuning, and marker gene analysis for dataset: {summary}."
    return f"Expert bioinformatics prompt for {name}."


# --- Official MCP Python SDK Server Factory ---



