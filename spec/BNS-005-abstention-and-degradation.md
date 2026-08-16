# BNS-005: Abstention & Degradation

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/intent_router.py`, `src/bionexus/contracts.py` (`refuse`), capability `RefusalTrigger`s
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

The most important output of a scientific agent is sometimes **"no"**. This document
norms when BioNexus MUST refuse, what a refusal MUST contain, and the narrower path
by which degraded execution is allowed at all.

## 2. Routing statuses

- **BNS-AD-001** Every request MUST resolve to exactly one routing status:
  - `PERMITTED` — scientifically valid, preconditions met, backend ready.
  - `NEEDS_DATA` — valid intent, essential metadata/artifacts missing; the runtime
    MUST enumerate the missing items (`missing_data_requests`).
  - `ABSTAIN` — a scientific invariant is violated; execution is prohibited.
  - `DEGRADED_ADVISORY` — permitted only with explicit Grade C degradation notice.

## 3. Mandatory refusals

- **BNS-AD-002** When any fatal `RefusalTrigger` fires, the runtime MUST return
  `ABSTAIN` with: the violated scientific rule, the trigger description, and an
  actionable remedy (BNS-CC-006/007). Refusals MUST be deterministic — same inputs,
  same refusal, same reasons.
- **BNS-AD-003** The refusal inventory MUST include at minimum: pseudoreplication
  (`missing_replicates`), count-scale violation (`normalized_matrix_only`,
  `normalized_input`), missing/degenerate spatial geometry, all-censored survival
  cohorts, unverified PVS1 mechanism, and unverified clinical diagnosis attempts.
- **BNS-AD-004** A refusal MUST NOT be scored as an agent failure in benchmarks when
  it is the expected behavior; conversely, executing a should-refuse analysis is an
  **unsafe invocation** and MUST be measured (target rate: 0.0%).
- **BNS-AD-005** Requests whose intent cannot be resolved MUST fall back to
  `NEEDS_DATA` orientation, MUST NOT guess a capability, and MUST NOT execute
  anything.

## 4. Degradation

- **BNS-AD-006** Degraded execution (heuristic in place of missing gold backend)
  MUST require explicit user consent (`allow_degraded`), and MUST only be offered
  for capabilities whose skill is not default-visible (BNS-EF-005/006).
- **BNS-AD-007** A degraded result MUST carry `ExecutionState.DEGRADED`, name the
  missing canonical backend in its evidence card, and synthesize maturity at most
  `FRAGILE`.
- **BNS-AD-008** Degradation advisories MUST NOT cascade silently: at most one
  degradation consent per invocation; downstream consumers of a degraded artifact
  MUST be able to detect its provenance (BNS-006).

## 5. Forbidden claims and abstention at the claim layer

- **BNS-AD-009** When a request asks a capability to produce a claim on its
  `forbidden_claims` list (BNS-CC-012) — e.g. causal cell-cell communication from
  Moran's I — the router MUST block or annotate the request and MUST provide the
  scientific reason (method measures autocorrelation, not mechanism).
- **BNS-AD-010** Clinical diagnosis, treatment recommendation, and CLIA/CAP-grade
  reporting are forbidden claims for every capability; outputs MUST carry the
  Research-Use-Only limitation (`RESEARCH_USE_ONLY`).
- **BNS-AD-011** Host agents SHOULD render refusal violations and remedies
  verbatim-class to the user rather than paraphrasing them; paraphrase drift is the
  most common source of lost scientific context. Users MAY re-request the same
  analysis after remedying the stated violations, and the runtime MUST re-evaluate
  from scratch — prior refusals MUST NOT be cached as permanent blocks.
- **BNS-AD-012** Refusal reasons SHOULD be traceable to the requirement IDs of this
  specification series (e.g. `BNS-II-002` for count-scale violations) so that hosts
  can cite the governing invariant.

## 6. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-AD-001 | `intent_router.route_scientific_intent`; eval `routing` |
| BNS-AD-002..005 | eval `refusal` + `adversarial`; metric `unsafe_invocation_rate` |
| BNS-AD-006..008 | eval `backend_failure` (DEGRADED_ADVISORY cases); `tests/unit/test_kernel_and_honesty.py` |
| BNS-AD-009 | `abi.audit_claims_against_abi`; frontier calibration track |
| BNS-AD-010 | `claim_checker._REGULATORY_PATTERNS`; eval L2 `host_agent_claim` |
