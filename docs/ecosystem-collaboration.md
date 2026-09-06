# BioNexus cross-plugin collaboration contract

BioNexus is the passive reliability plane around external scientific
capabilities. The host or researcher chooses and runs Literature, Databases,
NGS, Sequence, Structure, or Slide tools. BioNexus receives their completed
outputs and checks what those outputs can safely support.

```text
host-selected capability
        |
        v
external result + source context
        |
        v
BioNexus intake -> integrity -> explicit adjudication -> context/duplicate audit
                                                -> Claim-Evidence Ledger
        |
        v
Warrant + Audit + EvidenceCard + pending named human decision
```

BioNexus never selects the upstream tool, retries it, schedules work, or acts
as an orchestration platform.

## Envelope contract

Every external result enters through
`bionexus.external-evidence-envelope.v1`. The envelope binds:

- declared producer plugin, capability, tool, and version;
- capability family;
- exact JSON payload SHA-256;
- originating request SHA-256 when available;
- source-specific interpretation context;
- an optional BNS-019 scientific semantic envelope.

The hash detects content changes. It does not authenticate the producer, prove
that the upstream tool ran, or establish independent validation.

## Required context by capability family

| Family | Required interpretation context | Claim boundary |
|---|---|---|
| `literature` | source, stable identifiers, publication status, study design | One search result is not consensus, replication, or causality. |
| `database` | source, record IDs, database release, identifier namespace, taxon | Retrieval is not independent experimental validation. |
| `analysis` | backend/version, input hash, parameter hash, execution-receipt hash | Execution success is not biological generalization. |
| `sequence` | accession/version, sequence hash, coordinate system | Position/conservation alone is not function or pathogenicity. |
| `structure` | structure ID/source/version, residue mapping, model quality | Geometric proximity is not altered affinity or drug resistance. |
| `slide` | image hash, coordinates/transform, segmentation version, replicate/FOV IDs | Visual colocalization is not robust enrichment or mechanism. |

Missing required context yields `INCOMPLETE`; digest or schema failures yield
`INVALID`. Only `VALID` envelopes may enter the ledger, and they enter as
`context_only` with maturity `UNASSESSED`.

## Independent validation is explicit

An evidence node unlocks an external-validation ceiling only when its
`validation_role` is `external_validation` or `reference_ground_truth` and the
qualification contains:

- a supported independence basis (`independent_dataset`, `held_out_cohort`,
  `orthogonal_assay`, or `blinded_external_evaluation`);
- distinct SHA-256 hashes for the target and validation evidence;
- `review_status: approved`;
- a named `reviewer_id` and content-bound `review_receipt_sha256`.

Database and `cross_method` evidence no longer gain this status by type alone.
This prevents a second tool response from being mistaken for independent
scientific validation.

BioNexus nevertheless does not flatten all non-independent support to zero.
Each reviewed ledger edge exposes a descriptive `support_tier`:
`corroboration`, `methodological_triangulation`, `orthogonal_support`,
`independent_replication`, or `external_replication` (`context_only` for
non-claim-bearing material). This tier is review-bound metadata, not an
automatic validation flag or maturity promotion; strict external-validation
qualification above remains unchanged.

## Operational example

```python
from bionexus.ecosystem_intake import (
    ExternalCapabilityFamily,
    ExternalEvidenceEnvelope,
    ExternalProducerIdentity,
    audit_external_evidence,
    external_evidence_to_ledger_ref,
)

envelope = ExternalEvidenceEnvelope.create(
    evidence_id="EXT-UNIPROT-P04637",
    family=ExternalCapabilityFamily.DATABASE,
    producer=ExternalProducerIdentity(
        plugin_id="life-sciences-databases",
        capability="structured_database_lookup",
        tool_name="query_uniprot",
        plugin_version="2026.08",
    ),
    source_context={
        "source_name": "UniProt",
        "record_ids": ["P04637"],
        "database_release": "2026_03",
        "identifier_namespace": "UniProtKB",
        "organism_taxon": "NCBI:9606",
    },
    payload={"accession": "P04637", "gene": "TP53"},
    request={"accession": "P04637"},
)

audit = audit_external_evidence(envelope)
ref = external_evidence_to_ledger_ref(envelope, audit)
assert ref.validation_role == "context_only"
assert ref.maturity == "UNASSESSED"
```

Engineering validation of this contract does not establish scientific
accuracy, independent reproduction, clinical utility, or ecosystem adoption.

## Multi-source claim packet

Valid intake is deliberately not claim support. To connect multiple peer
results to one statement, the host must submit
`bionexus.ecosystem-claim-packet.v1`. BioNexus does not derive these edges from
payload text. Every envelope needs exactly one explicit adjudication:

- `supports` or `contradicts`: requires an assessed maturity, rationale,
  named `adjudicator_id`, and content-bound adjudication receipt;
- `context` or `depends_on`: remains `UNASSESSED` and `context_only`;
- `external_validation` and `reference_ground_truth`: additionally require
  the strict independent-validation qualification listed above.

`claim_context` is an explicit set of scope constraints. If an envelope
declares a different value for any constrained field, the packet is `BLOCKED`
and no claim-bearing edges are emitted. Identical payload hashes are retained
for provenance but count only once. A reviewed contradiction is preserved as
`CONFLICTED`; BioNexus does not average disagreement into consensus.

Run the passive assessment with:

```bash
python skills/external-evidence-audit/scripts/assess_ecosystem_claim.py claim-packet.json --out assessment.json
```

A minimal executable packet looks like this (the example receipt is a fixture,
not a real review attestation):

```json
{
  "schema_version": "bionexus.ecosystem-claim-packet.v1",
  "claim_id": "CLAIM-TP53-ASSOCIATION-1",
  "statement": "TP53 is associated with the DNA damage response.",
  "decision_owner": "researcher:principal-investigator",
  "claim_context": {"organism_taxon": "NCBI:9606"},
  "envelopes": [
    {
      "schema_version": "bionexus.external-evidence-envelope.v1",
      "evidence_id": "EXT-UNIPROT-P04637",
      "family": "database",
      "producer": {
        "plugin_id": "life-sciences-databases",
        "capability": "structured_database_lookup",
        "tool_name": "query_uniprot",
        "plugin_version": "2026.08"
      },
      "captured_at": "2026-08-28T12:00:00+00:00",
      "source_context": {
        "source_name": "UniProt",
        "record_ids": ["P04637"],
        "database_release": "2026_03",
        "identifier_namespace": "UniProtKB",
        "organism_taxon": "NCBI:9606"
      },
      "payload": {"gene": "TP53"},
      "payload_sha256": "bc39fc13cffbfc23a061ab27f667b6a15177d7a8118ccc98c695e2e070b30252",
      "request_sha256": "9ac710719c09ee896f06edf9b08c6bc485e63a9819f4e0175aa7b4c128b1c256"
    }
  ],
  "adjudications": [
    {
      "evidence_id": "EXT-UNIPROT-P04637",
      "relationship": "supports",
      "maturity": "PRELIMINARY",
      "rationale": "Reviewed only for the declared human TP53 association scope.",
      "adjudicator_id": "reviewer:alice",
      "adjudication_receipt_sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
      "validation_role": "supporting",
      "qualification": {}
    }
  ]
}
```

The assessment emits four connected artifacts:

```text
external envelopes + explicit adjudications
                    |
                    v
        +-----------+-----------+
        |           |           |
     Warrant      Audit     EvidenceCard
        |           |           |
        +-----------+-----------+
                    |
                    v
          Claim-Evidence Ledger
                    |
                    v
      PENDING_HUMAN_DECISION
                    |
                    v
     HumanScientificAdjudication
       (named owner + exact snapshot)
```

`PASS` means the packet is internally admissible under this contract. It is
not a truth verdict, producer authentication, scientific replication, or final
acceptance by the named decision owner.

## Human Scientific Adjudication

`bionexus.human_adjudication` is the only final-decision transition in this
workflow. The human record declares one of `ACCEPT_FOR_EXPLORATION`,
`ACCEPT_WITH_LIMITS`, `DEFER_PENDING_EVIDENCE`, or `REJECT`, and binds it to the
complete assessment SHA-256 plus a content digest of the decision record.

BioNexus validates that the frozen owner and claim match, the timestamp and
rationale are present, evidence limits are explicitly acknowledged for an
acceptance, and every contradiction is addressed. A structurally `BLOCKED`
assessment cannot be accepted. The returned adjudication result preserves the
original conclusion maturity and warrant verbatim. Content hashes detect
mutation but do not authenticate the real-world identity or authority of the
signer; host/laboratory identity controls remain responsible for that boundary.

```python
from bionexus import (
    HumanScientificAdjudication,
    HumanScientificDecision,
    adjudicate_ecosystem_claim,
    assessment_sha256,
)

record = HumanScientificAdjudication.create(
    claim_id=assessment.claim_id,
    decision=HumanScientificDecision.ACCEPT_FOR_EXPLORATION.value,
    decision_owner_id=assessment.decision_owner,
    adjudicator_id="scientist:dr-chen",
    decided_at="2026-08-29T10:30:00-07:00",
    rationale="Prioritize this candidate for an independent follow-up assay.",
    intended_use="bounded hypothesis generation",
    assessment_sha256=assessment_sha256(assessment),
    human_attestation=True,
    acknowledges_evidence_limits=True,
    conditions=("Do not use as confirmatory or clinical evidence.",),
)
result = adjudicate_ecosystem_claim(assessment, record)
assert result.final_decision == "ACCEPT_FOR_EXPLORATION"
assert result.preserved_warrant == assessment.warrant
```

## Epistemic Lineage Graph: Preventing Double-Counting in the Connector Era

In the multi-connector ecosystem, different connectors often return distinct payloads that represent the same underlying study. For example:
- PubMed returns a journal publication (PMID:12345).
- Consensus returns an AI summary derived from PMID:12345.
- bioRxiv returns a preprint of the study that became PMID:12345.
- ChEMBL returns a primary biochemical assay result.
- Open Targets returns an evidence string mirroring the ChEMBL assay.

If an agent or evaluator interprets "5 connectors agree" as 5 independent replications, this produces severe **epistemic double counting**.

BioNexus introduces the **Evidence Independence Graph / Epistemic Lineage Graph** (`bionexus.epistemic_lineage`). Each evidence envelope can declare:
- `origin_id`: Canonical stable identifier (e.g., `PMID:12345`, `doi:...`, `CHEMBL:...`).
- `origin_type`: `primary_study`, `preprint`, `database_mirror`, `derived_synthesis`, `meta_analysis`, `computational_model`, or `assay_result`.
- `derived_from`: Identifiers this node was computed or synthesized from.
- `same_study_as`: Equivalence pointers to other manifestations of the same study.
- `aggregates`: Identifiers aggregated into a multi-study synthesis.
- `dataset_identity`: Normalized underlying raw/processed dataset ID (e.g. `GEO:GSE...`).
- `assay_identity`: Normalized wet-lab or biochemical assay ID.
- `primary_source_ids`: Resolved root primary source IDs.

### Declared lineage diagnostics

Identity and derivation are different relationships. `same_study_as`, matching
origin IDs and identical payloads establish declared equivalence. `derived_from`,
`aggregates` and `primary_source_ids` are directed dependencies: a synthesis of two
studies keeps both roots and does not merge the studies. `cites` alone does not
establish dependence. Hosts must supply consistent, namespaced source identifiers;
BioNexus does not discover undocumented aliases or authenticate these declarations.

The EvidenceCard and audit report expose:

- `independent_origins`: legacy field name for the number of resolved **declared
  source origins**, not a verified count of independent replications.
- `primary_studies`: equivalent groups explicitly declared `primary_study` or
  `preprint`; peer review status, database mirrors and unknown origins do not
  create primary studies.
- `lineage_roots`: a list of source roots per evidence object. Multi-source
  syntheses can belong to multiple `study_clusters`.
- `unresolved_evidence_ids`: missing origins, dangling source references and
  cyclic derivations, including cycles that also reach a known source.
- `independence_status`: always `NOT_ESTABLISHED` for this declaration-only graph.
- `effective_independence_ratio`: legacy diagnostic, declared origin count divided
  by object count; it is not a calibrated independence probability or warrant.

Support selection prefers original studies over summaries, regardless of input
order. Shared datasets, assays and model identities also limit support counting
without asserting that the studies themselves are identical. This conservative
selection is deterministic; it does not search for an optimal independent set.
Excluded support remains visible under `depends_on`, and contradictions remain
visible under `contradicted_by`.

A named, receipted adjudication may still establish bounded claim support when
lineage is unresolved. It does not establish independent replication. The graph's
strict `get_independent_support_set()` excludes unresolved and unknown IDs; the
claim ledger explicitly preserves adjudicated unresolved support and emits
`SOURCE_LINEAGE_UNRESOLVED`. Final acceptance remains `PENDING_HUMAN_DECISION`.

### Receipt verification boundary

The receipt module validates self-consistent hash bindings. A receipt can be
edited and rehashed, so the hash by itself authenticates neither a producer nor
execution history. Level 1 host context and Level 2 attestation dictionaries remain
**declarations**. The current module has no trusted observer/provider signature
verification path: every receipt tier supplies zero scientific evidence factors,
including when consumed through a receipt log or `extract_evidence_factors()`.
Level 1/2 emit `ATTESTATION_NOT_VERIFIED`; backend fidelity and external validation
remain `UNASSESSED`. A future verifier needs an external trust anchor, signature
binding to the exact execution and scoped roles before any factor promotion.

Regression coverage: `tests/unit/test_epistemic_lineage.py`,
`tests/unit/test_ecosystem_claim.py`, and `tests/unit/test_tool_receipt.py`.
These are maintainer-authored engineering checks, not external scientific validation.

## BNS-019 as the Scientific Semantic Layer

Modeled after OpenTelemetry Semantic Conventions, BNS-019 describes the meaning of scientific artifacts without executing pipelines:
- Connectors emit standard envelopes:
  `{"claim.type": "associative", "evidence.type": ["computational_result"], "biological.unit": "pathway", "warrant.status": "unassessed"}`
- Connectors do not need to install the full BioNexus suite.
- In Node/TypeScript environments, MCP tools and web platforms import the zero-dependency `@bionexus/scientific-semconv` reference package:
  `import { createObservationEnvelope } from "@bionexus/scientific-semconv"`

## Connector Profile Registry

BioNexus Core knows only the protocol. To prevent BioNexus from sliding into a proprietary MCP marketplace or router, connector behaviors are declared as community-maintained scientific contracts in `standards/connector-profiles/profiles/` (e.g. `enrichr.yaml`, `pubmed.yaml`, `chembl.yaml`).

Each profile specifies:
- `production_mode`: Epistemic origin class (`computational_inference`, `curated_database`, `literature_retrieval`, etc.).
- `required_context`: Mandatory fields for intake integrity.
- `default_evidence_role`: Base role (`supporting`, `context_only`).
- `maximum_default_claim`: Maximum claim level reachable without explicit review.
- `forbidden_claims`: Prohibited inferences (e.g. Enrichr cannot claim `causal_mechanism` or `clinical_actionability`).
- `independence`: Explicit rules defining replication boundaries.
- `semantic_profile`: Canonical BNS-019 attributes.
