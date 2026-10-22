# Trust-chain correction for the unreleased working candidate

The September 19, 2026 correction withdraws unsupported authority from local
development material. This is an implementation correction, not an external
scientific review, new experiment, laboratory acceptance, or release approval.

| Material | Correct evidence ceiling |
|---|---|
| BN-PB-IV-006 | Selected gene-label proxy on historical GSE96583 output, with synthetic comparison/null controls; no demonstrated empirical FDR or causal benefit |
| BN-ANN-IV-004 | Same-dataset antibody-gating proxy; no FACS adjudication, independently verified blinding, or held-out calibration |
| BN-SP-IV-002 | Tiny real-instrument format example with synthetic labels; no pathology ground truth or measured biological artifact discrimination |
| MULTI_LAB_DOSSIER | No independently executed second-host receipt established |
| SCIENTIFIC_REVIEW | Pending reviewer roles, zero completed independent reviews |
| Rule holdout/calibration/ladder reports | Developer-case demonstrations; labels, confidence values and a weak baseline do not establish independent calibration or method superiority |

Original bytes, SHA-256 digests and correction records are retained under
`review/trust-restoration-2026-09-19/`. Retracted IVN records point to the
preserved original files with their unchanged original digests. Corrected
public views are withdrawal notices; they are not attributed to a new
scientific execution. Existing negative studies remain unchanged.

The evidence index enforces fixed development ceilings even when an input
report self-declares PASS or APPROVED. These five records have no promotion
edges. Flagship independent-ground-truth, external-host and external-review
criteria remain false. `VALIDATED` is an internal engineering tier;
`scientific_authorization` remains `NONE`.

Cryptographic integrity and scientific authority are separate. Legacy v1
signatures are hash-only. v2 requires its cryptographic fields, but a valid
signature under a supplied public key does not identify a real reviewer.
Nextflow warrants require run and file binding, successful execution metadata,
and validator success; unit tests mocking that validator do not prove native
Nextflow deployment.

Data import defaults to UNKNOWN. Declare a classification explicitly when it
is known. UNKNOWN cannot authorize failure-report transmission. Exchange
acceptance reparses the exported product and verifies actual file bytes.
Migration validates the old schema and requires genuine recorded digests;
it cannot recover missing source bytes or manufacture a digest from text.

The archived manuscript under `manuscript/biorxiv_submission_2026-08-22/`
is a historical draft with mixed version snapshots. It is not the current
submission candidate. Any claim of independent validation, calibration,
external review, adoption or method superiority must be rebuilt against
subsequent independent evidence before submission. The historical manuscript
is preserved rather than silently rebound to this candidate.

Local acceptance results, skipped checks and the frozen working-candidate
identity are reported separately. Existing public rc.8 release/CI results do
not validate the new uncommitted working tree.
