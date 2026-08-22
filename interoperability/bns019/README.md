# BNS-019 multi-implementation interoperability

This directory makes one language-neutral BNS-019 release consumable by
independent validators and host adapters without copying the registry into any
implementation.

| Track | Role | Registry source | Host boundary |
|---|---|---|---|
| Python | independent validator | unpacked BNS-019 release | standard library only |
| R | independent validator | same unpacked release | `jsonlite` + `digest`; no Python |
| Scanpy/AnnData | host adapter | same unpacked release | `adata.uns["bionexus"]` only |
| Seurat | host adapter | same unpacked release | `object@misc$bionexus` only |
| nf-core/Nextflow | workflow adapter | same unpacked release | JSON workflow record + `versions.yml` |

“Independent validator” and “host adapter” are deliberately different
claims. Scanpy, Seurat, and nf-core integrations do not count as additional
independent semantic engines when they reuse a validator.

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
