# Connectors & Authentication

## How Tool References Work

Plugin files use `~~category` as a placeholder for whatever tool the user connects in that category. For example, `~~literature` might mean PubMed, bioRxiv, or any other literature source with an MCP server.

Plugins are **tool-agnostic** — they describe workflows in terms of categories (literature, clinical trials, chemical database, etc.) rather than specific products. The `mcp.json` pre-configures both a local direct-API fallback server (`local-bio-mcp`) and remote Streamable HTTP servers. Prefer hosted PubMed/ChEMBL/Open Targets/ClinicalTrials/bioRxiv tools when they are connected. Local `tools/list` marks those five as `hosted_fallback`. Use the local server for **unique** tools: UniProt, Ensembl, gnomAD, PDB, AlphaFold DB, Reactome, STRING, GEO, and GTEx. `search_cosmic` is an Ensembl lookup plus a tiny local CGC hint, not the COSMIC API.

---

## Supported MCP Servers & Transports

| Category | Placeholder | Standard Remote Server | Local Fallback (Stdio) | Auth Key (Optional) |
|----------|-------------|------------------------|------------------------|---------------------|
| Literature | `~~literature` | `pubmed`, `biorxiv`, `consensus` | `local-bio-mcp` (`search_pubmed`, `search_biorxiv`) | `NCBI_API_KEY`, `CONSENSUS_API_KEY` |
| Scientific illustration | `~~scientific illustration` | `biorender` | — | `BIORENDER_API_KEY` |
| Clinical trials | `~~clinical trials` | `c-trials` | `local-bio-mcp` (`search_clinical_trials`) | None (Free public API) |
| Chemical database | `~~chemical database` | `chembl` | `local-bio-mcp` (`search_chembl`) | None (Free public API) |
| Drug targets | `~~drug targets` | `ot` (Open Targets) | `local-bio-mcp` (`search_opentargets`) | None (Free public API) |
| Data repository | `~~data repository` | `synapse` | — | `SYNAPSE_AUTH_TOKEN` |
| Journal access | `~~journal access` | `wiley` | — | `WILEY_API_KEY` |
| AI research | `~~AI research` | `owkin` | — | `OWKIN_API_KEY` |
| Lab platform | `~~lab platform` | `benchling` | — | `BENCHLING_API_KEY`, `BENCHLING_TENANT` |

---

## 🔑 Authentication & API Key Configuration

Copy `.env.example` to `.env` to configure your API tokens:

```bash
cp .env.example .env
```

To check your credential configuration status:
```bash
python scripts/auth_helper.py --status
```

### Key Highlights:
1. **Zero-Config Core Access**: PubMed, bioRxiv/medRxiv, ChEMBL, Open Targets, and ClinicalTrials.gov work immediately without any API keys.
2. **NCBI API Key**: Adding `NCBI_API_KEY` raises the PubMed request limit from 3 req/sec to 10 req/sec.
3. **Enterprise LIMS**: Configure `BENCHLING_API_KEY` and `BENCHLING_TENANT` to connect your organization's Benchling workspace.
