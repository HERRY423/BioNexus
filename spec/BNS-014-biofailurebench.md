# BNS-014: BioFailureBench — the Scientific Trap Corpus

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `evals/datasets/biofailurebench.yaml`, `evals/biofailurebench.py`, `evals/runner.py`
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

BioFailureBench does not test "can the AI answer biology questions".
It tests:

> **Does the AI realize an analysis should not have been run — or that a
> conclusion does not stand?**

Software is easy to copy. Skills are easy to copy. Prompts are easier. A
scientific trap corpus with ground truth, maintained by computational biology
experts and wired into the failure taxonomy (BNS-011), is the durable asset.
The corpus is host-agnostic: Claude, Codex, Cursor, Biomni, and future agents
run the identical suite (`bionexus eval --suite biofailurebench`).

## 2. Requirements

- **BNS-BF-001** Every corpus record MUST be a complete trap with eight
  required fields, mapped onto the eval schema: `data` (data_metadata plus
  data context in the prompt), `intended analysis` (prompt), `hidden flaw`
  (failure_mode taxonomy id + description), `expected detection`
  (expected_status / expected_violations / expected_maturity),
  `allowed computation` (allowed_computation), `forbidden claim`
  (forbidden_claim), `remediation` (required_remedies), and `reference`.
- **BNS-BF-002** Trap IDs are stable `BF-nnn` and never reused; a trap's
  hidden flaw MUST NOT be silently changed (retire the trap and add a new one).
- **BNS-BF-003** A gating trap (no `known_limitation` flag) MUST pass
  deterministically in the reference environment; a trap that cannot pass
  deterministically MUST be marked frontier (`known_limitation: true`) with a
  description prefixed `FRONTIER TRAP`, following the honest calibration
  track (BNS-LC-004).
- **BNS-BF-004** Every gating trap's `failure_mode` MUST resolve into the
  failure taxonomy (BNS-FT-002), and the corpus MUST exercise every taxonomy
  mode; a new taxonomy mode lands together with at least one trap, or the
  mode is an open gap that MUST be visible (BNS-FT-005).
- **BNS-BF-005** The corpus MUST contain at least one positive control
  (`failure_mode: NONE`): a methodologically sound request that passes cleanly
  with its claimed warrant intact. An all-refusal benchmark is dishonest by
  construction.
- **BNS-BF-006** The corpus MUST be host-agnostic: identical traps execute
  through the standard eval runner for any provider (replay, OpenAI,
  Anthropic, Gemini) with no per-host variants of the ground truth.
- **BNS-BF-007** Corpus integrity MUST be machine-checked
  (`bionexus bench validate`): field completeness, taxonomy linkage,
  gating/frontier prefixes, ID resolution, and mode coverage; an invalid
  corpus MUST fail CI.
- **BNS-BF-008** Frontier traps that become deterministic graduate into the
  gating set (BNS-LC-005); graduation is recorded by removing the
  `known_limitation` flag, never by weakening the expectation.
- **BNS-BF-009** Growth direction: the corpus grows toward 100–300
  expert-maintained traps; quantity MUST NOT be reached by duplicating the
  same hidden flaw under different wording (each trap teaches a distinct
  detection). Contributors SHOULD document the detection a new trap teaches;
  trivial rewordings of existing traps MAY be rejected in review.

## 3. Current corpus state (honest)

26 traps: 23 gating (all passing deterministically), 3 frontier (honest known
limitations: insufficient-power boundary, doublet-driven annotation,
negative-marker-absent verdict wiring). Coverage spans all twelve taxonomy
modes BN-F001..BN-F012, closing the three formerly-open gaps (BN-F004
identifier mismatch, BN-F005 missing FDR, BN-F008 cross-database
contradiction) with wired detection.

## 4. Verification hooks

- `evals/biofailurebench.py::validate_corpus` — schema and coverage (BNS-BF-001/004/007).
- `tests/unit/test_biofailurebench.py` — corpus contract and runner wiring.
- `tests/unit/test_failure_taxonomy.py` — benchmark-case references resolve (BNS-FT-005).
- CI eval job — gating traps must pass in the reference environment.
