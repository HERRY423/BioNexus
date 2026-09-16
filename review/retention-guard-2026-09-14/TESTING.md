# Verification record

## Completed checks

- Focused regression suite:
  `tests/unit/test_rc6_p0_boundaries.py`, `tests/unit/test_de_audit.py`, and
  `tests/unit/test_ga_semantic_boundaries.py` — **173 passed**. JUnit output is
  retained at `attempt-02/focused-tests.xml`.
- Frozen 54-case retention guard attempt 02 — **PASS**:
  valid retained 12/12, invalid accepted 0/42, invalid with a high-impact or
  blocker finding 42/42.
- Independent run verifier attempt 02 — **16/16 checks passed**. The first
  verifier output is retained as a failure because it incorrectly included
  runtime `__pycache__` files in the source tree. Attempt 02 excludes the same
  cache/bytecode paths as the snapshot producer.
- Ruff on the two product modules, changed regression test, and verifier —
  **passed**.
- Post-run family-to-mechanism check — all **54/54** cases matched the expected
  family-specific severe finding, explicit missing-receipt check, or valid-case
  pass behavior. This check is descriptive and was added after observing the
  main run; it is not part of the predefined endpoint.

## Incomplete additional check

`python -m pytest -q` for the entire repository was started as an extra broad
check. It produced no test output while one Python process continued consuming
CPU for approximately 25 minutes. The run was interrupted and has no pass/fail
test result. It is not reported as passing and is not part of the predefined
54-case gate.

The focused 173-test suite covers the modified execution binding, claim
semantics, negative-claim boundaries, DE audit status behavior, and GA semantic
boundaries.
