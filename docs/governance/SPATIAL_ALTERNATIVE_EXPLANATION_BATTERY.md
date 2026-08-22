# Spatial Alternative Explanation Battery

`spatial.inference_validity` is BioNexus flagship C. Version 2 deepens that
capability into an executable challenge battery; it does not add a fourth
flagship and it is not a wrapper around a generic Squidpy workflow.

## Scientific question

For a predeclared observation such as:

> CXCL13 expression is enriched in T cells at macrophage contacts.

the battery asks whether the estimated effect survives plausible measurement,
geometry, field, and labeling explanations. It returns `ROBUST`, `SUPPORTED`,
`FRAGILE`, `CONFLICTED`, or `ABSTAIN`; it does not infer a causal mechanism.

## Executed controls

| Alternative explanation | Executable challenge | Required evidence boundary |
|---|---|---|
| Segmentation uncertainty | Re-estimate across supplied anchored-cell expression/contact revisions | BioNexus never fabricates a segmentation; topology-changing merge/split validation remains future work |
| Transcript leakage | Re-estimate across supplied leakage-model outputs, or a predeclared neighbor-mixture sensitivity grid | Assumed fractions are sensitivity parameters, not estimates or corrections |
| Cell size | Exposure effect adjusted for supplied cell size | Missing morphology stays `UNTESTED` |
| Nuclear eccentricity | Exposure effect adjusted for supplied eccentricity | Missing morphology stays `UNTESTED` |
| Transcript density | Exposure effect adjusted for local neighbor-averaged transcript counts | Counts must align with the state revision |
| Local cell density | Exposure effect adjusted for physical-radius neighbor count | Radius and units are predeclared |
| Contact geometry | Exact contact effect challenged by radius proximity and edge-weight adjustment | Contact claims require an exact segmentation-derived graph; radius is never substituted as exact contact |
| FOV/batch | Effect re-estimated within at least two supplied fields/batches | Cross-FOV graph edges are removed for each within-field estimate |
| Neighborhood radius | Effect retained across a predeclared physical-radius grid | No optimized radius is selected post hoc |
| Coordinate null | Two-sided coordinate-permutation null with +1 correction | All requested permutations must be estimable |
| Spatial autocorrelation | The same null score, resolved through its own calibration metric | Separate calibration prevents one null from silently warranting two claims |
| Cell-label uncertainty | Supplied label revisions plus partial count-preserving label permutations | Random perturbations do not replace platform-specific confusion models |

Spot composition and ligand/receptor abundance are explicit applicability
controls. A cell-resolved expression-enrichment claim may record them as not
applicable; a spot-resolved or ligand/receptor claim cannot silently inherit
that status.

## Fail-closed contracts

- Physical tissue coordinates in micrometers are mandatory. UMAP/PCA is refused.
- Dataset, state, segmentation, label, and coordinate-system revisions are mandatory.
- Exact contact graphs and all derived radius graphs are sparse and bounded by a predeclared edge limit.
- An unestimable baseline produces `ABSTAIN`.
- A failed alternative produces `CONFLICTED`; an untested alternative produces
  `FRAGILE`. `ABSTAIN` is reserved for absent or unestimable evidence rather
  than hiding an observed contradiction.
- Every numeric decision first resolves
  `threshold(metric, tissue, platform, reference, task, evidence_source)` from
  the Empirical Calibration Layer, then independently verifies exact Spatial
  Gold Program membership, real-study manifest bytes, approved profile bytes,
  a trusted signature, expiry, and signed revocation state. A generic
  `APPROVED` profile is insufficient. Any missing or mismatched gate means
  `UNTESTED`; there is no universal fallback threshold.
- The output binds input/variant hashes, revision IDs, plan, random seed,
  calibration registry hash, and a deterministic battery-run hash.

## Why this is the flagship scientific direction

Segmentation error has been shown to confound differential expression,
neighbor-influence, and ligand-receptor analyses and to frequently dominate
results in imaging spatial transcriptomics ([Nature Genetics, 2026](https://www.nature.com/articles/s41588-025-02497-4)).
A 2026 preprint reports transcript leakage across platforms, species, and
tissues, affecting expression quantification, annotation, and spatially
dependent expression ([bioRxiv 10.64898/2026.06.13.732076](https://www.biorxiv.org/content/10.64898/2026.06.13.732076v1)).
SpatialCCCbench separately emphasizes robustness under multiple noise regimes
and boundary-related analysis
([bioRxiv 10.64898/2026.05.19.724475](https://www.biorxiv.org/content/10.64898/2026.05.19.724475v1)).
These papers motivate the battery surface; they do not validate BioNexus.

## Current evidence boundary and calibration program

The engine and fail-closed contract are implemented. Unit tests use synthetic
software fixtures. Synthetic generic `APPROVED` profiles are now explicitly
ignored by runtime authorization and cannot produce `ROBUST`. Separate signing
fixtures exercise cryptographic plumbing but are not packaged as program
evidence. The packaged registry currently contains no approved real spatial
calibration profile. Therefore the implementation is not evidence that the
battery is biologically calibrated, cross-platform robust, or superior.

The next scientific program is deliberately narrow:

1. Pre-register one observation family, outcome adjudication, operating
   criterion, perturbation generators, and held-out split.
2. Run platform-separated studies on real Xenium, CosMx, and MERSCOPE data;
   isolate donors, tissues, segmentation versions, and FOVs.
3. Calibrate each metric separately by empirical regime. Never pool platforms
   merely to increase sample size.
4. Include known segmentation/leakage counterexamples and negative observations,
   not only prepared positive cohorts.
5. Require independent review and held-out evidence before any profile becomes
   `APPROVED`.
6. Report coverage, abstention, failures, and regime gaps alongside successful
   warrants. Missing platform evidence remains `incomplete_not_claim_ready`.

The program is now machine-enforced by the
[Spatial Empirical Gold Standard](SPATIAL_EMPIRICAL_GOLD_STANDARD.md). Its scope
is exactly Xenium, CosMx, and MERSCOPE. A supplied approved profile from any
other platform is ignored for control promotion and is reported as
`OUT_OF_GOLD_PROGRAM_SCOPE`.

The current zero-threshold registry reports 36 platform × metric coverage gaps,
zero registered real studies, and zero approved profiles. Synthetic contract
fixtures may still exercise the resolver, but they never enter the program
registry or count as platform evidence.
