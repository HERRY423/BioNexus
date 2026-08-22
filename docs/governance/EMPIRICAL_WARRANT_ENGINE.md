# BioNexus Empirical Warrant Engine

BioNexus no longer interprets annotation or spatial robustness scores with
universal thresholds.
The runtime resolves a reviewed calibration profile using this key:

```text
(metric, tissue, platform, reference, task, evidence_source)
```

Only then does it compare the score with the profile's threshold. The decision
record includes the registry hash, profile ID and version, profile hash,
comparison direction, threshold, and full declared context.

## Runtime behavior

| Situation | Resolution | Maximum annotation warrant |
|---|---|---|
| Exact valid `APPROVED` profile | `RESOLVED` | Determined by all evidence classes |
| Missing profile context | `INSUFFICIENT_CONTEXT` | `TENTATIVE` |
| No matching regime | `NO_MATCH` | `TENTATIVE` |
| Candidate or legacy profile only | `PROFILE_NOT_APPROVED` | `TENTATIVE` |
| Reference-domain mismatch | `DOMAIN_MISMATCH` | Mapping score contributes no identity support |
| Conflicting equal-specificity profiles | `AMBIGUOUS` | `TENTATIVE` |
| Rare or open-set population | not forced through resolver | `ABSTAIN` |
| Continuous developmental state | resolved metrics retained | discrete identity capped at `TENTATIVE` |

There is deliberately no fallback from these states to the former annotation values
`0.60`, `0.20`, `0.70`, or `0.80`.

The same resolver now governs every numeric diagnostic emitted by the
`spatial.inference_validity` v2 alternative-explanation battery. A computed
retention score or permutation p-value without a matching approved spatial
profile remains `UNTESTED`; computation alone is not empirical warrant.

## Profile lifecycle

1. Define the target regime and outcome that constitutes a scientifically
   supported annotation.
2. Split labelled observations into calibration and held-out validation
   partitions before threshold fitting.
3. Fit a threshold against an explicitly declared operating criterion. The
   built-in fitter maximizes coverage subject to a one-sided Wilson precision
   lower bound supplied by the study protocol.
4. Retain the result as `CANDIDATE`, including the observation hash and fit
   receipt. Automated fitting cannot activate a profile.
5. Obtain accountable human review and attach independently validated evidence.
6. Publish a new immutable `APPROVED` profile version. Runtime decisions may now
   resolve it.
7. If evidence later shows a boundary failure, retire or split the regime; do
   not mutate the active threshold in place.

## Current evidence boundary

The packaged registry is intentionally `incomplete_not_claim_ready`. It records
the former global values as `LEGACY_UNCALIBRATED` migration entries, with zero
approved profiles. This is an honest implementation boundary: the engine and
contracts are executable, while real tissue/platform/reference calibration
studies and independent approvals remain external scientific work. It also has
zero approved real spatial profiles; the spatial battery's synthetic contract
fixtures are explicitly excluded from the packaged registry.

The SHA-256 records in this layer support reproducibility and tamper-evident
identification. They are not 21 CFR Part 11 signatures, GxP records, CLIA
validation, or proof that a benchmark is scientifically independent.
