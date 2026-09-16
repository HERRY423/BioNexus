# BN-METHODS-RC8-REPLAY-20260914

Post-outcome replay of the frozen 09-08 54-case audit challenge against
the rc.8 release commit. This is **not** a new freeze of BN-METHODS-20260908,
not an independent expert study, and not a laboratory net-benefit trial.

## Why this exists

The 09-08 confirmatory result was joint-negative: `bionexus_full` accepted
0/42 invalid cases and retained 0/12 valid cases. rc.6–rc.8 closed recorded
counterexamples in product code. Those regressions do not by themselves
prove the 54 frozen cases now jointly improve. Only a replay of the same
cases can answer that.

## Claim under test

On the **byte-identical** 54 developer-authored cases from
`review/methods-experiments-2026-09-08/run-01/challenge/cases/`, does the
rc.8 `audit_differential_expression` **jointly** improve:

1. valid-case retention (`passed` / `ROBUST_PASS` among 12 valid cases)
2. unsupported acceptance (`passed` among 42 invalid cases)

Joint improvement is predefined as:

- `valid_retained_rc8 > valid_retained_0908` **and**
- `invalid_accepted_rc8 <= invalid_accepted_0908`

A rise in valid retention that is paid for by a rise in false passes is
**not** joint improvement (that was the 09-08 exploratory ablation pattern).

`NEEDS_DATA` / `NOT_ASSESSED` remain abstentions, not successful issue
identification and not valid retention.

## Engine under test

- Git commit: `fffd792fcd3949805debeee5c421feee8fbba921` (`v1.0.0-rc.8`)
- Import path: a copied `src/bionexus` tree from that commit, inserted at
  `sys.path[0]`. The 09-08 `frozen-source/` is not used.
- Original 09-08 runner, freeze, and `run-01/` are read-only.

## Inputs that must not change

Case folders, DE tables, metadata, receipts, and claim text are taken from
the 09-08 challenge directory. No table cell, hash, or claim paraphrase is
edited for the primary arm.

Acceptance definition is unchanged: `accepted = (overall_status == "ROBUST_PASS")`.
High-impact-or-blocker findings still count as `issue_identified`.

## Arms

Primary (confirmatory for this replay):

- `bionexus_full` — same call as 09-08: table path, metadata frame, receipt,
  claim text.

Version-independent controls (recomputed only for completeness):

- `accept_all`, `reject_all`, `deterministic_checklist`

Mechanism arms:

- `without_claim_text`
- `without_execution_metadata`

Exploratory sensitivity, **not** confirmatory:

- `bionexus_full_fitstatus_synonym` — in-memory only, maps receipt
  `fit_status` `COMPLETE` → `COMPLETED`. rc.8's allowed success vocabulary
  is `SUCCESS|SUCCEEDED|CONVERGED|COMPLETED|PASS|PASSED|OK`. The 09-08
  receipts used `COMPLETE`. This arm isolates a status-string synonym from
  scientific rule changes. It does not rewrite files, hashes, claims, or
  `FAILED` statuses.

## What this cannot establish

Independent expert labels, live LLM baselines, laboratory time savings,
external replication, or scientific authorization. Developer family labels
remain developer labels.
