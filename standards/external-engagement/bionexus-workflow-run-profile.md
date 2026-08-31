# BioNexus evidence terms in Workflow Run RO-Crate — implementation proposal

Status: implementation proposal, version 0.1.0. No external adoption or
endorsement is claimed.

## Base profiles

The proposal only extends existing Research Object profiles. A conforming
BioNexus run crate declares and satisfies:

- RO-Crate 1.1;
- Process Run Crate 0.5;
- Workflow RO-Crate 1.0;
- Workflow Run Crate 0.5; and
- Provenance Run Crate 0.5 when recorded steps are present.

The base profile chain remains authoritative. BioNexus terms add evidence and
claim-boundary annotations; they do not weaken or replace any base constraint.

## Extension entities

An EvidenceCard is a schema.org `CreativeWork` whose `about` points to the main
run `CreateAction`. Compact terms from `bionexus-context.jsonld` may record the
execution state, conclusion maturity, input integrity, assumption validity,
statistical support, parameter robustness, cross-method concordance, and
external validation. Claim and evidence `CreativeWork` entities may record
evidence status, evidence kind, maturity, and validation role.

All values are copied from the sealed source capsule or Claim-Evidence Ledger.
Export MUST NOT promote, infer, or silently fill missing evidence values.

## Fail-closed conformance

The exported crate MUST pass the official `roc-validator==0.11.2` CLI with
profile `provenance-run-crate-0.5`, inherited profiles enabled, and severity
`REQUIRED`. The CI receipt binds the crate metadata and validator log by
SHA-256 and uses status `THIRD_PARTY_TOOL_VALIDATED`.

That receipt establishes technical conformance of the tested fixture only. It
is not certification, endorsement, external adoption, scientific validation,
or permission to raise an EvidenceCard maturity level.
