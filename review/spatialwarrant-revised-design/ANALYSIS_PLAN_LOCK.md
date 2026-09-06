# SpatialWarrant analysis plan lock

Status: `DRAFT_FOR_WORKBENCH_PREREGISTRATION`

This document preserves the complete S0–S7 design. It separates the primary
endpoint from secondary and exploratory analyses; it does not remove any
planned dataset, method, audit, or showcase element.

## Primary question

Across the six public Wu et al. breast-cancer Visium sections, does a
tumor–stroma boundary defined only from producer-provided pathology regions and
spatial geometry show a directionally consistent difference in a prespecified
immune/IFN program relative to tumor core?

No result direction, p value, runtime, memory peak, or BioNexus verdict has
been observed. Every result claim starts as `PENDING`.

## Scientific units and gates

- The raw observations are Visium spots; spots are not biological replicates.
- The intended independent unit is patient/sample. The metadata audit must
  establish the patient–sample–section relationship before patient-level
  language is allowed.
- Until that audit passes, all text must say `six sections`, not `six patients`.
- Each included section needs usable raw counts, coordinates, producer
  pathology labels, and enough boundary and core spots under the frozen rule.
- If fewer than four independent paired units remain, population-effect claims
  are blocked and the output becomes a descriptive case series.

## Boundary lock

The primary boundary is generated before expression testing from:

1. producer-provided invasive-cancer and stroma regions;
2. observed Visium coordinates and the registered spot-neighbor distance;
3. a preregistered boundary distance selected from 1, 2, or 3 spot spacings;
4. a core definition requiring tumor spots to be at least 3 spot spacings from
   the tumor–stroma interface;
5. a minimum of 20 spots and 100,000 total UMIs in each sample-region
   pseudobulk, unless the preflight justifies a stricter threshold.

Immune/stromal proportions, IFN genes, clusters, Tangram, marker scores,
ingest, niche assignments, differential expression, and literature must not
alter the primary mask.

## Prespecified primary endpoint

The primary endpoint is a paired sample-level effect for a frozen immune/IFN
program. The final gene set must be recorded before viewing boundary/core
expression and must include the exact source and version. A defensible default
is the MSigDB Hallmark Interferon Gamma Response set, with a short
project-focused panel (CXCL9, CXCL10, CXCL11, IDO1, STAT1, IRF1) reported as a
prespecified secondary display rather than used to choose the result.

Report:

- the effect for every independent sample;
- the paired aggregate effect and uncertainty interval;
- the number of samples with the same effect direction;
- leave-one-sample-out estimates;
- sensitivity across the frozen 1/2/3-distance masks;
- missing/failed samples and the exact denominator.

Exploratory gene-level DE uses raw-count pseudobulk with `~ section + region`
unless verified metadata identifies a different patient key. It is secondary,
uses BH adjustment, and cannot redefine the primary endpoint.

## Full retained S0–S7 design

### S0 — environment and plan-first approval

- Verify actual Workbench plugin versions and callable tools.
- Query the live NGS Analysis Workbench catalog.
- Record Python, dependency, memory, disk, and output-directory readiness.
- Astra produces the lock and waits for named human approval.

### S1 — public data and provenance

- Acquire GSE176078, Zenodo 4739739, the planned 10x transfer section, LIANA
  resources, and the knowledge-database returns.
- Preserve URL, provider identifier, size, provider checksum when present,
  local SHA-256, timestamp, and raw tool/download logs.
- Build `sample-identity.csv` with patient, sample, section, subtype, lab,
  modality, and evidence source; unknown values stay unknown.

### S2 — scRNA reference

- Retain the 40k stratified reference design, QC, HVG, PCA, numeric Leiden,
  author-label evidence, and provenance outputs.
- Use a registered NGS workflow only if the live catalog exposes a compatible
  processed-matrix entry and it is actually run. Otherwise use and label local
  Python/scverse execution.

### S3 — Visium QC and spatial domains

- Inspect coordinates, counts, tissue membership, labels, missing values, and
  per-section QC.
- Retain Leiden resolution sensitivity, ARI/NMI, overlays, Moran analysis, and
  boundary Dice/Jaccard.
- Treat producer pathology as an orthogonal reference from the same study.

### S4 — deconvolution and method sensitivity

- Retain Tangram cluster mode on CPU.
- Add a marker/NNLS composition baseline for proportion-level comparison.
- Retain scanpy ingest as label transfer only; do not call it proportional
  deconvolution.
- Shared-reference agreement is a sensitivity result, not independent
  biological validation.

### S5 — niche and boundary biology

- Retain KMeans niche analysis, k sensitivity, neighborhood enrichment,
  co-occurrence, Moran analysis, and six-section mapping.
- Use the pathology-geometry boundary frozen above.
- Do not add immune/stromal composition to the primary boundary definition.
- Retain the 10x section as a technical transfer check. Without matched
  pathology/clinical truth, it cannot validate the named boundary niche.

### S6 — pseudobulk, LIANA, pathways, and literature

- Execute the primary program endpoint first.
- Retain full paired pseudobulk DE, LIANA, pathway/target queries, and the top
  results literature table.
- Label LIANA as inferred communication and literature agreement as external
  context, not causal proof or independent reproduction of this result.

### S7 — evidence audit and submission

- Preserve Claim–Evidence Ledger, Evidence Debt, provenance, an overclaim
  test, all eight screenshot concepts, and the English submission thread.
- Machine verdicts must be imported from hash-bound receipts, not edited in the
  dashboard.
- Human Scientific Adjudication is named, dated, reasoned, and cannot raise a
  machine evidence ceiling.

## Model roles

- `gpt-6-astra`, high or xhigh: S0 preregistration, statistical challenge,
  conflict resolution, claim audit, final four-image story, and wording review.
- `gpt-5.6-sol`, high: downloads, environment work, code, long executions,
  checkpoints, recovery, file inspection, tables, figures, and evidence
  packaging.
- Model choice is recorded in the run log but is not scientific validation.

## Required output tree

```text
spatialwarrant-run-01/
  00_plan/
  01_inputs/
  02_identity/
  03_scrna_reference/
  04_visium_qc/
  05_boundary_masks/
  06_deconvolution/
  07_niches/
  08_pseudobulk/
  09_liana_literature/
  10_bionexus_audit/
  11_figures/
  12_submission/
  logs/
  environment/
  manifest/
```

No prior rehearsal directory may be overwritten.

