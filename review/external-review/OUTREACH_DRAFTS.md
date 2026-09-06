# First IVN outreach wave

Prepared 2026-08-31. Recheck each institutional contact immediately before
sending. These are unsent drafts, not evidence of contact, participation, or
review. All three drafts are pinned to pushed candidate
`b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9` (`ivn-rfv-004`); never substitute
`main`.

## 1. Michael I. Love — UNC Chapel Hill

To: `love@unc.edu`
Public source: <https://mikelove.github.io/pages/lab.html>
Assigned ID: `BN-IVN-REV-001`

**Subject: Independent pseudobulk review request — pre-output lock, fixed run, negative results welcome**

Dear Dr. Love,

I maintain [BioNexus](https://github.com/HERRY423/BioNexus), a passive,
open-source reliability layer for AI-assisted biology. I am seeking one
independent human review of its bounded `scrna.pseudobulk_de` rules. This is
not a request for endorsement: `CHALLENGED` or limited conclusions are valid
and will remain reviewer-authored.

Given your work on DESeq2 and RNA-seq inference, I would especially value your
criticism of the biological-replicate requirement, design/contrast handling,
multiple testing and effect size, refusal behavior, and the maximum biological
claim those rules permit.

The review has two phases. Before viewing BioNexus outputs, please lock the
methods-only assessment described in the [blinding protocol](https://github.com/HERRY423/BioNexus/blob/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/BLINDING_PROTOCOL.md), using the [packet](https://raw.githubusercontent.com/HERRY423/BioNexus/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/BLINDED_REVIEW_PACKET.json) and [pre-output JSON template](https://raw.githubusercontent.com/HERRY423/BioNexus/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/PREOUTPUT_ASSESSMENT_TEMPLATE.json). Then run:

```bash
REVIEW_COMMIT="b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9" REVIEW_ID="BN-IVN-REV-001" && test "${#REVIEW_COMMIT}" -eq 40 && git clone https://github.com/HERRY423/BioNexus.git BioNexus-IVN-review && cd BioNexus-IVN-review && git checkout --detach "$REVIEW_COMMIT" && python3 -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install --no-deps -e . && python -m pip install -r review/external-review/requirements-review.txt && python review/external-review/build_review_capsule.py --expected-commit "$REVIEW_COMMIT" --review-id "$REVIEW_ID"
```

The capsule preserves commit identity, a resolved environment snapshot, every
exit code, and complete logs. Please return the locked pre-output file plus
the completed [reviewer JSON](https://raw.githubusercontent.com/HERRY423/BioNexus/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/SIGNOFF_TEMPLATE.json). The allowed verdicts are `ENDORSED`, `ENDORSED_WITH_LIMITS`, and `CHALLENGED`.

This is technical reproduction and a bounded scientific judgment—not
external-lab replication, clinical/regulatory evidence, certification, or a
review of BioNexus as a whole. If you are willing, a short reply is enough; I
will send the Phase 1 files before you access the repository.

Best regards,
Herry
BioNexus maintainer

## 2. Mark D. Robinson — University of Zurich

To: `mark.robinson@mls.uzh.ch`
Public source: <https://www.mls.uzh.ch/en/research/robinson/professor-robinson.html>
Assigned ID: `BN-IVN-REV-002`

**Subject: Independent pseudobulk evidence-boundary review — fixed run, negative results welcome**

Dear Professor Robinson,

I maintain [BioNexus](https://github.com/HERRY423/BioNexus), a passive,
open-source reliability layer for AI-assisted biology. I am seeking one
independent human review of its bounded `scrna.pseudobulk_de` rules. This is
not a request for endorsement: `CHALLENGED` or limited conclusions are valid
and will remain reviewer-authored.

Given your work in statistical genomics, open science, and reproducible
benchmarking, I would especially value your assessment of whether the
experimental-unit rules, pseudobulk thresholds, refusal behavior, and public
evidence boundary are scientifically defensible rather than merely runnable.

The review has two phases. Before viewing BioNexus outputs, please lock the
methods-only assessment described in the [blinding protocol](https://github.com/HERRY423/BioNexus/blob/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/BLINDING_PROTOCOL.md), using the [packet](https://raw.githubusercontent.com/HERRY423/BioNexus/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/BLINDED_REVIEW_PACKET.json) and [pre-output JSON template](https://raw.githubusercontent.com/HERRY423/BioNexus/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/PREOUTPUT_ASSESSMENT_TEMPLATE.json). Then run:

```bash
REVIEW_COMMIT="b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9" REVIEW_ID="BN-IVN-REV-002" && test "${#REVIEW_COMMIT}" -eq 40 && git clone https://github.com/HERRY423/BioNexus.git BioNexus-IVN-review && cd BioNexus-IVN-review && git checkout --detach "$REVIEW_COMMIT" && python3 -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install --no-deps -e . && python -m pip install -r review/external-review/requirements-review.txt && python review/external-review/build_review_capsule.py --expected-commit "$REVIEW_COMMIT" --review-id "$REVIEW_ID"
```

The capsule preserves commit identity, a resolved environment snapshot, every
exit code, and complete logs. Please return the locked pre-output file plus
the completed [reviewer JSON](https://raw.githubusercontent.com/HERRY423/BioNexus/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/SIGNOFF_TEMPLATE.json). The allowed verdicts are `ENDORSED`, `ENDORSED_WITH_LIMITS`, and `CHALLENGED`.

This is technical reproduction and a bounded scientific judgment—not
external-lab replication, clinical/regulatory evidence, certification, or a
review of BioNexus as a whole. If you are willing, a short reply is enough; I
will send the Phase 1 files before you access the repository.

Best regards,
Herry
BioNexus maintainer

## 3. Charlotte Soneson — Friedrich Miescher Institute

To: `charlotte.soneson@fmi.ch`
Public source: <https://www.fmi.ch/about/contact/?firstname=Charlotte&lastname=Soneson>
Assigned ID: `BN-IVN-REV-003`

**Subject: Independent BioNexus pseudobulk review — pre-output lock and one fixed run**

Dear Dr. Soneson,

I maintain [BioNexus](https://github.com/HERRY423/BioNexus), a passive,
open-source reliability layer for AI-assisted biology. I am seeking one
independent human review of its bounded `scrna.pseudobulk_de` rules. This is
not a request for endorsement: `CHALLENGED` or limited conclusions are valid
and will remain reviewer-authored.

Given your work across RNA-seq methodology, Bioconductor, and practical
computational biology, I would especially value your assessment of whether the
pseudobulk requirements, failure modes, and claim ceiling are scientifically
defensible rather than merely technically reproducible.

The review has two phases. Before viewing BioNexus outputs, please lock the
methods-only assessment described in the [blinding protocol](https://github.com/HERRY423/BioNexus/blob/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/BLINDING_PROTOCOL.md), using the [packet](https://raw.githubusercontent.com/HERRY423/BioNexus/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/BLINDED_REVIEW_PACKET.json) and [pre-output JSON template](https://raw.githubusercontent.com/HERRY423/BioNexus/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/PREOUTPUT_ASSESSMENT_TEMPLATE.json). Then run:

```bash
REVIEW_COMMIT="b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9" REVIEW_ID="BN-IVN-REV-003" && test "${#REVIEW_COMMIT}" -eq 40 && git clone https://github.com/HERRY423/BioNexus.git BioNexus-IVN-review && cd BioNexus-IVN-review && git checkout --detach "$REVIEW_COMMIT" && python3 -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install --no-deps -e . && python -m pip install -r review/external-review/requirements-review.txt && python review/external-review/build_review_capsule.py --expected-commit "$REVIEW_COMMIT" --review-id "$REVIEW_ID"
```

The capsule preserves commit identity, a resolved environment snapshot, every
exit code, and complete logs. Please return the locked pre-output file plus
the completed [reviewer JSON](https://raw.githubusercontent.com/HERRY423/BioNexus/b468886d8c51b1f0c4bf4e3f48f4dd2a5af9a6b9/review/external-review/SIGNOFF_TEMPLATE.json). The allowed verdicts are `ENDORSED`, `ENDORSED_WITH_LIMITS`, and `CHALLENGED`.

This is technical reproduction and a bounded scientific judgment—not
external-lab replication, clinical/regulatory evidence, certification, or a
review of BioNexus as a whole. If you are willing, a short reply is enough; I
will send the Phase 1 files before you access the repository.

Best regards,
Herry
BioNexus maintainer

## Reserve targets

- Rahul Satija / Satija Lab for a future `scrna.annotation_evidence` packet:
  <https://satijalab.org/join_contact/>
- Giovanni Palla for a future `spatial.inference_validity` packet:
  <https://giovp.github.io/assets/vitae.pdf>

Do not reuse the pseudobulk capsule for those tracks; they require distinct
subjects, attack questions, data, and evidence ceilings.
