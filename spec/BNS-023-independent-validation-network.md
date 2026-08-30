# BNS-023: Independent Validation Network

**Status**: development | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/ivn.py`, `src/bionexus/calibration_freeze.py`, `validation/ivn/REGISTRY.json`, `bionexus ivn` CLI
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

Frameworks and reviewer slots do not count as completed evidence. The
Independent Validation Network (IVN) turns the flagship external-validation
quotas from prose into computed, hash-verified gates, and binds the
threshold/calibration layer to its held-out evidence:

> **Every flagship capability must reach >= 3 independent datasets x
> >= 2 external labs x >= 1 non-author reviewer, with annotation evidence
> spanning cross-disease / cross-tissue / cross-technology contexts, spatial
> evidence carrying independent pathology or segmentation truth, and
> calibration profiles frozen on held-out contexts.**

The network is an accounting layer, not an honor system: every quota is
recomputed from on-disk artifacts whose SHA-256 digests must match the
registry, and every gate fails closed.

## 2. Registry

- **BNS-IVN-001** The network state MUST live in
  `validation/ivn/REGISTRY.json` with schema version
  `bionexus.ivn.registry.v1`. Entity ids MUST be unique across each entity
  collection; capability ids MUST be flagship capability ids.
- **BNS-IVN-002** The registry MUST carry an author roster. Review
  non-authorship is verified against this roster; an empty or unreadable
  roster means non-authorship cannot be established and no review MAY count.
- **BNS-IVN-003** Entities have statuses `REGISTERED`, `EVIDENCE_SUBMITTED`,
  `VERIFIED`, `RETRACTED`. Only `VERIFIED` entities count toward any quota.
  Registered frameworks, lab slots, and reviewer slots MUST NOT count.

## 3. Datasets

- **BNS-IVN-010** A dataset counts toward the independent-dataset quota only
  when it is not author-associated, is `VERIFIED`, carries a hash-locked
  preregistration and a hash-bound report whose digests match the on-disk
  artifacts at assessment time, and satisfies the capability-specific depth
  requirements below.
- **BNS-IVN-011** For `scrna.pseudobulk_de`, a counting dataset MUST be
  donor-aware: the biological donor is the unit of inference and cell-level
  pseudoreplication is excluded.
- **BNS-IVN-012** For `scrna.annotation_evidence`, the counted datasets MUST
  collectively span at least 2 distinct diseases, 2 distinct tissues, and
  2 distinct technologies (cross-disease, cross-tissue, cross-technology
  coverage). Coverage is computed over counted datasets only.
- **BNS-IVN-013** For `spatial.inference_validity`, every counting dataset
  MUST carry independent ground truth: truth kind `pathology_annotation` or
  `segmentation_truth`, produced by a provider independent of the BioNexus
  authors, blinded to BioNexus outputs. Pipeline-derived truth never
  qualifies. A real-instrument technical acceptance without such truth is
  recorded honestly but does not count.
- **BNS-IVN-014** A negative study outcome (e.g. a frozen negative result)
  remains valid executed evidence for the dataset quota; outcomes are
  recorded and displayed, never silently promoted or dropped.

## 4. External labs

- **BNS-IVN-020** The external-lab quota requires at least 2 `VERIFIED`
  external-lab studies from at least 2 distinct institutions, each with a
  signed independence declaration, an agent host recorded, and a hash-bound
  capsule/report artifact that matches on disk.
- **BNS-IVN-021** A lab study counts only when it executes a dataset that
  itself counts under Section 3.
- **BNS-IVN-022** The cross-host certification criterion (BNS-010) MAY be
  raised to satisfied only when the external-lab quota is met across at
  least 2 distinct hosts; it can never be lowered by this module.

## 5. Non-author review

- **BNS-IVN-030** The reviewer quota requires at least 1 `VERIFIED` review
  whose reviewer is absent from the author roster, whose review was blinded,
  whose verdict is one of `ENDORSED`, `ENDORSED_WITH_LIMITS`, `CHALLENGED`,
  and whose attestation id and hash-bound review artifact are recorded.
- **BNS-IVN-031** The `external_reviewer` certification criterion (BNS-010)
  MAY be raised to satisfied only when BNS-IVN-030 is met; the
  implementation MUST NOT satisfy `external_reviewer` with its own authors.

## 6. Calibration freeze

- **BNS-IVN-040** Only an `APPROVED` calibration profile whose
  `validation_issues()` are empty MAY be frozen; freezing MUST record the
  canonical profile hash, the accountable approvers, and at least one
  held-out context (`partition = "validation"`).
- **BNS-IVN-041** A freeze binds the profile to explicit held-out contexts
  (disease / tissue / platform / technology fingerprints plus dataset
  digests). A positive warrant in a context is authorized only when an
  intact freeze for the exact profile version exists and the context is
  inside the frozen held-out scope; all other combinations MUST yield a
  non-authorizing decision (`PROFILE_NOT_APPROVED`, `FREEZE_REQUIRED`,
  `FREEZE_MISMATCH`, `CONTEXT_NOT_COVERED`).
- **BNS-IVN-042** Any post-freeze modification of the profile invalidates
  the freeze (`FREEZE_MISMATCH`); a changed threshold requires re-approval
  and a new freeze. Freezing never overwrites, downgrades, or auto-approves
  an existing profile.
- **BNS-IVN-043** The packaged calibration registry ships zero APPROVED
  profiles; therefore zero profiles are frozen and the calibration
  authorization gate refuses by default (fail-closed frontier, consistent
  with BNS-018 and the OPEN_QUESTIONS calibration blocker).

## 7. Honesty invariants

- **BNS-IVN-050** Every quota re-verification MUST recompute artifact
  digests from disk at assessment time; trust-on-write is forbidden.
- **BNS-IVN-051** The network assessment MUST publish, per capability, the
  counted and excluded entities with exclusion reasons, plus the blocking
  gaps — this list is the external-validation roadmap.
- **BNS-IVN-052** The assessment MUST derive the four
  `docs/context/OPEN_QUESTIONS.md` blockers (calibration, real-data
  validation, cross-host + independent review, external adoption and
  governance) from evidence. No registry content, schema, or local test MAY
  mark the adoption/governance blocker resolved; that requires signed
  governance council records this schema cannot synthesize.
- **BNS-IVN-053** `bionexus ivn status` MUST remain runnable in any
  environment (no scientific backends required); the network can only ever
  raise a certification criterion above its static baseline, never lower one.

## 8. Current assessed state (post-rc3 baseline)

Recorded honestly in `validation/ivn/REGISTRY.json`:

| Flagship | Independent datasets | External labs | Non-author reviewers |
|---|---|---|---|
| `scrna.pseudobulk_de` | 3/3 (GSE96583, Parse-10M+C04, C05 — all frozen negative results) | 0/2 | 0/1 |
| `scrna.annotation_evidence` | 2/3 (CITE-seq PBMC, Azimuth PBMC) — cross-disease 1/2, cross-tissue 1/2, cross-technology 2/2 | 0/2 | 0/1 |
| `spatial.inference_validity` | 0/3 (Xenium kidney tiny lacks independent pathology/segmentation truth) | 0/2 | 0/1 |

Zero frozen calibration profiles. All four OPEN_QUESTIONS blockers remain
open. This table is the work program: cross-disease/tissue annotation
cohorts, a spatial public cohort with independent truth, two external labs
per flagship, one non-author reviewer per flagship, and held-out-frozen
calibration profiles are all outstanding.
