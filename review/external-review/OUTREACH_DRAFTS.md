# First IVN outreach wave

Prepared 2026-08-31. Public contact channels were checked on the named lab or
institutional pages. Recheck them immediately before sending. These are drafts,
not evidence that a message was sent or received.

Do not send until `__IMMUTABLE_REVIEW_COMMIT__` has been replaced by a pushed,
full 40-character commit SHA and the fresh-clone command has been exercised.

## 1. Michael I. Love — UNC Chapel Hill

Contact: `love@unc.edu` (Love Lab public directory) or the current UNC profile
address. Source: <https://mikelove.github.io/pages/lab.html>

**Subject: Independent pseudobulk review request — fixed BioNexus run, one JSON, negative results welcome**

Dear Dr. Love,

I maintain [BioNexus](https://github.com/HERRY423/BioNexus), an open-source
scientific reliability layer for AI-assisted biology. It records evidence
boundaries, refusal conditions, provenance, and claim ceilings; it is not an
autonomous scientist and it does not replace human scientific judgment.

I am inviting a small number of computational-biology researchers to create
the first external human record in its Independent Validation Network. This is
not a request for endorsement. A negative or limited review is a valid result
and will be preserved without being rewritten by the maintainer.

Given your work on DESeq2 and RNA-seq statistical inference, I would especially
value your criticism of our biological-replicate requirements, pseudobulk
design assumptions, multiple-testing/effect-size rules, and the boundary
between statistical association and stronger biological claims.

The review is bounded to immutable commit `__IMMUTABLE_REVIEW_COMMIT__` and the
`scrna.pseudobulk_de` track. One command creates a SHA-256-bound capsule with
the exact environment, exit codes, and complete logs; failed checks are
retained. You then fill one JSON and may return `ENDORSED`,
`ENDORSED_WITH_LIMITS`, or `REJECTED`, including any unreviewed scope.

Full one-command instructions and the JSON are here:

- `review/external-review/README.md`
- `review/external-review/SIGNOFF_TEMPLATE.json`

The capsule is technical reproduction evidence, not external-laboratory
replication. Your review would cover only the stated scope and would not assert
clinical fitness, regulatory compliance, or correctness of other capabilities.
You retain authorship and control of the review artifact.

If you are willing to participate, a short reply is enough. I will confirm the
review ID and immutable commit before you begin.

Best regards,  
Herry  
BioNexus maintainer

## 2. Mark D. Robinson — University of Zurich

Contact: `mark.robinson@mls.uzh.ch`. Source:
<https://www.mls.uzh.ch/en/research/robinson/professor-robinson.html>

**Subject: Independent pseudobulk evidence-boundary review — fixed run, negative results welcome**

Dear Professor Robinson,

I maintain [BioNexus](https://github.com/HERRY423/BioNexus), an open-source
scientific reliability layer for AI-assisted biology. It records evidence
boundaries, refusal conditions, provenance, and claim ceilings; it is not an
autonomous scientist and it does not replace human scientific judgment.

I am inviting a small number of computational-biology researchers to create
the first external human record in its Independent Validation Network. This is
not a request for endorsement. A negative or limited review is a valid result
and will be preserved without being rewritten by the maintainer.

Given your work in statistical genomics, open science, and reproducible
benchmarking, I would especially value your criticism of whether the
pseudobulk evidence thresholds, experimental-unit rules, and externally
verifiable ledger model form an appropriate scientific validation boundary.

The review is bounded to immutable commit `__IMMUTABLE_REVIEW_COMMIT__` and the
`scrna.pseudobulk_de` track. One command creates a SHA-256-bound capsule with
the exact environment, exit codes, and complete logs; failed checks are
retained. You then fill one JSON and may return `ENDORSED`,
`ENDORSED_WITH_LIMITS`, or `REJECTED`, including any unreviewed scope.

Full one-command instructions and the JSON are here:

- `review/external-review/README.md`
- `review/external-review/SIGNOFF_TEMPLATE.json`

The capsule is technical reproduction evidence, not external-laboratory
replication. Your review would cover only the stated scope and would not assert
clinical fitness, regulatory compliance, or correctness of other capabilities.
You retain authorship and control of the review artifact.

If you are willing to participate, a short reply is enough. I will confirm the
review ID and immutable commit before you begin.

Best regards,  
Herry  
BioNexus maintainer

## 3. Charlotte Soneson — Friedrich Miescher Institute

Contact: FMI's public directory “Send email” route. Source:
<https://www.fmi.ch/about/contact/?firstname=Charlotte&lastname=Soneson>

**Subject: Independent BioNexus pseudobulk review — one fixed run, one JSON**

Dear Dr. Soneson,

I maintain [BioNexus](https://github.com/HERRY423/BioNexus), an open-source
scientific reliability layer for AI-assisted biology. It records evidence
boundaries, refusal conditions, provenance, and claim ceilings; it is not an
autonomous scientist and it does not replace human scientific judgment.

I am inviting a small number of computational-biology researchers to create
the first external human record in its Independent Validation Network. This is
not a request for endorsement. A negative or limited review is a valid result
and will be preserved without being rewritten by the maintainer.

Given your work across RNA-seq methodology, Bioconductor, and practical
computational biology, I would especially value your assessment of whether our
pseudobulk requirements are scientifically defensible rather than merely
technically reproducible.

The review is bounded to immutable commit `__IMMUTABLE_REVIEW_COMMIT__` and the
`scrna.pseudobulk_de` track. One command creates a SHA-256-bound capsule with
the exact environment, exit codes, and complete logs; failed checks are
retained. You then fill one JSON and may return `ENDORSED`,
`ENDORSED_WITH_LIMITS`, or `REJECTED`, including any unreviewed scope.

Full one-command instructions and the JSON are here:

- `review/external-review/README.md`
- `review/external-review/SIGNOFF_TEMPLATE.json`

The capsule is technical reproduction evidence, not external-laboratory
replication. Your review would cover only the stated scope and would not assert
clinical fitness, regulatory compliance, or correctness of other capabilities.
You retain authorship and control of the review artifact.

If you are willing to participate, a short reply is enough. I will confirm the
review ID and immutable commit before you begin.

Best regards,  
Herry  
BioNexus maintainer

## Reserve targets after track-specific packets exist

- Rahul Satija / Satija Lab (`scrna.annotation_evidence`):
  <https://satijalab.org/join_contact/>
- Giovanni Palla (`spatial.inference_validity`): public contact listed in his
  current CV at <https://giovp.github.io/assets/vitae.pdf>

Do not reuse the pseudobulk capsule for these tracks. They need their own fixed
commands, subjects, attack questions, and evidence ceilings.
