# BNS-025: External Scientific Capability Receipt & Connector Profile

**Status**: Development / Engineering-only, no certification effect | **Version**: 0.1 | **Supersedes**: none
**Applies to**: `src/bionexus/tool_receipt.py`, `src/bionexus/connector_profile.py`, `src/bionexus/rosalind_adapter.py`, external tool intake, host adapters, and claim assessment.
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose and Epistemic Boundary

External capability connectors (e.g. PubMed, ChEMBL, Owkin, Synthesize Bio, LatchBio, Scispot, BioRender) produce heterogeneous outputs ranging from bibliographic citations and biochemical assays to speculative in-silico designs and visual illustrations.

BioNexus does not select or invoke upstream tools. When an external connector returns a result, BioNexus MUST NOT infer evidence-to-claim relationships, MUST NOT fabricate missing source context, and MUST NOT permit self-declared metadata to self-promote into scientific evidence factors.

- **BNS-CP-001** An intake adapter MUST NOT synthesize default or fallback values for undeclared source context. Missing information MUST be classified as `INCOMPLETE` or `UNKNOWN`.
- **BNS-CP-002** Envelope intake validity (`INTAKE_VALID`), evidence-to-claim support (`EVIDENCE_SUPPORTS_CLAIM`), and scientific warrant (`CLAIM_WARRANTED`) MUST remain strictly separate epistemic states. `INTAKE_VALID` MUST NOT imply `EVIDENCE_SUPPORTS_CLAIM` or `CLAIM_WARRANTED`.
- **BNS-CP-003** External capability outputs MUST be classified across two decoupled, orthogonal dimensions: `ScientificDomain` × `EvidenceProductionMode`.

## 2. Three-Level Receipt Hierarchy

Tool execution receipts provide tamper-evident cryptographic bindings. A self-consistent hash binding checks content consistency; a caller can modify and rehash a receipt. Without an externally retained expected digest or trusted signature, it does not establish historical immutability, provider identity, backend fidelity, or scientific validity.

- **BNS-CR-001** Receipts MUST declare an explicit tier in the three-level hierarchy:
  - **Level 0 (Content Integrity)**: Binds request SHA-256, response SHA-256, timestamp, and declared tool name. Checks self-consistent content binding only; does not prove execution or historical immutability.
  - **Level 1 (Host-Observed Execution)**: Recorded by an independent host observer (e.g. Claude, Codex, ChatGPT, Rosalind, BCTK). Binds host identity, connector ID, tool schema digest, transport, session ID, and execution digests. Establishes observation only after the host observer is independently authenticated and the execution binding is verified.
  - **Level 2 (Provider / Independent Attested)**: Binds a verifiable provider cryptographic signature or independent verification attestation (BNS-023 / BNS-024). Establishes the scoped attestation only after signature, trust anchor and execution binding verification.
- **BNS-CR-002** Level 0 receipts MUST NOT certify `backend_fidelity`, `provenance`, or scientific evidence factors.
- **BNS-CR-003** Level 1 receipts MAY certify execution `provenance`, but MUST NOT certify `backend_fidelity` or `external_validation` without Level 2 attestation.
- **BNS-CR-004** Unsigned or un-attested metadata attributes (such as `external_validation=True` or `regulatory_certification=True`) MUST NOT be promoted into verified evidence factors.
- **BNS-CR-005** Only Level 2 attested receipts or verified independent verification network records MAY certify `backend_fidelity` and attested empirical factors.

## 3. Universal Connector Profile Taxonomy

- **BNS-CP-004** Every external tool connector MUST map to a canonical `ConnectorProfile` defining:
  1. `domain`: literature, chemistry, genomics, functional_genomics, transcriptomics, pathology, clinical, regulatory, lab_record, structure, or communication.
  2. `production_mode`: retrieval, observation, experiment, statistical_analysis, computational_inference, model_prediction, generative_model, workflow_execution, human_annotation, or synthesis.
  3. `scientific_object_type`: descriptive classification of the produced object.
  4. `default_max_claim_maturity`: the highest maturity level the capability may support alone.
  5. `prohibited_claims`: list of scientific assertions forbidden for this capability.
- **BNS-CP-005** Generative communication tools (e.g. BioRender) MUST declare `allows_scientific_evidence=False` and MUST NOT be used to support any scientific claim.
- **BNS-CP-006** In-silico predictive and generative models (e.g. Synthesize Bio, EDEN, Inductive Bio) MUST be capped at `PRELIMINARY` hypothesis generation and MUST NOT claim `in_vivo_efficacy` or `clinical_actionability` without empirical replication.
- **BNS-CP-007** Observational and literature retrieval capabilities (e.g. PubMed, Consensus) MUST NOT claim direct causality or consensus from single queries.
- **BNS-CP-008** Warrant evaluation engines MUST evaluate claim statements and maturities against the connector profile boundaries and fail closed if prohibited inferences are detected.


## 4. Receipt Verification Preconditions

- **BNS-CR-006** A declared tier, `host_context`, `attestation`, role, or inline public key MUST NOT serve as its own trust anchor. Scientific factor promotion MUST require a separately trusted verifier with scope-bound execution verification. A provider signature alone MUST NOT establish independent validation or regulatory certification.
- **BNS-CR-007** Unsupported, malformed or conflicting receipt tiers MUST fail closed. Tier declarations MUST be integers 0, 1 or 2, excluding booleans.

**Current implementation status:** `tool_receipt.py` checks content bindings only.
It has no trusted observer/provider signature verifier. Level 1/2 declarations emit
`ATTESTATION_NOT_VERIFIED` and all tiers grant zero scientific evidence factors.
BNS-CR-003/005 describe conditional permission after verification, not implemented
trust capabilities. Receipt logs and evidence-model ingestion retain this boundary.

## 5. Epistemic Lineage and Support Counting

- **BNS-EL-001** Identity equivalence MUST be distinct from derivation. A synthesis referencing several studies MUST preserve multiple source roots; `derived_from`, `aggregates` and `primary_source_ids` MUST NOT merge the studies. Citation alone MUST NOT establish identity or dependence.
- **BNS-EL-002** Missing lineage, unresolved references and cyclic derivation MUST be reported explicitly. Unknown objects, database mirrors and publication status alone MUST NOT create primary studies. An unknown evidence ID MUST NOT enter the strict resolved support set.
- **BNS-EL-003** Support representative selection MUST be deterministic across input permutations and prefer original source evidence over its derived summaries. Shared dataset, assay and model identities MUST constrain support counting without merging study identities. Excluded objects and contradictions MUST remain auditable.
- **BNS-EL-004** Declared source counts MUST NOT be represented as verified scientific independence. The declaration-only graph MUST report `independence_status=NOT_ESTABLISHED`. The legacy `independent_origins` and `effective_independence_ratio` fields describe declared source counts only, not independence probabilities or scientific warrant.
- **BNS-EL-005** Explicit adjudication MAY supply bounded support with unresolved lineage, but MUST preserve an unresolved-lineage warning and MUST NOT be promoted by the graph into independent replication or a final human decision.

Verification hooks: `tests/unit/test_epistemic_lineage.py`,
`tests/unit/test_ecosystem_claim.py`, `tests/unit/test_tool_receipt.py`.
These tests establish local engineering behavior only.
