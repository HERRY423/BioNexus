# Frozen component retest

Upstream base: `683018420a753738d8a84d43f0c60b3a36516698`. Exact source file: `src/bionexus/nextflow_bridge.py`.
The protocol was copied without changing its input tables or expected behavior from
PVL protocol SHA-256 `0282acf427180b42fb825e2281be4f25f577003541e365461c8b00839ac07745`.

Run from the repository root with Python 3.11+ (standard library only):

```sh
python tests/pvl_samplesheet_retest/retest.py --source tests/pvl_samplesheet_retest/before.py --output before-retest
python tests/pvl_samplesheet_retest/retest.py --source src/bionexus/nextflow_bridge.py --output after-retest
```

The before run intentionally exits 1 when the frozen regression cases fail.
Both commands refuse existing output directories and unpinned source bytes.
Observed before: 2/5; after: 5/5.
All cases, including valid controls, are retained in `observed-results.json`.

Real public source executed on disclosed synthetic inputs; exact samplesheet helper AST, not the harvest path. No model or independent scientific validation.
No FASTQ pipeline was run. This does not establish plugin/model benefit.
Please record acceptance, elapsed human review/retest time and any disagreement in
`feedback.template.json` or the PR discussion. Rejection and counterexamples are useful outcomes.
Submission does not establish adoption, and a same-owner BioNexus review would not be independent.

Source identity checks normalize CRLF to LF to support Git checkouts on both platforms; actual executed raw byte hashes remain in each report. Other changes are refused. Protocol and bundle bytes are preserved using the local .gitattributes.
