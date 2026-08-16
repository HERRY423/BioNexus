# BNS-002: Input Semantic Invariants

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/integrity.py`, capability input specifications, router stages 2–3
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

Most scientific software failures in agent-driven biology are not crashes — they are
**semantically valid executions on semantically invalid inputs**: a negative-binomial
model fitted to log-normalized floats, spatial statistics on non-spatial embeddings,
cluster IDs narrated as discovered cell types. This document defines the input
invariants BioNexus enforces *before* any analysis executes.

## 2. Count-scale invariants

- **BNS-II-001** For single-cell differential expression, an implementation MUST
  verify whether the matrix represents **raw counts** or **transformed expression**
  (log-normalized, scaled, z-scored) before model selection.
- **BNS-II-002** A negative-binomial count model (PyDESeq2 pseudobulk, scVI/totalVI
  generative likelihoods) MUST NOT be executed on log-normalized values without an
  explicit, recorded justification. In strict mode this is a deterministic refusal
  (`normalized_matrix_only` / `normalized_input`), with the remedy pointing at
  `adata.raw.X` or a `counts` layer.
- **BNS-II-003** Integer-likeness checks MUST be performed on the actual matrix
  values (`audit_expression_matrix`), not inferred from file suffixes or user claims.
  A matrix of floats whose values are all integral MAY be accepted as counts; a matrix
  containing negative values MUST be refused as count input.
- **BNS-II-004** Analyses that *require* normalized expression (e.g. Moran's I SVG
  detection on expression) MUST declare `normalized_expression` (or wider) in their
  ABI input contract; passing raw counts SHOULD trigger an advisory, not a refusal,
  unless the downstream method is scale-sensitive.

## 3. Spatial invariants

- **BNS-II-005** A spatial analysis MUST NOT claim spatial autocorrelation unless
  **physical coordinates** or a **justified spatial embedding** is available. The ABI
  input contract MUST enumerate the allowed `coordinate_type` values
  (`physical`, `justified_spatial_embedding`).
- **BNS-II-006** A UMAP/PCA embedding of expression data MUST NOT be silently
  substituted for physical coordinates. If only a non-spatial embedding exists, the
  runtime MUST either refuse or — when the capability explicitly allows
  `justified_spatial_embedding` — emit a DEGRADED/FRAGILE advisory naming the
  substitution.
- **BNS-II-007** Spatial graph construction requires non-degenerate geometry:
  coordinates MUST have positive variance on at least two axes, and spot/cell counts
  MUST suffice for graph construction (>= 5 spots for KNN graphs). Violations are
  deterministic refusals (`degenerate_spatial_coordinates`,
  `insufficient_spatial_spots`).

## 4. Biological identity invariants

- **BNS-II-008** Unsupervised clusters MUST NOT be promoted to biological cell-type
  identities without an **explicit annotation evidence source** (validated reference
  atlas, marker-panel curation with cited markers, or a trained classifier with a
  recorded training set). Cluster labels in outputs MUST remain numeric
  (`"0"`, `"1"`, ...) until such evidence is attached.
- **BNS-II-009** Marker genes derived from cluster ranking (e.g.
  `rank_genes_groups`) MUST NOT be reported as condition-level differential
  expression. Cross-conflation of within-sample exploratory statistics with
  between-condition inference is a scientific semantic error and is benchmarked
  (eval category `scientific_semantics`).
- **BNS-II-010** Cell-level and sample-level experimental units MUST NOT be
  conflated. Condition inference on single cells without replicate aggregation is
  pseudoreplication and MUST be refused (BNS-005, `missing_replicates`).

## 5. Clinical invariants

- **BNS-II-011** Survival estimation MUST verify that at least one uncensored event
  exists (`non_zero_events`); all-censored cohorts are refused (`all_censored`).
- **BNS-II-012** Durations MUST be non-negative; negative follow-up times indicate
  data corruption and MUST be refused rather than clipped.
- **BNS-II-013** ACMG/AMP classification MUST NOT apply PVS1 unless the
  loss-of-function mechanism for the gene is verified
  (`no_auto_pvs1_without_mechanism`). Caller-supplied codes MUST be traceable to
  evidence rationales.

## 6. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-II-001..003 | `integrity.audit_expression_matrix`; eval `refusal` (refuse-normalized-counts-001, refuse-scvi-normalized-001) |
| BNS-II-004 | ABI input contracts (`bionexus abi show spatial.morans_svg`) |
| BNS-II-005..007 | eval `refusal` (refuse-spatial-degenerate-001); `tests/unit/test_capabilities.py` |
| BNS-II-008 | eval `capability_claim`; `claim_checker._CELL_TYPE_ASSERTION_PATTERNS` |
| BNS-II-009 | eval `scientific_semantics` |
| BNS-II-010 | eval `refusal` (refuse-pseudorep-001/002) |
| BNS-II-011..013 | eval `refusal` (refuse-survival-all-censored-001); `tests/unit/test_clinical_cohort.py` |
