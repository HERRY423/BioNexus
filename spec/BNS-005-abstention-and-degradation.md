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
  - `EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN` — a frontier capability was matched
    but the caller has not opted in (`allow_frontier=False`); execution is blocked
    until explicit opt-in (BNS-010 runtime isolation).

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
  MUST require explicit user consent (`allow_degraded`). Backend readiness binds
  to the capability, never to the skill: for canonical capabilities a missing
  canonical backend is a strict refusal (`ABSTAIN`/REFUSE) regardless of consent;
  `DEGRADED_ADVISORY` is reachable only for frontier capabilities under explicit
  frontier opt-in (`allow_frontier`) plus degradation consent (BNS-EF-005/006,
  BNS-010).
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

## 6. Fail-closed philosophy: `prevent_invalid_run()`

*Knowing when not to compute is a scientific capability.* The platform's most
scarce API is not `run()` — it is `prevent_invalid_run()`
(`src/bionexus/failclosed.py`).

- **BNS-AD-013** The runtime MUST expose `prevent_invalid_run()` as the single
  canonical fail-closed gate: it evaluates a requested run against the
  scientific contract BEFORE any compute and returns a prevention verdict
  (`PreventionDecision`) with prevention kind, action, reason, failure-mode IDs
  (BNS-FT-006), remedies, and the underlying routing decision. Hosts SHOULD
  call it before execution and MUST honor its verdict; an unsupervised `run()`
  of a prevented request is a BNS-HC-002 conformance violation.
- **BNS-AD-014** The gate MUST implement the closed-by-default table:

  | Condition | Prevention kind | Action |
  |---|---|---|
  | missing evidence | `MISSING_EVIDENCE` | ABSTAIN (request data) |
  | invalid input | `INVALID_INPUT` | REFUSE |
  | backend unavailable (canonical) | `BACKEND_UNAVAILABLE` | REFUSE |
  | backend unavailable (frontier, opt-in + explicit fallback) | `BACKEND_UNAVAILABLE` | DEGRADE WITH DISCLOSURE |
  | frontier capability, no opt-in | `ASSUMPTION_VIOLATED` | REFUSE (`EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN`) |
  | assumption violated | `ASSUMPTION_VIOLATED` | BLOCK CLAIM |
  | claim beyond warrant | `CLAIM_BEYOND_WARRANT` | BLOCK CLAIM |
  | external validation absent | `EXTERNAL_VALIDATION_ABSENT` | CAP EVIDENCE LEVEL |

  Backend readiness binds to the capability, never to the skill: no default/legacy
  skill classification may decide whether a missing backend matters.

- **BNS-AD-015** Every prevention row MUST terminate in a blocked or disclosed
  state; there is NO row that resolves to silent execution. A clean request
  resolves to `RUN PERMITTED` only after every row fails to match.

## 6. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-AD-001 | `intent_router.route_scientific_intent`; eval `routing` |
| BNS-AD-002..005 | eval `refusal` + `adversarial`; metric `unsafe_invocation_rate` |
| BNS-AD-006..008 | eval `backend_failure` (DEGRADED_ADVISORY cases); `tests/unit/test_kernel_and_honesty.py` |
| BNS-AD-009 | `abi.audit_claims_against_abi`; frontier calibration track |
| BNS-AD-010 | `claim_checker._REGULATORY_PATTERNS`; eval L2 `host_agent_claim` |
| BNS-AD-011..012 | Host integration guidance (SHOULD-tier) |
| BNS-AD-013..015 | `tests/unit/test_failclosed.py` (all six rows); `bionexus prevent` CLI |
