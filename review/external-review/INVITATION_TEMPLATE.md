**Subject: Independent BioNexus review request — one fixed run, one JSON, negative results welcome**

Dear Dr. [Name],

I maintain [BioNexus](https://github.com/HERRY423/BioNexus), an open-source
scientific reliability layer for AI-assisted biology. It records evidence
boundaries, refusal conditions, provenance, and claim ceilings; it is not an
autonomous scientist and it does not replace human scientific judgment.

I am inviting a small number of computational-biology researchers to create
the first external human record in its Independent Validation Network. This is
**not a request for endorsement**. A negative or limited review is a valid
result and will be preserved without being rewritten by the maintainer.

I am asking you to challenge one fixed evidence track,
`scrna.pseudobulk_de`, because [one personalized sentence]. In particular, I
would value your judgment on the biological-replicate assumptions, pseudobulk
design and contrasts, multiple-testing/effect-size rules, refusal behavior,
and the maximum biological claim those rules permit.

The task is bounded:

1. Run one command against immutable commit
   `339cefb98643d5e9bd2483c44469481fed7a31f6` (macOS/Linux shown; a PowerShell equivalent is
   in `review/external-review/README.md`):

```bash
REVIEW_COMMIT="339cefb98643d5e9bd2483c44469481fed7a31f6" && test "${#REVIEW_COMMIT}" -eq 40 && git clone https://github.com/HERRY423/BioNexus.git BioNexus-IVN-review && cd BioNexus-IVN-review && git checkout --detach "$REVIEW_COMMIT" && python3 -m venv .venv && . .venv/bin/activate && python -m pip install --upgrade pip && python -m pip install -e . && python review/external-review/build_review_capsule.py --expected-commit "$REVIEW_COMMIT" --review-id BN-IVN-REV-001
```

2. Inspect the generated ZIP. It includes the exact commit/environment,
   command exit codes, and complete logs. Failed checks are retained rather
   than hidden. The ZIP's SHA-256 is emitted as a sidecar file.
3. Fill one file: `review/external-review/SIGNOFF_TEMPLATE.json`. You may return
   `ENDORSED`, `ENDORSED_WITH_LIMITS`, or `REJECTED`, and explicitly list what
   you did not review.

The capsule is technical reproduction evidence, not an external-laboratory
replication. A signed review covers only the stated scope and does not assert
clinical fitness, regulatory compliance, or correctness of other BioNexus
capabilities. You retain authorship and control of the review artifact.

If you are willing to participate, a short reply is enough. I will confirm the
review ID and immutable commit before you begin.

Best regards,
Herry
BioNexus maintainer
