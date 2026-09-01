# Independent Validation Network (BNS-023)

The Independent Validation Network (IVN) is the computed accounting layer for
the external-validation quotas that bound what the three flagship
capabilities may claim. It exists because frameworks and reviewer slots do
not count as completed evidence — only hash-verified artifacts do.

- **Specification**: [`spec/BNS-023-independent-validation-network.md`](../spec/BNS-023-independent-validation-network.md)
- **Implementation**: `src/bionexus/ivn.py` (network), `src/bionexus/calibration_freeze.py` (calibration freeze), `src/bionexus/ivn_ledger_page.py` (public ledger portal)
- **Registry**: `validation/ivn/REGISTRY.json`
- **Public Append-Only Ledger Portal**: `docs/ivn/index.html` (Deployed via GitHub Pages)
- **CLI**: `bionexus ivn {status | verify | build-ledger | register-dataset | register-lab-study | register-review | verify-review | freeze-profile | authorize}`

## The Moat That Deepens Over Time (Asset Transformation)

The IVN transforms verification from an internal compliance check into a **public, append-only, cryptographically signed asset**.
Algorithms and computational heuristics can be cloned overnight; an immutable, timestamped ledger of multi-center biological holdouts,
frozen negative results, independent lab replications, and blinded peer reviews **cannot be copied**.

Publishing an **honest, empty ledger with clear recruitment slots** ("空账本 + 明确的填法") functions as an active Request for Validation (RFV)
recruitment tool across four community tracks:

1. **Track 1: Independent Dataset Provider** (`.github/ISSUE_TEMPLATE/5_ivn_dataset_submission.yml`)
2. **Track 2: External Laboratory Replication** (`.github/ISSUE_TEMPLATE/6_ivn_external_lab_study.yml`)
3. **Track 3: Blinded Non-Author Peer Review** (`.github/ISSUE_TEMPLATE/7_ivn_reviewer_attestation.yml`)
4. **Track 4: Calibration Profile Freeze** (Held-out context threshold locking)

## The quota

Per flagship capability (`scrna.pseudobulk_de`, `scrna.annotation_evidence`,
`spatial.inference_validity`):

```
>= 3 independent datasets  x  >= 2 external labs  x  >= 1 non-author reviewer
```

with capability-specific depth requirements:

| Flagship | Additional depth requirement |
|---|---|
| `scrna.pseudobulk_de` | counted datasets must be donor-aware |
| `scrna.annotation_evidence` | counted datasets must span **cross-disease**, **cross-tissue**, and **cross-technology** contexts (>= 2 distinct each) |
| `spatial.inference_validity` | every counted dataset must carry **independent pathology-annotation or segmentation truth** (provider independent of the authors, blinded to BioNexus outputs) |

## What counts (fail-closed rules)

**Independent datasets** count only when they are not author-associated, are
`VERIFIED`, carry a hash-locked preregistration and a hash-bound report whose
SHA-256 digests match the on-disk files *at assessment time*, and satisfy the
capability depth requirement above. A negative study outcome — such as the
frozen pseudobulk negative results — remains valid executed evidence; it is
recorded and displayed, never promoted or dropped.

**External labs** count only as `VERIFIED` studies with a signed independence
declaration, a recorded agent host, a hash-bound capsule artifact, a dataset
that itself counts, and at least 2 distinct institutions. A registered
framework or an empty lab slot never counts.

**Non-author reviews** count only when the reviewer is absent from the
registry's author roster (an empty roster means non-authorship cannot be
established, so no review counts), a two-phase pre-output blinding record is
bound, an attestation id is recorded, and both the reviewer artifact and the
separate maintainer verification receipt match their SHA-256 digests. Pending
reviewer slots and review artifacts without a verification receipt never
count.

Every quota re-verification recomputes artifact digests from disk. Trust-on-
write is forbidden: editing an artifact after registration excludes the
entity instead of silently keeping the credit.

## Calibration freeze on held-out contexts

A threshold/calibration profile may only issue a positive warrant in a
context its frozen held-out evidence actually covers
(`src/bionexus/calibration_freeze.py`):

1. Only an `APPROVED` profile with empty `validation_issues()` can be frozen
   (a CANDIDATE profile — including anything produced by automatic fitting —
   never freezes).
2. The freeze hash-locks the exact canonical profile to explicit held-out
   contexts (`disease` / `tissue` / `platform` / `technology` fingerprints
   bound to dataset digests, `partition = "validation"`). Freezing with no
   held-out context is refused.
3. `bionexus ivn authorize` is the fail-closed gate: `AUTHORIZED` requires an
   intact freeze for the exact profile version plus a covered context.
   Everything else — unapproved profile, no freeze, post-freeze profile edit
   (`FREEZE_MISMATCH`), or a context outside the frozen scope — refuses.
4. The packaged calibration registry ships zero APPROVED profiles, therefore
   zero profiles are frozen and the gate refuses by default. This is the
   honest state; it changes only when real approved-and-frozen evidence
   exists.

## Using the CLI

```bash
# Assess every flagship against the network quota + OPEN_QUESTIONS blockers
bionexus ivn status

# Recompute every recorded artifact hash (drift check)
bionexus ivn verify

# Compile and generate the public standalone HTML ledger (GitHub Pages portal)
bionexus ivn build-ledger --output docs/ivn/index.html

# Register new evidence (templates in validation/ivn/templates/)
bionexus ivn register-dataset     --payload validation/ivn/templates/INDEPENDENT_DATASET.template.json
bionexus ivn register-lab-study   --payload validation/ivn/templates/EXTERNAL_LAB_STUDY.template.json
bionexus ivn register-review      --payload validation/ivn/templates/INDEPENDENT_REVIEW.template.json
#   registration refuses author-roster overlap for reviews and computes
#   artifact digests from disk; registration alone never satisfies a quota.

# Governed review promotion; validates the reviewer-controlled v3 artifact,
# two-phase blinding lock, immutable commit, disclosures, and signature, then
# emits a separate verification receipt. It does not endorse the verdict.
bionexus ivn verify-review --review-id BN-IVN-REV-001 \
    --expected-commit FULL_40_CHARACTER_COMMIT \
    --verified-by "named governance reviewer"

# Freeze an APPROVED calibration profile to its held-out contexts
bionexus ivn freeze-profile --profile-json profile.json --held-out-json contexts.json \
    --freeze-id F-001 --frozen-by release-governance

# Fail-closed authorization gate for one context
bionexus ivn authorize --profile-json profile.json --context-json context.json
```

## Relation to certification and OPEN_QUESTIONS

The IVN can only ever *raise* a certification criterion above its static
baseline (`certification.py` merges IVN evidence for `cross_host_test` and
`external_reviewer` only when the corresponding quota is fully satisfied by
hash-verified entities). While quotas are unmet, certification output is
byte-identical to the static evidence records.

The network derives the four blockers recorded in
[`docs/context/OPEN_QUESTIONS.md`](context/OPEN_QUESTIONS.md) from evidence:

| Blocker | Derived from | State at seed |
|---|---|---|
| No approved empirical calibration profiles | approved profiles that are also frozen on held-out contexts | open (zero frozen) |
| Annotation and spatial real-data validation is missing | per-capability dataset + coverage + independent-truth gaps | open (annotation 2/3 + coverage gaps; spatial 0/3 without independent truth) |
| Cross-host and independent review are incomplete | verified lab studies and non-author reviews per capability | open (0/2 labs, 0/1 reviewers everywhere) |
| External adoption and governance are not established | signed governance council records (cannot be synthesized by this schema) | open by construction |

## Current assessed state (post-rc3 baseline)

```
[scrna.pseudobulk_de]          3/3 datasets (frozen negative results) | 0/2 labs | 0/1 reviewers
[scrna.annotation_evidence]    2/3 datasets | cross-disease 1/2 | cross-tissue 1/2 | cross-technology 2/2 | 0/2 labs | 0/1 reviewers
[spatial.inference_validity]   0/3 datasets (no independent pathology/segmentation truth yet) | 0/2 labs | 0/1 reviewers
```

This is the work program, not a scorecard: cross-disease/tissue/technology
annotation cohorts, a full public spatial cohort with independent pathology
or segmentation truth, two external labs and one non-author reviewer per
flagship, and held-out-frozen calibration profiles are all outstanding.
