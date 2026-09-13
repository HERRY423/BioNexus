# Core 1.0 release criteria

The supported surface is frozen in
[`core-support.v1.json`](src/bionexus/data/core-support.v1.json).
This freezes an intended support boundary, not a GA declaration. The present
release remains an RC. No scientific authorization is granted by these checks.

## Supported surface

- Passive review of completed multi-donor DE artifacts: `audit-de`,
  `audit-de-verify`, `audit-de-summary` and their existing flags and exit codes.
- The five Python entry points and two bundle/integrity contract identifiers
  explicitly enumerated in the frozen manifest. Record serialization and
  unknown-state handling remain governed by their existing contracts and tests.
- Single-gene table assertions, separately evaluated complete clauses, honest
  nonsignificance and scoped limitations. Ambiguous gene/contrast binding and
  unsupported statistical designs require additional evidence or human review.

Other commands remain available with existing compatibility, but their presence
does not make analysis execution, annotation, spatial models, host behavior or
certification part of this Core support commitment. The long-term flagship
certification programme is separate from Core release acceptance.

## Internal acceptance gates

1. Historical reports keep their exact bytes and recorded execution identity.
   The retired synchronizer is read-only; a snapshot match is not a new run.
   Reports previously affected by metadata synchronization are quarantined as
   historical evidence of unestablished original execution provenance.
2. Actual validation runs retain before/after files and a separate run receipt,
   including failures and unchanged reports. Unchanged reports are not credited
   to the new run. Current-source verification still rejects stale evidence.
3. Within the supported audit scope, known serious failure cases have executable
   regression coverage: evaluator exceptions, multi-clause claims, ambiguous
   gene rows, missing/nonfinite/zero directional effects, missing or inconsistent
   execution bindings, negation/absence confusion, population extrapolation,
   unknown evidence states and bundle tampering. Positive controls must remain.
4. Core types, fixed line/branch coverage floors, DE requirement traceability,
   CLI/bundle compatibility and installed-wheel verification must pass on the
   candidate. Tests do not establish the correctness of all possible prose or
   independent scientific validity.
5. Version, scope, deprecation and support documents agree. Stable publication
   runs `scripts/check_release_contract.py` before creating a release. A version
   suffix alone cannot activate the proposed support contract.

## External and human release acceptance

The operator must supply independent rule-review and real-user acceptance
evidence for the supported scope, explicitly preserving unresolved issues.
Any advertised host support needs actual host acceptance evidence. Record these
separately from local tests; no local helper creates independent reviewers,
external adoption, consensus or biological certification.

`release/GA_ACTIVATION.json` stays PROPOSED until actual named maintainers accept
the scope, dates, contact and limitations. Its verification references bind exact
files. The record checker validates the record, not a person's identity or the
truth of their assertions. A responsible release reviewer must verify them.

## Correction and reassessment

A rule correction can ship as a patch with rule IDs, affected contexts,
before/after examples and a reassessment notice. Preserve original assessments;
write reassessments to new directories. Breaking consumer/scientific meanings
require a new contract identifier and migration, not silent reinterpretation.

No unhandled *known* severe false-pass or evidence-upgrade path may remain in
the declared scope at acceptance. This criterion is bounded by the recorded
cases and review; it is not a proof that unknown defects cannot exist.
