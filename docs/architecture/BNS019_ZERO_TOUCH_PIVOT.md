# BNS-019 zero-touch, artifact-addressable pivot

Status: accepted repository architecture decision, 2026-09-01.

## Problem

The first nf-core prototype mixed two layers:

1. generic execution provenance; and
2. domain-specific scientific meaning.

It also assumed a samplesheet shape and inferred evidence factors from sample
and condition counts. That approach could not generalize across nf-core
pipelines or heterogeneous output entities and risked fabricating semantics
that were absent from the run.

## Decision

- BioNexus does not modify nf-core pipelines for generic BNS-019 integration.
- Workflow Run RO-Crate / `nf-prov` owns execution provenance.
- BNS-019 annotations are optional and attach to individual, SHA-256-bound
  artifact entities.
- One run-level manifest may group many artifact annotations, but it may not
  apply one blanket interpretation to all outputs.
- Only explicit producer or domain-adapter declarations populate semantics.
  Unknown fields remain absent/unassessed.
- The generic adapter does not parse samplesheets, inspect matrix values, infer
  from filenames, or convert workflow success into scientific warrant.

## Consequences

The samplesheet-derived receipt/EvidenceCard generator and injected receipt
module are retired. A standard-library-only external RO-Crate annotator is the
new proof-of-concept surface. The older Nextflow semantic process remains only
as a frozen historical interoperability-trial fixture.

This narrows BNS-019 to a passive, implementation-neutral annotation contract.
It does not make BioNexus a workflow engine, plugin platform, or autonomous
agent.

## External-evidence boundary

External maintainer feedback motivated this decision, but no authenticated,
permanent third-party discussion URL has yet been registered in this
repository. Therefore external engagement states remain zero. A conversation
summary, screenshot, local implementation, or maintainer-authored draft cannot
create `external_discussed`, `external_referenced`, `external_implemented`, or
`external_adopted` status.
