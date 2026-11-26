# Spatial Alternative Explanation Battery

`spatial.inference_validity` is BioNexus flagship C. Contract version 4 derives external control statuses from
input-bound adjusted effect intervals and measures sample replication from
donor identities. Tissue edge effects and cell-contact geometry are distinct
controls.

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

## Sample replication and evidence binding

For `assess_spatial_inference`, supply the claim-scoped `obs` table and its
group column (default `condition`; use `group_col=None` for a single cohort).
The assessment counts distinct donors in each group. A group with fewer
than two observed donor or section units yields `ABSTAIN`. Multiple sections
may share one donor. With only section IDs, the report shows the section
counts and caps the verdict at `FRAGILE`. To establish independent origins,
supply `sections_are_independent=True`, the SHA-256 in
`section_provenance_sha256`, and the corresponding JSON bytes in `artifacts`.
The JSON object has schema `bionexus.spatial-section-origins.v1` and a
`section_to_donor` object mapping every observed section to its distinct
donor ID. With repeated donors, provide the donor column in `obs` to measure
the number of biological replicates directly. The executable battery accepts
the same origin table as `SpatialBatteryData.section_provenance` alongside
its digest. It counts donor units for focal cells in each exposure arm.

External `ControlResult` objects locate original JSON bytes by
`artifact_sha256`. Pass those bytes in `artifacts` and independently supply
the audited input digest in `input_sha256`. Each JSON report must contain
the following fields.

| Field | Meaning |
|---|---|
| `schema` | `bionexus.spatial-control-result.v1` |
| `control` | Registered name or alias of the control tested |
| `input_sha256` | SHA-256 of the audited input for this observation |
| `baseline_effect_sign` | Integer +1 or −1, consistent across controls and with the expected direction when supplied |
| `adjusted_effect_interval` | Two ordered finite numbers on the effect scale after applying this control |
| `statistic` | Optional finite point estimate |
| Permutation fields | The permutation-calibrated interval additionally requires integer `n_permutations` ≥999, integer `random_seed` and `null_distribution_summary` with finite, ordered `min`, `mean`, and `max` |

An interval wholly in the baseline direction yields `TESTED`; crossing zero
or reversing the sign yields `FAILED`. The verdict records the parsed
interval and source. Unbound or incomplete reports remain `DECLARED`.
The structured report records the submitted measurement. Independent review
establishes the quality of the underlying experiment.

The battery calculates a digest covering the expression matrix and feature
axis, coordinates, contact graph, labels, aligned sample metadata, covariates,
perturbation inputs, observation, plan and calibration context. Each native
diagnostic records this digest and its producer. Its state follows the
executed, calibrated analysis. Native control records serialize as UTF-8
JSON using sorted keys, compact separators and literal Unicode. The battery
records tissue edge effects as `UNTESTED` until a separate boundary challenge
is available.

## Interpreting ROBUST across reports

| Report field | Meaning of `ROBUST` |
|---|---|
| Spatial observation verdict | Every canonical control passes, including a complete permutation null. Target groups have at least two measured donors, directly observed or verified by the section-origin table. |
| General evidence maturity | Measured sample design, replication, confound controls and sensitivity analysis meet the evidence ladder, together with backend fidelity and provenance. Rule violations still cap maturity. |

The spatial verdict enters a broader scientific claim subject to the
capability's external-validation ceiling. The general evidence ladder is
evaluated independently.

## Fail-closed contracts

- Physical tissue coordinates in micrometers are mandatory. UMAP/PCA is refused.
- Dataset, state, segmentation, label, and coordinate-system revisions are mandatory.
- Exact contact graphs and all derived radius graphs are sparse and bounded by a predeclared edge limit.
- An unestimable baseline produces `ABSTAIN`.
- A failed alternative produces `CONFLICTED` when the observation is estimable.
  An untested or declared alternative caps a positive verdict at `FRAGILE`.
  An abstaining report retains any failed controls and their evidence.
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
