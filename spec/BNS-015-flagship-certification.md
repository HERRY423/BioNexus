# BNS-015: Flagship Certification Track

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: `src/bionexus/certification.py` (flagship program), `src/bionexus/capabilities.py`
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

The honest certification state (0 CERTIFIED) is not a weakness — it is the
roadmap. The flagship track concentrates certification effort where
scientific weight lives:

> **Three CERTIFIED capabilities with independent external validation
> outweigh ten self-defined, self-tested, self-certified capabilities.**

The flagship set maps onto the three highest-frequency scientific failure
surfaces in agentic biology:

| Flagship | Capability | Failure surface |
|---|---|---|
| A | `scrna.pseudobulk_de` | cell ≠ biological replicate; count-state; design; FDR |
| B | `scrna.annotation_evidence` | how much evidence backs a cell-type label |
| C | `spatial.inference_validity` | can a spatial conclusion survive its alternatives |

## 2. Requirements

- **BNS-FC-001** The flagship track MUST publish its principle verbatim:
  external evidence, not self-assertion, is the path to CERTIFIED; three
  externally-validated CERTIFIED capabilities are the stated priority over
  breadth of self-tested ones.
- **BNS-FC-002** The flagship set MUST be exactly the three capabilities
  above; membership changes are specification version bumps, never silent
  edits.
- **BNS-FC-003** Flagship CERTIFIED requires all 14 criteria of BNS-010
  unchanged; in particular the four external criteria (public reference
  dataset, independent ground truth, cross-host test, external reviewer)
  MUST be satisfied by parties other than the implementer. An implementation
  MUST NOT satisfy `external_reviewer` with its own authors.
- **BNS-FC-004** The M4 target of 10 CERTIFIED capabilities (BNS-CF-006)
  remains unchanged: the flagship track is a prioritization of effort, not a
  relaxation or redefinition of any criterion.
- **BNS-FC-005** Flagship progress MUST be computed from the same evidence
  records as the general program (BNS-CF-002); the flagship report MUST NOT
  assert a tier the evidence does not compute.
- **BNS-FC-006** The flagship report MUST publish, per capability, the
  external criteria still blocking CERTIFIED — this list is the flagship
  roadmap and MUST be visible in `bionexus certification` output.
- **BNS-FC-007** A capability MUST reach VALIDATED (all core criteria) before
  entering the flagship set; flagship slots are never occupied by
  EXPERIMENTAL or CONNECTOR-ONLY capabilities.
- **BNS-FC-008** Flagship capabilities MUST carry their own BioFailureBench
  trap coverage (BNS-BF-004): the failure surface they certify is exercised
  by the corpus, not only by unit tests. Flagship progress reviews SHOULD
  happen at every minor release; a capability that loses a core criterion
  MUST leave the flagship set until the criterion is restored (it MAY remain
  VALIDATED in the general program).

## 3. Verification hooks

- `src/bionexus/certification.py::flagship_program` — computed progress (BNS-FC-005).
- `tests/unit/test_flagship_capabilities.py` — flagship set, tier floor,
  external-criteria reporting.
- `bionexus certification` CLI — flagship section (BNS-FC-006).
- BioFailureBench coverage: BF-005/BF-012/BF-024 (flagship A),
  BF-004/BF-022/BF-026 (flagship B), BF-011/BF-015/BF-013 (flagship C).
