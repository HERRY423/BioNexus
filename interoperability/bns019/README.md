# BNS-019 multi-implementation interoperability

This directory makes one language-neutral BNS-019 release consumable by
independent validators and host adapters without copying the registry into any
implementation.

| Track | Role | Registry source | Host boundary |
|---|---|---|---|
| Python | independent validator | unpacked BNS-019 release | standard library only |
| R | independent validator | same unpacked release | `jsonlite` + `digest`; no Python |
| TypeScript (`@bionexus/scientific-semconv`) | independent validator / producer | same unpacked release | standard library (`node:crypto`, `node:fs`); zero runtime deps |
| Scanpy/AnnData | host adapter | same unpacked release | `adata.uns["bionexus"]` only |
| Seurat | host adapter | same unpacked release | `object@misc$bionexus` only |
| RO-Crate artifact annotator | zero-touch sidecar | same unpacked release | existing RO-Crate + explicit per-artifact declarations |

“Independent validator” and “host adapter” are deliberately different
claims. Scanpy, Seurat, and workflow integrations do not count as additional
independent semantic engines when they reuse a validator.

The recommended workflow boundary is now
[`ro-crate/`](ro-crate/): run the pipeline unchanged, consume provenance
already produced by the engine or `nf-prov`, and annotate only selected
hash-bound artifacts. The older [`nf-core/`](nf-core/) Nextflow process is
retained solely as a frozen historical interoperability-trial fixture; it is
not a proposed deployment mechanism and must not be copied into nf-core
pipelines.

Run the locally available tracks:

```bash
python interoperability/bns019/trial/run_trial.py \
  --output interoperability/bns019/trial/results/local-run.json
```

The runner emits `NOT_RUN` when a runtime or host dependency is absent. It
returns `INCOMPLETE` rather than turning an adapter-core test into host or
workflow conformance.

The public trial protocol is in [`trial/PROTOCOL.md`](trial/PROTOCOL.md). The
trial becomes public only when these files and CI are published; the checked-in
manifest therefore starts as `open_on_publication`, not `open`.
