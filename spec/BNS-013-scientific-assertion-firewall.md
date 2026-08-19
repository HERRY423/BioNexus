# BNS-013: Scientific Assertion Firewall

**Status**: Active | **Version**: 1.1 | **Supersedes**: none
**Applies to**: `src/bionexus/preflight.py`, `src/bionexus/analysis_audit.py`, `src/bionexus/verification.py`, `src/bionexus/cli.py`
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

BioNexus's defensible product claim is not "BioNexus can run analyses" — it is:

> **BioNexus tells you what the evidence warrants: it caps claims that exceed
> their evidence, and blocks execution only where a true invariant is violated.**

The Scientific Assertion Firewall productizes the blocking and capping surface
of that claim as three high-frequency
entry points around the researcher's existing toolchain (Scanpy, Seurat,
Bioconductor, Claude, Codex, Cursor — BioNexus does not replace any of them):

| Entry point | When | Question answered |
|---|---|---|
| `bionexus preflight` | before the analysis | should this analysis run at all? |
| `bionexus audit` | on the analysis artifact | does this notebook/script stand up? |
| `bionexus verify` | on the final results | is this conclusion warranted by its evidence? |

## 2. Requirements

- **BNS-FW-001** The firewall MUST expose exactly three user entry points —
  `preflight` (before compute), `audit` (on the analysis artifact), and
  `verify` (on final results) — each invocable from the CLI without a host
  agent.
- **BNS-FW-002** The preflight decision vocabulary MUST be the fail-closed
  table (BNS-AD-014) re-used verbatim: ABSTAIN (request data), REFUSE,
  DEGRADE WITH DISCLOSURE, BLOCK CLAIM, CAP EVIDENCE LEVEL, RUN PERMITTED.
  The firewall MUST NOT invent new decision words.
- **BNS-FW-003** `preflight` MUST NOT execute the requested analysis; its
  output is a decision about whether the analysis should be run (it may read
  input data to establish the data state).
- **BNS-FW-004** `preflight` MUST render the seven-section output contract —
  INTENT, DATA STATE, RISKS, DECISION, ALLOWED, FORBIDDEN CLAIM, REMEDY — and
  MUST provide a machine-readable JSON projection of the same content.
- **BNS-FW-005** Exit codes MUST encode the verdict: `0` the analysis may
  proceed (including CAP EVIDENCE LEVEL and DEGRADE WITH DISCLOSURE), `1`
  refused or claim-blocked, `2` missing evidence (data requested).
- **BNS-FW-006** The FORBIDDEN CLAIM section MUST be derived mechanically
  from the matched capability's forbidden-claim catalog and evidence ceiling
  (BNS-CC-012/BNS-CC-013); it MUST NOT be hand-authored per invocation.
- **BNS-FW-007** Under a prevented decision, the ALLOWED section MUST be
  populated only from the failure taxonomy's `acceptable_degradation`
  entries (BNS-FT-004); anything not named there is prohibited.
- **BNS-FW-008** Data-state checks that cannot be verified in the current
  environment MUST be rendered distinctly from checks that failed; an
  unverifiable state MUST NOT be displayed as a pass.
- **BNS-FW-009** `audit` on a code artifact (notebook or script) MUST emit
  findings that each cite a rule id (BFA-nnn), a taxonomy failure id
  (BN-Fxxx, BNS-FT-002), the evidence location, and a remedy; severity
  vocabulary is FATAL and ADVISORY.
- **BNS-FW-010** The static audit rules are heuristics with false negatives
  by construction: `audit` MUST carry the disclaimer that the absence of
  findings is NOT proof of validity, and MUST NOT return a "certified clean"
  verdict.
- **BNS-FW-011** `verify` MUST re-resolve every claim in the supplied
  Claim–Evidence Ledger fail-closed per BNS-CL-005 and MUST cross-check the
  resolved status against the capability's evidence ceiling (BNS-CC-013).
- **BNS-FW-012** `verify` MUST flag claim statements whose causal or
  mechanistic language exceeds the warrant of the underlying evidence class
  and MUST surface the capability's forbidden-claim catalog as the
  "not warranted" list.
- **BNS-FW-013** `verify` MUST exit non-zero when any claim resolves ABSTAIN
  or CONFLICTED or carries unwarranted causal language; honest intermediate
  maturities (PRELIMINARY, FRAGILE) MUST NOT fail verification by themselves.
- **BNS-FW-014** Hosts SHOULD surface firewall exit codes and verdict
  sections verbatim in their own output; a host MAY add context around them
  but MUST NOT summarize a REFUSE as a warning.

## 3. Output contract example (normative shape)

```text
=== BioNexus Preflight ===

INTENT
Differential expression between treatment and control  (scrna.pseudobulk_de)

DATA STATE
[OK] matrix state: raw integer-like counts present
[!!] biological samples: 8 donors across 2 conditions; minimum 2 donors in a group

RISKS
[!!] BN-F006: condition strongly confounded with 'donor' (1:1 design)

DECISION
ABSTAIN -> REFUSE
  ...

ALLOWED
- at most: Exploratory within-sample marker ranking, explicitly not condition DE

FORBIDDEN CLAIM
- causal_interaction: ...
- maturity above 'SUPPORTED' without external validation

REMEDY
- Add biological replicates that decouple condition from 'donor' ...
```

## 4. Verification hooks

- `tests/unit/test_preflight.py` — output contract, exit codes, trap surfacing.
- `tests/unit/test_analysis_audit.py` — rule families BFA-001..BFA-013.
- `tests/unit/test_result_verify.py` — ledger verification semantics.
- BioFailureBench (BNS-014) exercises the router the firewall builds upon.
