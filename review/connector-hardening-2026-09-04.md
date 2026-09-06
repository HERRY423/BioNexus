# Connector evidence boundary hardening — 2026-09-04

## Scope and starting state

This continuation read all three turns of the referenced conversation
`6a99418c-e8d8-83ea-a64a-0b0174b3d27a` and inspected the current local implementation.
The starting HEAD was `cfb0691`; the working tree already contained substantial
uncommitted work, including BNS-025, connector profiles, receipt tiers and a lineage
graph. Those features are prior work, not newly delivered by this continuation.

The architectural direction is retained: the host chooses and runs external tools;
BioNexus passively checks supplied results, preserves uncertainty and produces
bounded evidence records. Human Scientific Adjudication remains the final decision
boundary. No external services were invoked, and no publication was performed.

## Findings resolved

| Finding in the starting working tree | Resulting behavior |
|---|---|
| Missing lineage and orphan summaries/mirrors were counted as independent primary studies. | Unknown and unresolved lineage is exposed; only explicitly declared primary-study/preprint equivalence groups count as declared primary studies. Independence remains `NOT_ESTABLISHED`. |
| `derived_from` unioned different studies; `aggregates` was ignored. | Identity equivalence and directed derivation are separate. A two-study synthesis retains two roots. |
| The first supporting object could displace its original source. | Deterministic support selection prefers original studies, retains excluded objects as dependencies, and preserves contradictions. |
| Shared data/resources and unknown references did not have reliable handling. | Shared dataset/assay/model declarations constrain support counting. Missing references and cyclic lineage remain unresolved. Citation alone does not merge studies. |
| Literature fallback inferred primary-study status from peer review and discarded all but the first citation. | Publication status supplies no study type; multiple supplied citations are preserved. Shared analysis software no longer fabricates shared fitted-model identity. |
| A self-hashed Level 2 dictionary granted backend fidelity and empirical factors without signature verification; unknown integer tiers also fell through to that path. | All receipt tiers grant zero scientific factors until a trusted verifier exists. Level 1/2 emit `ATTESTATION_NOT_VERIFIED`; malformed/conflicting tiers fail closed. |
| `spec/README.md` linked BNS-023 to the wrong document and omitted BNS-024/025. | Index corrected; registry validation checks exactly one correct index link per registered specification. |

## Changed contracts

`lineage_roots` now contains a list of roots per object, matching its declared type.
The legacy `independent_origins` and `effective_independence_ratio` fields describe
declared origins only; they are not independence assessments or probabilities.
`unresolved_evidence_ids`, `dependency_tokens` and `independence_status` make that
boundary machine-visible in the audit, ledger provenance and EvidenceCard.

The strict graph support selector excludes unknown IDs and unresolved lineage.
Claim assessment can retain explicitly adjudicated unresolved support and warns
`SOURCE_LINEAGE_UNRESOLVED`. That is bounded support, not independent replication.

Receipt creators retain their existing tier fields for compatibility. Neither a
host name nor an attestation dictionary authenticates an execution. Hash checking
and log checking remain available, but receipt-based scientific factor promotion
is disabled. Existing caller-supplied metadata/explicit factor APIs are still
declaration inputs; this continuation does not turn them into authenticated evidence.

## Verification

Local Python 3.13.9 / pytest 9.1.1: **133 passed in 4.95 seconds**.

```powershell
python -m pytest tests/unit/test_epistemic_lineage.py tests/unit/test_ecosystem_claim.py tests/unit/test_ecosystem_intake.py tests/unit/test_ecosystem_fixtures.py tests/unit/test_tool_receipt.py tests/unit/test_evidence_model.py tests/unit/test_eval_receipt.py tests/unit/test_eval_receipt_integration.py tests/unit/test_rosalind_adapter.py tests/unit/test_connector_profile.py tests/unit/test_connector_profiles.py tests/unit/test_spec_registry.py tests/unit/test_human_adjudication.py -q -p no:cacheprovider --basetemp=.pytest-tmp-connector-hardening-20260904-c
```

Regression cases include reordered multi-source syntheses, missing lineage,
same-study preprints, duplicate payloads, shared datasets/models, cyclic and dangling
references, forged provider signatures, receipt-log/evidence-model ingestion,
invalid receipt tiers, and stale/duplicate specification index links.

The first expanded run exposed two legacy tests expecting self-declared Level 2
metadata to grant factors. Those assertions were corrected to enforce the trust
boundary; their receipt and log scenarios remain covered. Scoped `git diff --check`
passed. The complete repository suite, hosted CI, installed-plugin behavior and
live connector behavior were not verified by this continuation.

## Remaining evidence requirements

- Trusted host/provider attestation verification is **not implemented** in the
  receipt module. It requires an external trust anchor, exact execution binding,
  role/scope authorization and appropriate expiry/revocation handling before any
  factor promotion can be restored. A provider attestation alone is not independent
  scientific validation or regulatory certification.
- Source aliases and resource identities are supplied declarations. Undocumented
  dataset overlap, hidden mirrors and false lineage declarations are not detected
  by this local deterministic graph.
- The tests are maintainer-authored engineering regressions, not an externally
  validated ConnectorFailureBench, independent scientific replication, adoption
  evidence or certification.
- Connector-profile corpus expansion and TypeScript interoperability already
  present in the working tree were not independently validated here.
