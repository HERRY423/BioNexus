# SpatialWarrant S6 checkpoint

- Status: COMPLETED_WITH_PRESERVED_EXTERNAL_QUERY_FAILURES
- Locked plan SHA-256: `854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82`
- Execution route: local Python/scverse; not a registered NGS workflow run.
- Formal S2 path resolved to `03_scrna_reference/S2-run-01`; the user-stated `02_reference/S2-run-01` path was absent and was not substituted with a new dataset.
- CID4535 region eligibility: B1 49 spots/930,131 UMI; B2 94 spots/1,654,362 UMI; B3 145 spots/2,555,030 UMI; core 273 spots/5,002,262 UMI.
- Frozen IFN program coverage: 196/200; missing: MARCHF1, RIGI, TMT1B, WARS1.
- Primary B2 boundary − core: 0.051510939 mean log2(CPM+1). Sensitivities: B1 0.034906652; B3 0.022163777.
- This is one eligible section and is descriptive only. Population CI, population p value, sign test, and patient-level inference were not computed.
- Whole-gene table: complete deterministic absolute-effect ranking; PyDESeq2 `NOT_RUN_INSUFFICIENT_REPLICATION`; p and padj blank.
- LIANA: COMPLETED, 3,584,342 rows, version 1.10.0; boundary cell-type-specific communication `NOT_IDENTIFIABLE`.
- Pathways: Hallmark 2024.1.Hs complete; PROGENy decoupler ULM COMPLETED (14 pathways).
- External evidence: 163/180 successful source calls after source-wrapper and raw-source corrections; 17 true failures retained. Returned context remains UNASSESSED.
- BioNexus: provenance sidecars and six passive envelope audits completed; MCP host probe failed validation once and then timed out before raw-source correction, so no MCP receipt is claimed.
- Peak measured process memory: 9,827,737,600 bytes. Start/end C free: 32,392,167,424/32,322,793,472 bytes. Combined S6 output: 35,028,870 bytes.
- Machine verdict: PENDING. Biological conclusion: PENDING. Human Scientific Adjudication: PENDING.
- S7: NOT_STARTED. Required inputs are both S6 output directories, their SHA256SUMS/output manifests, `S6-result.json`, this checkpoint, the locked plan, S0-S5 checkpoints, and the preregistered claim file.
