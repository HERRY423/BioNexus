# BioNexus Community Connector Profile Registry

This directory contains the declarative scientific output contracts for connectors (tools, databases, preprints, literature crawlers, and computational inference engines).

## Purpose

BioNexus Core knows only the protocol. It is deliberately **not** an MCP marketplace or router. Instead of hardcoding vendor endpoints in core code, scientific boundaries are declared as community-maintained contracts:

```text
BioNexus Core
      │
      └── knows only protocol

Connector Profile Registry (standards/connector-profiles/)
      │
      ├── enrichr.yaml       (computational pathway inference)
      ├── pubmed.yaml        (biomedical primary literature)
      ├── biorxiv.yaml       (life sciences preprints)
      ├── consensus.yaml     (AI literature meta-synthesis)
      ├── chembl.yaml        (bioactivity assays & pharmacology)
      ├── opentargets.yaml   (target-disease evidence aggregation)
      ├── owkin.yaml         (computational pathology & biomarker ML)
      └── ...
```

## Contract Anatomy

Each profile specifies:
1. **Identity**: `connector` and `tool` identifier.
2. **Production Mode**: `computational_inference`, `curated_database`, `literature_retrieval`, `experimental_assay`, `deep_learning_prediction`, or `meta_synthesis`.
3. **Required Context**: Context fields that must be present in `source_context` for valid intake.
4. **Default Evidence Role**: `supporting`, `context_only`, etc.
5. **Maximum Default Claim**: Ceiling on the proposition class warranted without independent human review.
6. **Forbidden Claims**: Proposition types that MUST NOT be inferred or claimed solely from this connector output (e.g. `causal_mechanism`, `clinical_actionability`).
7. **Independence Rules**: Principles governing epistemic independence (e.g. preprints and published papers share study identity; AI summaries of a paper are not independent replications).
8. **Semantic Profile**: Canonical BNS-019 attributes (`claim.type`, `evidence.type`, `biological.unit`, `warrant.level`, `warrant.status`).
9. **Epistemic Lineage Mapping**: Field mappings to extract `origin_id`, `origin_type`, `dataset_identity`, and `assay_identity`.
