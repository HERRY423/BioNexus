# Historical BNS-019 Nextflow trial fixture — not an integration surface

This directory preserves the development 0.1.0 interoperability trial that
executed a BNS-019 validator inside a standalone Nextflow test workflow. It is
retained for reproducibility of the recorded trial, not as a proposal to add a
process, Python script, samplesheet input, or BNS dependency to nf-core
pipelines.

The former samplesheet-derived receipt/EvidenceCard generator and injected
receipt module were removed. They inferred scientific evidence factors from
pipeline shape and therefore violated the explicit-only semantic boundary.

New work uses the zero-touch
[`../ro-crate/bns019_artifact_annotator.py`](../ro-crate/bns019_artifact_annotator.py):
run nf-core unchanged, obtain a Workflow Run RO-Crate (for example via
`nf-prov`), then attach optional semantics to individually hash-bound artifacts
outside the pipeline.

Passing this historical fixture is software-contract evidence only. It is not
nf-core adoption, endorsement, or proof that a production nf-core integration
exists.
