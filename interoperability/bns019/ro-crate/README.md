# Zero-touch BNS-019 annotation over Workflow Run RO-Crate

This proof of concept consumes provenance already produced by an unchanged
workflow (for example, a Workflow Run RO-Crate emitted by `nf-prov`). It does
not inject a Nextflow process, parse a pipeline samplesheet, require new
pipeline inputs, or replace RO-Crate.

The boundary is deliberate:

- RO-Crate answers **what ran and what entities were produced**.
- BNS-019 optionally records **explicitly declared scientific meaning for one
  hash-bound artifact at a time**.
- Artifacts without an explicit producer declaration remain unannotated.
- Workflow success, filenames, values, and workflow shape never manufacture
  matrix state, biological unit, claim type, confounds, or warrant.

One run produces one annotation manifest containing zero or more independent
artifact annotations. Different matrices in the same run may therefore carry
different semantics; a report, BAM, VCF, or unknown entity can remain without
scientific semantics.

```bash
python interoperability/bns019/ro-crate/bns019_artifact_annotator.py \
  --validator interoperability/bns019/python/bns019_validator.py \
  --standard-root standards/scientific-semantic-conventions \
  --crate PATH/TO/ro-crate-metadata.json \
  --declarations PATH/TO/artifact-semantics.json \
  --output PATH/TO/bns019-artifact-annotations.json
```

The declarations file is producer-authored and must contain
`schema_version`, `producer`, and an `annotations` array. Every annotation
names an existing crate `entity_id`, the exact expected artifact SHA-256, a
BNS-019 convention, and explicit attributes. A run-level `attributes` object
is refused.

The output is an external sidecar. It does not rewrite the RO-Crate and does
not imply nf-core, Nextflow, nf-prov, or RO-Crate community endorsement.
