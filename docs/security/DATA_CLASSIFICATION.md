# BioNexus Data Classification & Handling Guidance

This document defines the 4-tier data classification framework for biomedical datasets processed by BioNexus and maps each tier to permitted execution modes, storage requirements, and egress policies.

---

## 1. Data Classification Tiers

```mermaid
graph TD
    Level4[Level 4: RESTRICTED_CLINICAL_PHI\nHIPAA / GDPR Patient Data] -->|Mandatory| Mode4[OFFLINE_STRICT Local Compute Only]
    Level3[Level 3: CONTROLLED_ACCESS_GENOMIC\ndbGaP / EGA Controlled Human Omics] -->|Mandatory| Mode3[OFFLINE_STRICT Local Compute Only]
    Level2[Level 2: PROPRIETARY_UNPUBLISHED\nPre-publication Lab Data / Biotech IP] -->|Default| Mode2[ALLOWLIST (Metadata/Queries Only)]
    Level1[Level 1: PUBLIC_BENCHMARK\n10x Genomics, GEO, SRA, 1000 Genomes] -->|Permitted| Mode1[ALLOWLIST or CONNECTED]
```

---

## 2. Classification Definitions & Requirements

### Level 1: `PUBLIC_BENCHMARK`
- **Definition**: Publicly accessible scientific data (e.g. NCBI GEO, SRA, 10x Genomics public datasets, 1000 Genomes).
- **Permitted Egress Modes**: `ALLOWLIST`, `CONNECTED`, `OFFLINE_STRICT`.
- **Egress Restrictions**: None beyond standard rate limits; queries to public knowledge services (PubMed, UniProt, ChEMBL) permitted.

### Level 2: `PROPRIETARY_UNPUBLISHED`
- **Definition**: Pre-publication laboratory datasets, unpublished CRISPR screens, confidential drug target sequences, proprietary assay results.
- **Permitted Egress Modes**: `ALLOWLIST` (Default), `OFFLINE_STRICT`.
- **Egress Restrictions**:
  - **Prohibited**: Raw expression matrices, count tables, FASTA/FASTQ sequence payloads, candidate molecule structures.
  - **Permitted**: Public database IDs (e.g. PMID, ENSG, UniProt ID), canonical gene symbols (e.g. `TP53`, `EGFR`), literature keyword searches.

### Level 3: `CONTROLLED_ACCESS_GENOMIC`
- **Definition**: Controlled-access human genomic datasets governed by Data Access Agreements (e.g. dbGaP, EGA, UK Biobank individual-level data).
- **Permitted Egress Modes**: `OFFLINE_STRICT` (Mandatory).
- **Egress Restrictions**:
  - **Strictly Prohibited**: Any external network communication or cloud MCP invocation.
  - All analysis must execute within local air-gapped environment or institutionally approved HIPAA/FISMA secure enclave.

### Level 4: `RESTRICTED_CLINICAL_PHI`
- **Definition**: Protected Health Information (PHI) under HIPAA, GDPR Special Category Data, patient clinical records, electronic health record (EHR) extracts.
- **Permitted Egress Modes**: `OFFLINE_STRICT` (Mandatory).
- **Egress Restrictions**:
  - **Strictly Prohibited**: All external network egress.
  - Runtime payload inspection immediately halts execution if PHI fields (e.g. `MRN`, `patient_id`, `SSN`, `DOB`) are detected in any external request.

---

## 3. Configuration & Enforcement

Set the active data classification and egress mode via environment variables or CLI:

```bash
# Set air-gapped mode for clinical / controlled data
export BIONEXUS_EGRESS_MODE=OFFLINE_STRICT

# Inspect active data governance policy
bionexus security egress-policy
```
