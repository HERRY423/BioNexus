# Spatial Empirical Gold Standard

## Product decision

BioNexus will deepen `spatial.inference_validity`; it will not add a fourth
flagship or a broad spatial-omics toolbox. The empirical program admits exactly
three cell-resolved imaging platforms:

- Xenium;
- CosMx; and
- MERSCOPE.

Visium, Slide-seq, generic spots, proteomics, metabolomics, and new vendor
pipelines are outside this calibration program. They may use descriptive
software, but they cannot inherit a Spatial Empirical Gold warrant.

## Calibration target

The unit of calibration is not “a platform score.” It is:

```text
threshold(
  alternative-explanation metric,
  platform release,
  tissue,
  panel,
  task,
  reference/adjudication protocol,
  evidence-source version
)
```

Each profile belongs to one platform. Xenium, CosMx, and MERSCOPE observations
are never pooled to manufacture sample size or a universal threshold. Transfer
between platforms is a new empirical claim requiring its own held-out study.

## Gold evidence chain

```text
real platform export + immutable hash
                │
                ▼
preregistered study manifest
  ├─ exact platform release / tissue / panel / task
  ├─ calibration donors + FOVs
  ├─ disjoint held-out donors + FOVs
  ├─ segmentation and leakage model revisions
  └─ independent adjudication protocol
                │
                ▼
executed Alternative Explanation Battery
  └─ every metric row binds battery_run_sha256
                │
                ▼
independently adjudicated outcome record
                │
                ▼
precision-controlled candidate fit
  └─ CANDIDATE only; never automatic approval
                │
                ▼
external review + verified signed attestation
                │
                ▼
APPROVED regime-specific profile
```

Both donor and FOV partitions are disjoint. This blocks a common leakage path
where nearby fields or repeated donor biology appear in both calibration and
validation. Every observation also carries the exact battery receipt digest and
adjudication-record digest, so a score cannot be detached from the executed
data state or truth decision.

## Alternative-explanation program

The program covers the twelve numeric battery metrics already implemented:
segmentation, transcript leakage, cell size, nuclear eccentricity, transcript
density, local cell density, contact geometry, FOV/batch, neighborhood radius,
coordinate permutation, cell-label perturbation, and spatial autocorrelation.

The scientific execution order is narrower:

1. **Segmentation and transcript leakage** — mandatory first anchors on each
   platform because these can directly alter cell assignment and top hits.
2. **Morphology, density, and contact geometry** — calibrated only after the
   state-bound segmentation/leakage evidence chain is operational.
3. **FOV, radius, null, and label sensitivity** — calibrated against the same
   preregistered observation family without post-hoc choice of radius or null.

This ordering is an evidence dependency, not a claim that later controls are
less important.

## Machine contracts

The zero-threshold program registry and schemas live under
`calibration/spatial-empirical-gold-standard/`:

- `program.json` fixes the three-platform scope, metric identities, directions,
  and empirical-anchor requirements;
- `schemas/study-manifest.schema.json` defines preregistration and split
  provenance;
- `schemas/observations.schema.json` defines battery/adjudication-bound metric
  records; and
- `bionexus.spatial_empirical_gold` validates byte-level manifest binding,
  every per-record battery/adjudication artifact, partitions, platform
  isolation, candidate fitting, runtime program membership, approval
  signatures, expiry, and signed revocation state.

`bionexus-spatial-gold inventory|validate-study|verify-artifacts|validate-observations`
provides the fail-closed command-line inspection path. Candidate fitting also
requires a receipt covering study artifacts, the observation artifact, and
every `<record_id>:battery_run` and `<record_id>:adjudication_record` byte
binding; declared hashes without corresponding bytes are insufficient.

Runtime promotion is a separate gate. A normal calibration registry entry with
`review_status=APPROVED` cannot control a Spatial Gold diagnostic. The exact
profile must be active in an `externally_validated` program and platform whose
registry bytes are re-read, bind registered real-study manifests and
full-record verification receipts, and carry a target-bound
`spatial-gold-profile-approval` attestation that verifies against the configured
trust registry after expiry and signed-revocation checks. Profile artifact maps
use `<profile_id>@<version>` keys to prevent cross-version substitution.

The program registry intentionally contains no `threshold` field, studies, or
approved profiles.

## Current evidence state

Current machine inventory:

| Measure | Value |
|---|---:|
| Supported platforms | 3 |
| Alternative-explanation metrics | 12 |
| Platform × metric cells | 36 |
| Registered real studies | 0 |
| Approved profiles | 0 |
| Coverage gaps | 36 |
| Claim-ready | No |

Therefore the current state is `incomplete_not_claim_ready`. Unit tests use
software fixtures and do not count as Xenium, CosMx, or MERSCOPE evidence.
Passing schema validation or fitting a candidate does not prove segmentation
accuracy, leakage correction, biological validity, cross-platform transfer, or
superiority.

## Exit gate for the first empirical release

The first defensible release requires, for each of Xenium, CosMx, and MERSCOPE:

1. at least one immutable real-data study manifest;
2. preregistered, donor- and FOV-disjoint held-out observations;
3. segmentation and transcript-leakage battery receipts linked to independent
   adjudication;
4. negative/counterexample outcomes, not only prepared positive observations;
5. a candidate threshold fit with full coverage and abstention reporting; and
6. independent review represented by a verifiable, revocable signed
   attestation.

Until every required evidence artifact is present, missing cells remain visible
coverage gaps and cannot be replaced by a neighboring platform profile.
