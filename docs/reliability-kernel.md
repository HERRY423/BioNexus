# BioNexus bounded reliability kernel

BioNexus remains a **Scientific Reliability Layer used by a host or researcher**.
The components described here are passive Python records and validators. They do
not select tools, schedule work, execute analyses, recommend a next action, or
make scientific decisions. They are not an Agent, hosted service, or platform.

## What this adds

### Contract traceability

`bionexus.contract_traceability` dynamically discovers normative BNS definition
bullets and preserves exact identifiers, including both `BNS-RC-004` and
`BNS-RC-004A`. A manifest can bind a requirement to source, test, evaluation,
documentation, or an acknowledged gap.

Definition bullets that omit an RFC 2119 keyword remain in the inventory with
`normative_level: UNSPECIFIED`; they are surfaced as specification debt instead
of being silently dropped from the denominator.

The report deliberately separates these states:

| State | Meaning |
|---|---|
| `documented_only` | Requirement exists; no evidence was declared. |
| `declared_unverified` | A reference resolves, but execution was not proven. |
| `implementation_bound` | A source symbol resolves; this is not proof of semantic correctness. |
| `tested` | An exact test node has a passing receipt bound to the current test-file hash. |
| `evaluated` | An exact evaluation target has a passing, content-bound receipt. |
| `acknowledged_gap` | The gap is explicit and machine-readable. |
| `invalid_reference` | A declared target is missing, unsafe, or unresolved. |

Example manifest:

```yaml
requirements:
  BNS-CL-005:
    evidence:
      - kind: implementation
        target: src/bionexus/ledger.py::ClaimLedger.resolve_status
      - kind: test
        target: tests/unit/test_ledger.py::test_contradiction_forces_conflicted
```

A test reference alone never becomes `tested`. A receipt must name the exact
node and carry the SHA-256 of the current file bytes:

```json
{
  "receipts": [{
    "receipt_id": "local-pytest-2026-08-27",
    "evidence_kind": "test",
    "command": "pytest tests/unit/test_ledger.py::test_contradiction_forces_conflicted",
    "passed_targets": ["tests/unit/test_ledger.py::test_contradiction_forces_conflicted"],
    "artifact_sha256": {"tests/unit/test_ledger.py": "<sha256>"},
    "outcome": "passed"
  }]
}
```

`reference_coverage`, `implementation_reference_coverage`, executed-test
coverage, and executed-evaluation coverage are reported independently. None of
these metrics proves that a scientific rule is biologically valid.

### Research snapshots and evidence capsules

`bionexus.research_snapshot` provides an append-only state record whose digest
covers the state, metadata, revision ID, and parent digest. Loading verifies the
entire parent chain. Supplying an externally retained head digest also detects a
valid-prefix rollback that internal hashing alone cannot detect.

Evidence capsules hash exact raw bytes. LF and CRLF files are intentionally
different artifacts, so writing or verifying on Windows cannot silently change
the hashed representation. ZIP member names, duplicate members, exact
membership, sizes, artifact hashes, and the manifest digest are verified. Keep
the returned `manifest_digest` outside the capsule and pass it back during
verification when protection against coordinated capsule replacement is needed.

Capsules reuse `bionexus.provenance.sidecar`. Its package/environment snapshot
supports reproducibility; it is not an electronic signature or evidence of
21 CFR Part 11, GxP, ALCOA+, CLIA, or biological validation.

### Strategy-neutral evaluation contract

`bionexus.evaluation_contract` separates `VisibleScenario` from
`ScorerGroundTruth`. A policy receives only the former. Scores depend on the
normalized `PolicyOutput` and scorer truth, never a policy name or category.
Consequently, renaming identical output from `baseline` to `frontier` cannot
change its score.

Metrics retain their real scope and direction:

- `target_gap_accuracy` and `acceptable_action_rate`: higher is better;
- `decision_changing_evidence_priority_rate`: higher is better;
- `competing_explanation_coverage`: higher is better;
- `unnecessary_action_rate`: lower is better;
- `review_artifact_completeness_proxy`: a structural proxy, not human-review evidence;
- `mean_payload_bytes`: serialized output size, not scientific context quality.

The harness can rerun a policy for deterministic replay and perturb scorer-only
truth to test output invariance. It does not ship a policy that tells a
researcher what to do, and it does not assume BioNexus must outperform a
baseline.

## Evidence boundary

These components improve repository maintenance, artifact integrity, and fair
offline evaluation. Passing their tests is engineering evidence only. It does
not establish scientific accuracy, external reproducibility, clinical utility,
regulatory readiness, or independent adoption.
