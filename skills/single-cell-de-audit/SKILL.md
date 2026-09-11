---
name: single-cell-de-audit
display_name: "Pre-submission Single-Cell DE Shadow Review"
description: Review completed multi-donor single-cell differential expression before submission. Accept existing DE tables, sample sheets, AnnData, scripts and claims; produce located findings, evidence gaps, repairs and human review. Record pilot observations without claiming validated benefit.
tier: core
grade: gold-wrapper
status: canonical
backend: "bionexus.de_audit"
---

# 投稿前单细胞 DE 影子审阅

Use for completed multi-donor single-cell DE results before submission, a lab meeting or handoff. Keep the user's existing analysis workflow. The first product promise is a bounded evidence review; error reduction and saved time remain hypotheses until measured in laboratories.

## First review

Inspect supplied files and column names. A DE table plus sample sheet is a useful starting point. Request missing donor/condition mappings only when needed. Do not require a full analysis rerun or fabricate execution records to get a pass.

```bash
bionexus audit-de --de-table de_results.csv --sample-sheet samples.csv --claim "Exact proposed manuscript claim" --bundle review-case-001
```

Use a new bundle directory. Add --script analysis.ipynb or --execution execution.json when those artifacts already exist. AnnData uses --h5ad results.h5ad and requires goldchain; table review works with the core package.

For a teaching example with no user data:

```bash
bionexus audit-de --demo --bundle review-demo
```

The synthetic example deliberately lacks evidence; exit code 1 is expected. It cannot count toward pilot benefit. If the installed CLI lacks these options, report the version mismatch rather than claiming a source-tree feature ran in the installed plugin.

## Deliver the review

Open REVIEW.md first: priority findings, their locations, minimal next steps, missing evidence and claim limits. Link audit-full.md for every finding and recorded fact. Do not turn a generic check into a specific donor/contrast attribution without evidence. Code snippets are suggestions, not verified execution.

The original audit status is binding. Missing evidence and parse failures remain explicit; a result-table schema, a script mentioning pseudobulk or a receipt hash is not proof of donor-level execution. Distinguish artifact validity from the warrant for the supplied claim. Keep valid negative results and unresolved interpretations visible. Leave scientific adjudication with the responsible human.

## Pilot observations, only when requested

Use reference-review.json with original inputs for a human reference review before revealing BioNexus findings. Copy the finished reference fields into review.json, then ask a human to judge each finding and record time/cost and reuse intent. Never invent reviewers, independent labels or saved minutes.

```bash
bionexus audit-de-summary review-case-001/review.json --out pilot-observations.md
```

Pending reviews and synthetic demos are excluded. Duplicate cases, changed audit hashes, incomplete judgments and invalid times are rejected. Summaries are self-reported descriptive evidence; they do not activate calibration or certify net benefit. See docs/de-pilot-guide.zh-CN.md in the source checkout for the pilot procedure. No outreach, scheduling, LIMS write or autonomous planning is part of this skill.
