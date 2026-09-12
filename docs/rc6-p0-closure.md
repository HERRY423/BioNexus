# Post-rc6 P0 closure and migration

Scope: the four P0 items in the review dated 2026-09-12: negation warrant,
execution-binding edge cases, IVN Pages and GA support policy. This change does
not release rc7/GA or establish independent review, external adoption or
cross-host conformance. Local checks apply to the working tree, not the rc6 tag.

## Scientific claims

A scoped limitation such as `We cannot prove that X causes Y` is allowed as a
descriptive limitation. Its evidence ceiling is `UNASSESSED`, even when the
language check is satisfied. A disclaimer cannot license another assertion in
the same compound text; submit separate claims when scope is ambiguous.

`X does not cause Y`, `no effect`, `no difference`, equivalence and
non-inferiority are not established by a nonsignificant DE test, cohort size or
a `perturbation=True` flag. The current EvidenceProfile has no verified
endpoint/margin/interval/test contract for those claims and returns an explicit
evidence gap. Their scientific review needs the appropriate prespecified
endpoint, margin, uncertainty and test. This change does not implement a new
equivalence-testing capability or substitute agent approval for scientific review.

An accurate statement that a named gene was not significant, or that the
supplied table contains no significant genes at the audited FDR threshold,
remains usable. It makes no assertion of biological absence. Text recognition
is deterministic and bounded; it is not a complete natural-language proof system.

Extreme nonzero p-values remain a diagnostic signal. With complete consistent
donor execution inputs, BFA-001c is advisory. Neither tiny p-values nor matching
receipt metadata establish effect magnitude or biological validity.

## Execution record migration

Two fields such as `statistical_unit=donor` and `method=pydeseq2` no longer
produce `ROBUST_PASS`. The required execution-binding check now needs:

| Field/input | What is checked |
|---|---|
| `statistical_unit` (or `unit`) | Explicit `donor`, `sample` or `biological_replicate`; an aggregation substring cannot override a cell unit |
| `method` | Nonempty method; a recognized cell-ranking method cannot acquire donor-level status from metadata |
| `fit_status` | Explicit success (`SUCCESS`, `SUCCEEDED`, `CONVERGED`, `COMPLETED`, `PASS`, `PASSED`, `OK`); missing/unknown/failed states do not pass |
| `design` (or `formula`) | Bounded additive formula such as `~ condition` or `~ donor + condition`; unsupported complex formulas remain unverified |
| `design_matrix_columns` | Nonempty unique column names consistent with formula factors and the audited condition; numeric matrix rank and actual backend fitting are not authenticated here |
| `n_donors`, `donor_ids` | Positive integer and unique string IDs matching the observed donor metadata; this checks labels, not real human identity |
| `result_sha256` (or `receipt_result_sha256`) | Exactly 64 hex characters, nonzero, equal to the actual result file bytes; those same bytes must parse to the table being audited |
| Result input | A readable CSV/TSV result file; a DataFrame has no original-file bytes and cannot satisfy a file hash check |

Conflicting aliases, duplicate JSON keys, malformed flags and contradictory unit,
design or donor facts do not pass. Any required check with `ISSUE_FOUND` now
prevents overall success even without a separate high-severity finding. Missing
inputs remain `NEEDS_DATA`; contradictions remain visible and require revision.
DataFrame and ExecutionRecord object inputs are still accepted for inspection,
but missing file/receipt evidence is not silently synthesized.

`ROBUST_PASS` is the existing local audit status. The execution summary now
explicitly limits success to input consistency. The receipt producer, real
model execution, selected count layer, full statistical design and scientific
validity require their own evidence. Do not manufacture receipt fields to clear
this check; export the actual execution record with the result.

Historical bundles remain readable. Do not edit old assessments or re-hash
their manifests to appear current. Reassess affected claims in a new output
directory, retain the original package/version, and record why the outcome changed.

## IVN Pages

The rc6 [failed run](https://github.com/HERRY423/BioNexus/actions/runs/34620670777)
successfully built and verified the ledger. Its deployment annotation says:
`Tag "v1.0.0-rc.6" is not allowed to deploy to github-pages due to environment protection rules.`
The environment currently permits the `main` branch only.

The workflow now publishes Pages only from `main`, including a manual dispatch
on `main`. Tags and PRs still build and retain a verified ledger as a normal
workflow artifact. Pages write/OIDC permissions are scoped to deployment;
branch protections are preserved. Tag snapshots do not overwrite the current
public registry. Per-ref concurrency separates tag/PR checks from deployment.

After merging the fix, dispatch **IVN Public Ledger & GitHub Pages** on `main`,
require both jobs to succeed, and check the public ledger against that commit.
A subsequent release-tag run must build successfully and skip deployment.
Until those hosted runs finish, remote deployment of this change is unverified.

## GA support activation

[MAINTENANCE.md](../MAINTENANCE.md#core-1x-ga-support-policy) defines a proposed
12-month Core 1.x support window, latest-minor fixes, 90-day critical backports
within the window, scientific-rule change notices and 90-day EOL notice.
SECURITY.md and SUPPORT.md point to the same policy.

The first GA release must publish actual dates, named accepting maintainers,
release/security contact and scope. The contract remains **NOT ACTIVATED** until
that acceptance; writing this document does not invent maintenance capacity.

## Verification

The fixed core test list includes `test_rc6_p0_boundaries.py`. DE traceability
binds its counterexamples to BNS-FW-008 alongside existing positive cases.
Run the normal type, fixed coverage, DE traceability, unit and packaging gates.
Never lower coverage floors to accommodate new branches. Source tests, installed
wheel tests and hosted CI must be reported separately.
