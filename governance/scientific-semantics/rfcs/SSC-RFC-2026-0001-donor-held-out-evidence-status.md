# SSC-RFC-2026-0001: Register donor-held-out and public-biological-cohort evidence-status vocabulary

- **Status**: `DRAFT` (lifecycle per `../RFC_PROCESS.md`; only an operational SSC
  may move this past `COUNCIL_REVIEW`)
- **Authors**: interim draft steward (BioNexus maintainer side) — *this RFC is
  explicitly seeking a non-author co-author and an external adjudicator*
- **Created**: 2026-08-30
- **Target**: Scientific Semantic Conventions registry, evidence-status vocabulary
- **Decision class**: Council decision (interim stewards cannot accept it)

## 1. Producer and consumer use cases

Producers: flagship validation studies emit result ceilings. BN-ANN-IV-004
minted `CANDIDATE_EXTERNAL_REFERENCE_DONOR_HELD_OUT` and BN-SP-IV-002 minted
`REAL_TISSUE_TECHNICAL_ACCEPTANCE_PUBLIC_BIOLOGICAL_COHORT` for ceilings that
existing vocabulary could not express precisely (a positive result that is
donor-held-out and threshold-blinded by protocol, yet not independently
reviewed; real-tissue technical acceptance on a public biological cohort that
is not independent ground truth).

Consumers: host agents and downstream dashboards that must render "how far did
this study actually get" without reading study JSON. Today those consumers
either over-generalize (`VALIDATED`) or drop the distinction.

## 2. Exact scientific meaning and out-of-scope interpretations

- `CANDIDATE_EXTERNAL_REFERENCE_DONOR_HELD_OUT`: all preregistered endpoints
  passed on donors never used for threshold derivation, with the threshold
  selected on development donors of the same cohort under a locked protocol.
  Out of scope: independent blinded validation (different implementer),
  cross-host conformance, biological truth, certification progress by itself.
- `REAL_TISSUE_TECHNICAL_ACCEPTANCE_PUBLIC_BIOLOGICAL_COHORT`: deterministic
  manufactured-confounder controls pass in the expected direction on an
  authentic public biological cohort. Out of scope: segmentation accuracy
  against independent pathology truth; biological validity of any conclusion
  drawn from the cohort.

Both are evidence *provenance* descriptors. Neither raises or lowers an
EvidenceCard maturity ladder value.

## 3. Regime limitations and risks of semantic overclaim

The main risk is "held-out donor" being read as "blinded": same-implementer
blinding is partial by construction (the BN-ANN-IV-004 access disclosure states
holdout category names were visible during reconnaissance). Mitigation: the
vocabulary entry must carry the mandatory qualifier that donor-held-out status
never implies independent blinding.

## 4. Namespace collision and external-standard analysis

No collision with existing SSC status terms or the certification tiers
(CERTIFIED / VALIDATED / EXPERIMENTAL / CONNECTOR-ONLY): these descriptors sit
below tier language and never map to a tier by themselves. No GA4GH/RO-Crate
counterpart exists; the terms stay BioNexus-namespaced (`urn:bionexus:*`).

## 5. Compatibility classification and migration plan

Additive. Existing reports that used `CANDIDATE_EXTERNAL_REFERENCE_NONBLINDED`
(BN-ANN-IV-003) are unchanged. Migration: none required; producers MAY adopt
the new terms for new studies only.

## 6. Language-neutral registry/schema patch

Sketch (binding diff deferred to Council review): add two closed-vocabulary
strings to the evidence-status registry with `implies_independent_blinding:
false`, `implies_independent_ground_truth: false`, and verbatim
render-as-written rules (never render as WARRANTED).

## 7. Conformance fixtures from at least two implementation paths

- Path A: `validation/annotation/studies/BN-ANN-IV-004/REPORT.json` (status field).
- Path B: `validation/spatial/studies/BN-SP-IV-002/REPORT.json` (status field).
- A third negative fixture (a study that must NOT carry either term) is required
  before `PUBLIC_REVIEW` ends.

## 8. Institutional impact and accessibility review

Terms render in reports and dashboards; plain-language glosses are required in
the registry entry (done in §2) and must survive truncation in UI badges
(short forms: `DONOR_HELD_OUT`, `PUBLIC_COHORT_TECHNICAL`).

## 9. Conflicts and funding disclosures

Author is the BioNexus maintainer (interim steward). No funding. The RFC
cannot reach `ACCEPTED` until a non-author co-author and an operational
Council exist — see `../ONBOARDING.md`.

## 10. Proposed decision class and review period

Decision class: **Council decision** (namespace addition). Proposed review
period: 30 days public review once the Council has its first external member;
until then this RFC remains `DRAFT` and implementation experiments may proceed
without implying acceptance.
