---
name: external-evidence-audit
description: Audit completed results from literature, database, analysis, sequence, structure, or slide capabilities, then optionally assemble an explicitly adjudicated multi-source claim assessment. Passive only; never select tools, infer evidence relationships, or make the final scientific decision.
---

# External evidence audit

Use this skill only after the host or researcher has supplied a JSON envelope
for a completed external capability call.

## Boundary

- Do not choose, call, retry, or schedule another plugin.
- Do not infer producer authenticity from a declared plugin name.
- Do not treat a content hash as a signature.
- Do not convert a database record, paper, viewer observation, or successful
  analysis run into independent validation.
- Do not assign scientific maturity; intake always starts `UNASSESSED`.
- Do not infer whether an envelope supports or contradicts a claim. The host
  must supply one review-bound adjudication per envelope.
- Do not treat `PASS` as final scientific acceptance. The named
  `decision_owner` remains accountable for the final decision.

## Input

Create `bionexus.external-evidence-envelope.v1` with the producer identity,
capability family, exact returned payload, originating request, and the
family-specific source context documented in `docs/ecosystem-collaboration.md`.

Audit it with:

```bash
python skills/external-evidence-audit/scripts/audit_external_evidence.py envelope.json
```

Write a reusable JSON audit artifact with:

```bash
python skills/external-evidence-audit/scripts/audit_external_evidence.py envelope.json --out audit.json
```

`VALID` means only that the payload hash and required declared context are
internally consistent. Producer identity remains `DECLARED_NOT_AUTHENTICATED`.
`INCOMPLETE` or `INVALID` must not enter the Claim–Evidence Ledger as support.

## Multi-source claim assessment

After each envelope is `VALID`, create
`bionexus.ecosystem-claim-packet.v1` with:

- the exact envelopes;
- a declared claim and explicit `claim_context` constraints;
- exactly one `supports`, `contradicts`, `context`, or `depends_on`
  adjudication per envelope;
- rationale, named adjudicator, and SHA-256 adjudication receipt for every
  claim-bearing edge;
- a named human `decision_owner`.

Then run:

```bash
python skills/external-evidence-audit/scripts/assess_ecosystem_claim.py claim-packet.json --out assessment.json
```

The result contains Warrant, Audit, EvidenceCard, and Claim–Evidence Ledger
artifacts. Duplicate payloads count once, declared context conflicts block all
claim-bearing edges, explicit contradictory evidence yields `CONFLICTED`, and
`final_decision` always remains `PENDING_HUMAN_DECISION`.
