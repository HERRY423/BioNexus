# BNS-011: Scientific Failure Taxonomy

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/failures.py`, refusal triggers, evidence cards, benchmark suites
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

BioNexus is not "providing bioinformatics knowledge" — it is building the
**failure ontology for agentic computational biology**. Every deterministic
refusal, ceiling clamp, and degraded advisory in the runtime traces back to a
taxonomy ID (`BN-Fxxx`). This ontology is a durable asset: prompts, skills, and
endpoints can be copied; a validated failure taxonomy with detection rules and
benchmark coverage cannot.

## 2. Taxonomy records

- **BNS-FT-001** Every failure mode MUST be a first-class record with:
  `failure_id` (`BN-Fxxx`), `name`, `definition`, canonical `example`,
  `affected_capabilities`, `detection_rule`, `required_behavior`,
  `acceptable_degradation`, and `benchmark_cases`.
- **BNS-FT-002** Failure IDs are stable and never reused; new modes append
  (the current series is BN-F001..BN-F012).
- **BNS-FT-003** `required_behavior` MUST use the fail-closed vocabulary
  (BNS-AD-014): REFUSE, ABSTAIN, BLOCK CLAIM, DEGRADE WITH DISCLOSURE,
  CAP EVIDENCE LEVEL. "Warn and continue silently" is not an acceptable
  required behavior.
- **BNS-FT-004** `acceptable_degradation` MUST name what MAY still be reported
  under the failure condition (e.g. exploratory rankings without inferential
  labels). Anything not named is prohibited.
- **BNS-FT-005** `benchmark_cases` MUST reference real benchmark case IDs; a
  mode with no exercisable case MUST be flagged `open_gap` and tracked in the
  frontier philosophy (honest gaps, never hidden).

## 3. Current taxonomy (summary)

| ID | Name | Required behavior |
|---|---|---|
| BN-F001 | Assay-state confusion | REFUSE |
| BN-F002 | Pseudoreplication | REFUSE |
| BN-F003 | Unsupported annotation | BLOCK CLAIM |
| BN-F004 | Identifier mismatch | REFUSE (wired: router trap screen, BF-008/BF-025) |
| BN-F005 | Missing multiple-testing correction | CAP EVIDENCE LEVEL (wired: statistical warrant, BF-005) |
| BN-F006 | Invalid model assumption | BLOCK CLAIM |
| BN-F007 | Parameter instability | CAP EVIDENCE LEVEL (FRAGILE) |
| BN-F008 | Cross-database contradiction | CONFLICTED (wired: router trap screen, BF-016) |
| BN-F009 | Missing spatial provenance | REFUSE / DEGRADE WITH DISCLOSURE |
| BN-F010 | Backend degradation masquerading | DEGRADE WITH DISCLOSURE |
| BN-F011 | Claim inflation | BLOCK CLAIM |
| BN-F012 | Unexecuted maturity claim | CAP EVIDENCE LEVEL |

## 4. Runtime integration

- **BNS-FT-006** Refusal payloads and prevention decisions SHOULD carry the
  failure mode IDs they instantiate (`failures.classify_violation`), so hosts
  receive the ontology, not just a string.
- **BNS-FT-007** The taxonomy MUST provide the `known_failure_modes` criterion
  for capability certification (BNS-CF criterion 4): a capability is only
  VALIDATED when its failure modes are linked with detection rules.
- **BNS-FT-008** Benchmark suites SHOULD grow by attaching cases to open-gap
  failure modes; closing an open gap is a changelog-recorded event.

## 5. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-FT-001..004 | `tests/unit/test_failure_taxonomy.py` (record shape, vocabulary) |
| BNS-FT-005 | benchmark case ID resolution against `load_eval_cases()` |
| BNS-FT-006 | `failclosed.PreventionDecision.failure_mode_ids` |
| BNS-FT-007 | `certification` structural cross-check for known_failure_modes |
