# nf-core / BNS-019 zero-touch architecture response — draft, unsent

Status: revised proof-of-concept draft. This is not an RFC, submission,
external discussion receipt, endorsement, or adoption record.

## Proposed response

Thanks — the feedback exposes a real flaw in the first prototype: it
conflated generic execution-provenance collection with domain-specific
scientific semantics.

The revised boundary is:

- no samplesheet parsing, new pipeline inputs, injected processes, or Python
  scripts in nf-core pipelines;
- run nf-core unchanged and rely on engine-native provenance or an opt-in
  plugin such as `nf-prov` to produce Workflow Run RO-Crate;
- treat the run as the provenance container, while attaching optional BNS-019
  semantics to individual output entities;
- populate semantics only from an explicit producer or domain-specific
  adapter; unknown matrix state, biological context, claim type, confounds, or
  warrant remain unannotated.

The new proof of concept consumes an existing `ro-crate-metadata.json` plus an
explicit artifact declaration file and produces a separate, hash-bound
annotation manifest. It never modifies the pipeline or crate. Different count
matrices in one run may have different semantics, while reports/BAM/VCF files
remain unannotated unless a producer declares them.

This makes BNS-019 an optional vocabulary/profile layered on provenance rather
than a provenance replacement or nf-core dependency. The useful next test is:

```text
unchanged nf-core/rnaseq + nf-prov
  -> Workflow Run RO-Crate
  -> explicit domain declarations for a small number of understood artifacts
  -> external BNS-019 artifact annotation manifest
```

I would rather validate that proof of concept and ask whether any useful gap
remains after RO-Crate/nf-prov before proposing an RFC.

## Repository evidence

- zero-touch adapter: `interoperability/bns019/ro-crate/`
- BNS-019 development proposal:
  `spec/BNS-019-scientific-semantic-conventions.md`
- WRROC composable-profile question:
  `standards/external-engagement/bionexus-workflow-run-profile.md`

The old injected receipt generator was removed. The remaining Nextflow process
is a frozen historical trial fixture only and is explicitly not an integration
surface.
