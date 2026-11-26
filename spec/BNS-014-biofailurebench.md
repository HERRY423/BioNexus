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
- **BNS-BF-010** Community submissions MUST validate against the formal JSON Schema
  `spec/schemas/failure_trap.schema.json` via `bionexus bench validate-trap <file.yaml>`,
  carry non-empty input metadata, and declare an explicit Failure Taxonomy v1 ID.

## 3. Tooling & CLI Integration

```bash
# Validate corpus integrity and taxonomy linkage
bionexus bench validate

# Output community trap submission template
bionexus bench template -o my_trap.yaml

# Lint and validate a community trap file
bionexus bench validate-trap my_trap.yaml

# Display corpus statistics and flywheel moat depth
bionexus bench stats
```

## 4. Corpus coverage and causal-language measurements

`bionexus bench validate` lists the current gating and frontier case counts and
coverage of the BN-F001 through BN-F012 failure modes.

BF-051 through BF-060 exercise the INV-009 detector used by `bionexus verify`.
Each case supplies a fixed statement about an observational study. The positive
label means the author asserts a causal effect. Cases cover negation within
and across clauses, endorsed and rejected quotations, and paraphrases.

Run `bionexus eval --suite biofailurebench --level L2 --provider replay` to
replay those ten regression statements, including the frontier cases.

`bionexus bench inv009` scores a separate fixed panel of 100 statements.
The authors of the English and Chinese halves independently wrote and labeled
their statements without seeing the detector or development examples. Each
language has five asserted and five nonasserted claims in each of five groups:
direct statements, negation, quotations, paraphrases and hedging. A claim
counts as positive when the author endorses a causal relationship, regardless
of whether the study design warrants it. The panel is an authored challenge
set. Performance in published manuscripts remains unmeasured.

CI publishes `evals/reports/inv009_metrics.json` with confusion counts,
the text and labels of errors, and two-sided Wilson 95% intervals for
precision and recall. A zero denominator gives an undefined rate and interval.
The job checks the latest panel and the previous independent panel separately.
It fails if any case is unscored or either recall lower bound falls below
0.80. CI uploads the measurements on either outcome.

An earlier, separate 100-sentence panel was used for development. Its first
measurement is retained in `evals/reports/inv009_development_first_pass.json`.
On the first independent panel the initial detector had 28 true positives,
8 false positives, 22 false negatives and 42 true negatives. Its corpus,
measurement and detector patch are bound in `inv009_panel1_manifest.json`
under `evals/datasets/benchmarks/`. That panel became a regression set
after its errors were reviewed. The revised detector recovered 49 of its
50 positive labels, with 6 false positives.

Two other contributors wrote fresh English and Chinese halves for the final
independent measurement. Their original TSV hashes and the detector digest at
unblinding are recorded in `evals/datasets/benchmarks/inv009_panel_lock.json`.
The detector classified 33 of 50 assertions and flagged 3 of 50 nonassertions.
Precision was 91.7% (Wilson 95% interval 78.2%–97.1%) and recall was 66.0%
(52.2%–77.6%). This measurement fell below the prespecified recall floor.
Each panel has its own ID namespace.

## 5. Verification hooks

- `evals/biofailurebench.py::validate_corpus` — schema and coverage (BNS-BF-001/004/007).
- `tests/unit/test_biofailurebench.py` — corpus contract and runner wiring.
- `tests/unit/test_failure_taxonomy.py` — benchmark-case references resolve (BNS-FT-005).
- CI eval job — gating traps must pass in the reference environment.
