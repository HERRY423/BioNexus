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

## Composable extension boundary

Workflow Run RO-Crate remains authoritative for execution provenance. The
BioNexus extension is proposed as a separate composable profile, not a change
to the WRROC core profile and not a replacement for `nf-prov`.

An EvidenceCard may remain a contextual `CreativeWork` associated with the
main run `CreateAction`, but scientific semantic annotations are
artifact-addressable: each annotation targets one crate entity and binds that
entity's SHA-256. A run-level annotation manifest can group several such
records without applying one blanket meaning to every output.

The modeling question for external review remains open: reuse existing
schema.org/PROV-O terms where possible, then determine whether the annotation
manifest should itself be a contextual entity, an external referenced JSON
artifact, or a separate Profile Crate. BioNexus does not declare that choice
settled on behalf of the RO-Crate community.

All values are copied from a sealed source capsule, Claim-Evidence Ledger, or
an explicit producer/domain-adapter declaration. Export MUST NOT promote,
infer, or silently fill missing evidence values. Unannotated artifacts remain
unassessed.

## Fail-closed conformance

The exported crate MUST pass the official `roc-validator==0.11.2` CLI with
profile `provenance-run-crate-0.5`, inherited profiles enabled, and severity
`REQUIRED`. The CI receipt binds the crate metadata and validator log by
SHA-256 and uses status `THIRD_PARTY_TOOL_VALIDATED`.

That receipt establishes technical conformance of the tested fixture only. It
is not certification, endorsement, external adoption, scientific validation,
or permission to raise an EvidenceCard maturity level.
