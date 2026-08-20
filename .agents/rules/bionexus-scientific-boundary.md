# BioNexus scientific boundary

BioNexus is a reliability plugin and warrant layer inside this host. It is not
an independent platform, not a biological Agent, and not an autonomous cell
type annotator.

- Keep single-cell clusters numeric. Marker genes may support explicitly
  putative candidates, but never silently become definitive cell identities.
- Do not infer condition-level or causal differential expression from cells as
  replicates or from `rank_genes_groups`; require biological-replicate-aware
  pseudobulk evidence.
- Missing prerequisites, provenance, tools, or evidence must produce a bounded
  refusal, `NEEDS_DATA`, or a clearly degraded advisory. Never invent or
  silently substitute evidence.
- BioNexus provenance and SHA-256 outputs support reproducibility only. They do
  not establish CLIA/CAP, FDA 21 CFR Part 11, clinical, or regulatory validity.
- `bionexus_host_probe` records technical MCP integration evidence only. It is
  not biological validation, clinical validation, or cryptographic attestation.
- Never edit `cross-host/antigravity/REQUEST.json` or
  `cross-host/antigravity/mcp-audit.jsonl` during acceptance. Write host output
  only to `cross-host/antigravity/RUN.json`.
