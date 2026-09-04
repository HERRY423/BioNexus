**Subject: Independent BioNexus pseudobulk review — two phases, one fixed run, negative results welcome**

Dear Dr. [Name],

I maintain [BioNexus](https://github.com/HERRY423/BioNexus), an open-source,
passive scientific reliability layer for AI-assisted biology. I am inviting a
small number of computational-biology researchers to challenge one bounded
track, `scrna.pseudobulk_de`. This is not a request for endorsement: a limited
or negative review is a valid result and will remain reviewer-authored.

[One personalized sentence explaining why this reviewer is relevant.]

The review uses a two-phase pre-output lock. First, without viewing BioNexus
outputs, fill and SHA-256 lock the methods-only pre-output assessment. Then run
the following command against the immutable commit. Full protocol:
[BLINDING_PROTOCOL.md](https://github.com/HERRY423/BioNexus/blob/__IMMUTABLE_REVIEW_COMMIT__/review/external-review/BLINDING_PROTOCOL.md).

```bash
REVIEW_COMMIT="__IMMUTABLE_REVIEW_COMMIT__" REVIEW_ID="__UNIQUE_REVIEW_ID__" && test "${#REVIEW_COMMIT}" -eq 40 && git clone https://github.com/HERRY423/BioNexus.git BioNexus-IVN-review && cd BioNexus-IVN-review && git checkout --detach "$REVIEW_COMMIT" && python3 -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install --no-deps -e . && python -m pip install -r review/external-review/requirements-review.txt && python review/external-review/build_review_capsule.py --expected-commit "$REVIEW_COMMIT" --review-id "$REVIEW_ID"
```

Reviewer JSON template:
[SIGNOFF_TEMPLATE.json](https://raw.githubusercontent.com/HERRY423/BioNexus/__IMMUTABLE_REVIEW_COMMIT__/review/external-review/SIGNOFF_TEMPLATE.json).
The packet uses a bounded review-only dependency profile, preserves all exit
codes and logs, and records a resolved environment snapshot. It is technical
reproduction evidence, not external-laboratory,
clinical, regulatory, or certification evidence.

Allowed verdicts are `ENDORSED`, `ENDORSED_WITH_LIMITS`, and `CHALLENGED`.
If you are willing to participate, a short reply is enough; I will send the
methods-only Phase 1 files before you access the repository.

Best regards,
Herry
BioNexus maintainer
