# BNS-012: Claim–Evidence Ledger

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/ledger.py` (ClaimLedger, ClaimRecord, EvidenceRef)
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

A scientific claim should not be a bare sentence ("TP53 pathway enrichment
significant"). It is a node in a dependency graph whose warrant can be audited:

```yaml
CLAIM-017:
  statement: "Cluster 3 exhibits interferon-response activation"
  supported_by: [DE-102, GSEA-021]
  depends_on: [DATASET-SHA256, QC-004, NORMALIZATION-003, CLUSTERING-007]
  contradicted_by: [SCVI-DE-014]
  evidence_status: CONFLICTED
```

## 2. Scope discipline

- **BNS-CL-001** The ledger is a DATA STRUCTURE, not a platform. BioNexus MUST
  implement it as records + JSON persistence + a PROV-O JSON-LD projection.
  There MUST NOT be a graph database, a UI, or a hosted service.
- **BNS-CL-002** Every `ClaimRecord` MUST carry: `claim_id`, `statement`,
  optional `capability_id`, `supported_by`, `contradicted_by`, `depends_on`,
  `evidence_status`, and `provenance`.
- **BNS-CL-003** Every `EvidenceRef` MUST declare a `kind` from the closed
  vocabulary: `dataset`, `transformation`, `method_run`, `statistical_result`,
  `database`, `cross_method`; and a `maturity` from the BNS-EM-004 ladder.
- **BNS-CL-004** `DATASET-` prefixed references MAY be raw content hashes
  without a materialized EvidenceRef node (datasets are large; hashes are
  auditable via BNS-PV-001).

## 3. Status resolution (fail-closed)

- **BNS-CL-005** Claim status resolution MUST be conservative:
  1. Any non-empty `contradicted_by` → `CONFLICTED` (fail-closed).
  2. No supporting evidence → `ABSTAIN` (claims need evidence).
  3. Otherwise → the minimum maturity among supporting evidence, clamped by
     the capability's ABI evidence ceiling (BNS-CC-013); `database` or
     `cross_method` support counts as external validation for the clamp.
- **BNS-CL-006** Resolution MUST never *raise* a claim above its weakest
  supporting evidence; aggregation cannot manufacture warrant.
- **BNS-CL-007** Ledger mutation SHOULD happen only through `add_evidence` /
  `add_claim`; duplicate IDs MUST be rejected (append-only audit semantics,
  BNS-PV-009).

## 4. Serialization

- **BNS-CL-008** The ledger MUST round-trip losslessly through JSON
  (`to_dict` / `from_dict` / `save` / `load`).
- **BNS-CL-009** The ledger MUST provide a PROV-O JSON-LD projection:
  claims are `prov:Entity` nodes `prov:wasDerivedFrom` their dependencies,
  `prov:wasGeneratedBy` the capability; contradiction edges use the `bns:`
  vocabulary. The projection MUST stay valid JSON-LD with a single `@context`
  and MUST NOT require a graph store to consume.

## 5. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-CL-001..004 | `tests/unit/test_ledger.py` (record shape, closed vocabularies) |
| BNS-CL-005..007 | resolution tests incl. the CLAIM-017 reference scenario |
| BNS-CL-008..009 | JSON round-trip and JSON-LD projection tests |
