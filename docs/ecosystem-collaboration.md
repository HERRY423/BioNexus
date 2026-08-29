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
