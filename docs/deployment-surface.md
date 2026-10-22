# Real-lab deployment surface

BioNexus already exposes plugins, MCP, CLI, Nextflow, RO-Crate, and BCO.
Those surfaces do not by themselves prove that a laboratory can hand over
mainstream analysis products and get a sealed, re-importable artifact back.

This document is the operator contract for that missing path.

## What is in scope

| Path | Command | Proof |
|---|---|---|
| Lab import / export acceptance | `bionexus deploy accept <source> -o <dir>` | `tests/unit/test_lab_exchange.py` plus `scripts/run_lab_acceptance.py` |
| Product compatibility matrix | `bionexus deploy matrix --json` | `src/bionexus/data/compatibility-matrix.v1.json` |
| Versioned schemas and migration | `bionexus deploy migrate <file>` | `src/bionexus/data/*.schema.json`, `tests/unit/test_schema_migration.py` |
| Opt-in failure reports | `bionexus deploy telemetry` / `report-failure` | `docs/plugin-privacy.md`, `tests/unit/test_failure_report.py` |

Import is a file contract. It does not run Cell Ranger, Seurat, DESeq2, edgeR,
or nf-core, and it does not grant scientific warrant
(`scientific_authorization` remains `NONE`).

## End-to-end acceptance gates

`bionexus deploy accept` walks one source through:

1. `DETECT` — product identity from layout or table headers
2. `IMPORT` — current lab-exchange envelope (`bionexus.lab-exchange-envelope.v2`)
3. `CAPSULE` — sealed run capsule (`run.json`)
4. `RO_CRATE` / `BCO` — fail-closed standards projections
5. `REIMPORT` — reimport the archived product files and recompute their byte checksums
6. `COMPAT` — adapter has `FIXTURE_VERIFIED` or `EXPORTED_ARTIFACT_VERIFIED` status

Source files are checked against the envelope before copying; the copied files
are checked again. Relative paths are preserved. The capsule records its archived
copies as inputs, so integrity verification does not require the original lab's
filesystem. Existing output directories and envelopes are not overwritten.
Compatibility here concerns the adapter's fixture scope; the producer's installed
version is `NOT_ASSESSED`. RO-Crate and BCO gates are structural prechecks, not
official profile conformance.

Every attempt writes `lab-acceptance-receipt.json` with the gate results, artifact
hashes, implementation hashes, and evidence limits. The fixture runner accepts
`--output-dir` and retains its receipts plus `summary.json`; these remain fixture
evidence, not laboratory validation.

Inputs default to `UNKNOWN` classification, which grants no permission to share
or transmit. Use `--data-classification` to declare the actual classification.
That value is retained in the envelope, capsule parameters, RO-Crate access
conditions, BCO parameters, and receipt. Public benchmark classification must
be selected explicitly.

Committed fixtures live under `tests/fixtures/lab_exchange/` for Cell Ranger
`outs/`, Scanpy tables, Seurat MTX exports, DESeq2/edgeR result tables, and
nf-core `samplesheet.csv` + `pipeline_info/`.

## Compatibility statuses

The matrix vocabulary is closed. Do not paraphrase it as certification.

- `FIXTURE_VERIFIED` — CI exercises committed lab-like fixtures
- `EXPORTED_ARTIFACT_VERIFIED` — vendor runtime is not executed; the export the lab actually hands over is verified
- `DECLARED` — adapter exists without a committed fixture
- `LIVE_VENDOR_UNVERIFIED` — the vendor binary has not been run in BioNexus CI
- `UNSUPPORTED` — import is refused (native Seurat `.rds` / `.qs`)

Seurat objects must be exported to MTX/TSV or h5ad before import.

## Schema versions and historical data

Input documents carry `schema_version`. Unknown versions fail closed.
Historical `bionexus.lab-exchange-envelope.v1` documents migrate to v2 through
`bionexus.schema_registry.migrate_document`. Old conclusions are not rewritten.
The historical document is validated first. Missing, malformed, or non-SHA-256
digests are refused; a digest string is never hashed to invent a file checksum.
Preserved historical SHA-256 values carry `DECLARED_UNVERIFIED` until original
file bytes are imported and checked. Absent historical classification becomes
`UNKNOWN`.

## Failure reports

Default is off. BioNexus does not operate a telemetry backend in this release.
Local sanitized JSON is the supported path. Network transmit requires all of:

- `BIONEXUS_FAILURE_REPORTS=transmit`
- `BIONEXUS_FAILURE_REPORTS_ENDPOINT` set by the lab
- `BIONEXUS_EGRESS_MODE=CONNECTED`
- `PUBLIC_BENCHMARK` classification
- `--opt-in-transmit`

Air-gap, PHI, and controlled-access genomic data never transmit. Paths, emails,
IPs, secrets, and long sequences are redacted before disk write.
Unknown or unpublished classification is also ineligible. Transmission rechecks
the current opt-in and egress configuration rather than trusting a previously
computed eligibility flag.
