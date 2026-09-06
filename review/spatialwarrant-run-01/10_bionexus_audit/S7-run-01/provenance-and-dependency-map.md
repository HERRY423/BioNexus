# Provenance and dependence

```mermaid
graph TD
 W[Wu study] --> R[scRNA reference]
 W --> V[Six Visium sections]
 R --> D[Tangram / NNLS / ingest]
 V --> G[Producer pathology + frozen geometry]
 G --> D
 D --> N[Niches]
 G --> P[CID4535 pseudobulk]
 R --> L[LIANA]
 P --> E[Result-selected external searches]
 L --> E
 N --> T[10x technical transfer]
```

Local Python/scverse execution. Workbench contributes data understanding/design/catalog routing, Literature and Databases supply external query returns, and BioNexus passively audits supplied records. None supplies independent biological replication.
