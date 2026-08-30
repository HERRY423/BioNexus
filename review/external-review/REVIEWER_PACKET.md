# External Reviewer Packet (Reviewer #1)

**Status: OPEN — no external sign-off exists yet.** This packet makes the first
independent review mechanical: everything below is reproducible from a clean clone,
and the acceptance artifact is a single JSON file.

## 1. Who qualifies as reviewer #1

You qualify if **all** of the following hold (mirrors `REVIEW_PROTOCOL.md` §independence):

- You are **not** the BioNexus author/maintainer and are not paid by or report to them.
- You have no financial stake in BioNexus adoption.
- You hold (or are supervised at) research-level expertise in at least one assigned case:
  - `pseudobulk` — pseudobulk DE, FDR, biological replicates;
  - `annotation` — reference mapping, marker consistency, cell-type evidence;
  - `spatial` — spatial transcriptomics confounders, segmentation artifacts.
- You are willing to have your name, affiliation, and disclosures published in
  `review/SCIENTIFIC_REVIEW.json`.

## 2. What to review (identical suite, ~45 minutes machine time)

From a clean clone of the branch you are reviewing (record its HEAD):

```bash
pip install -e ".[goldchain,spatial,deseq,survival]"   # scientific stack
pytest tests -q                                        # full unit suite (must be green)
bionexus eval --strict                                  # benchmark: skips are failures
bionexus certification                                  # honest tier state (0 CERTIFIED / 3 VALIDATED)
python -m bionexus.validation_verifier                  # preregistration locks + hashes
```

Then the three flagship evidence tracks — **challenge the rule thresholds, not just the code**:

| Track | What to inspect | The judgment call we want you to attack |
|---|---|---|
| `validation/pseudobulk/` | preregistration locks, REPORT, negative-result freezes | Are the locked endpoints the right scientific bar? |
| `validation/annotation/studies/BN-ANN-IV-004/` | donor-held-out blinded successor on GSE96583 | Is the donor split + dev-only threshold derivation genuinely blinded enough for the claimed ceiling? Is DC→MONOCYTE mapping conservative or precision-inflating? |
| `validation/spatial/studies/BN-SP-IV-002/` | public biological cohort (167,780-cell Xenium breast Rep1) | Are the declared-NOT_APPLICABLE exclusions justified? Is "real-tissue technical acceptance" the right ceiling? |

Cross-host evidence: `cross-host/zcode/REPORT.json` (one real non-author host run;
`codex`/`claude-code` rows remain open).

## 3. What a sign-off is and is not

A sign-off asserts: *you reproduced the artifacts, you attacked the thresholds and
decision rules, and the recorded conclusions match the evidence within the stated
claim boundaries.* It does **not** assert biological validity, clinical fitness,
regulatory compliance, or that untested capabilities work.

You may also sign a **negative or partial review** — a documented failure (wrong
threshold, overclaimed ceiling, non-reproducible artifact) is a valid, publishable
outcome and will be recorded verbatim in `review/SCIENTIFIC_REVIEW.json`.

## 4. The acceptance artifact

Fill `SIGNOFF_TEMPLATE.json` (same directory), including the HEAD commit you
reviewed, your disclosures, per-case verdicts, and any `false_refusals` you hit.
Submit by opening a PR that adds it as
`review/external-review/signed/SIGNOFF-<your-id>.json` plus a line in
`review/SCIENTIFIC_REVIEW.json` (field `reviewers[i].name` / `affiliation` fill-in).
The maintainer cannot edit your file's content — corrections go through your follow-up PR.

## 5. Conflicts and funding disclosure

Disclose funding, employment, and prior collaboration with the maintainer in the
template's `disclosures` object. "None" must still be stated explicitly.
