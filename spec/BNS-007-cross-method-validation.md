# BNS-007: Cross-Method Validation

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/integrity.py` (`audit_parameter_stability`), ABI `validation` block, L3 stability suites
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

A single run of a single method at a single parameter point is the weakest form of
computational evidence. This document norms how BioNexus escalates (or refuses to
escalate) maturity claims based on parameter sensitivity and cross-method concordance.

## 2. Parameter sensitivity

- **BNS-XM-001** Capabilities whose results depend on tunable parameters (clustering
  resolution, KNN graph k, number of HVGs) MUST declare `parameter_sensitivity:
  required` in their ABI validation block.
- **BNS-XM-002** Where required, results MUST be perturbation-audited across a
  declared parameter sweep (`audit_parameter_stability`) with a similarity metric
  (default: Adjusted Rand Index for labelings).
- **BNS-XM-003** A stability audit below the capability's threshold (default ARI
  >= 0.80 across the sweep) MUST cap maturity at `FRAGILE` — parameter-sensitive
  findings MUST NOT be reported as `SUPPORTED` or above.
- **BNS-XM-004** Stability audits MUST record the sweep definition (parameters,
  ranges, steps) in provenance (BNS-PV-003).

## 3. Cross-method concordance

- **BNS-XM-005** Capabilities with multiple defensible algorithms SHOULD declare
  `cross_method: recommended` (or `required` where a second gold method exists) and
  SHOULD run the primary plus at least one alternative (e.g. Moran's I vs Geary's C
  for spatial autocorrelation; Wald vs LRT for DE).
- **BNS-XM-006** Concordance MUST be evaluated at the finding level (e.g. rank
  overlap of top-k findings), not at the summary-statistic level. Discordant
  top-findings MUST surface `DimensionGrade.CONFLICTED` and maturity `CONFLICTED`
  (BNS-EM-005).
- **BNS-XM-007** Agreement between a gold method and a heuristic MUST NOT be cited
  as cross-method concordance; heuristic agreement is execution-fidelity information
  only (BNS-003).

## 4. External validation

- **BNS-XM-008** `REPLICATED` maturity REQUIRES independent external evidence:
  orthogonal datasets, orthogonal assays, or gold-standard truth sets (e.g. ClinVar
  expert-reviewed controls for variant classification). No capability MAY self-certify
  replication from internal consistency alone.
- **BNS-XM-009** External validation sources MUST be recorded with identifiers and
  access dates in provenance; truth-set versions matter (BNS-PV-002).

## 5. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-XM-001..004 | L3 `clustering_stability` suite; `tests/unit/test_cluster_profile.py` |
| BNS-XM-005..007 | ABI validation blocks; frontier calibration track (concordance cases) |
| BNS-XM-008..009 | `evals/datasets/benchmarks/clinvar_controls.json` (variant truth set); `tests/unit/test_golden_biology.py` |
