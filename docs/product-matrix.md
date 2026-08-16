# BioNexus Product Matrix & Scope Boundaries

The product is not an ever-growing monolith. It is four layers with hard
boundaries — and an explicit list of things BioNexus will never be.

```text
BioNexus
│
├── bionexus-core                 the scientific contract kernel
│   ├── BNS specification series  (spec/BNS-001..016)
│   ├── Biological Capability ABI (capabilities, abi)
│   ├── Failure Taxonomy          (failures, BN-F001..F012)
│   ├── Fail-Closed Engine        (intent_router, failclosed)
│   └── Evidence Model            (contracts, ledger, provenance, artifacts, interop)
│
├── bionexus-audit                the researcher entry points
│   ├── preflight                 (preflight)
│   ├── audit                     (analysis_audit, integrity, claim_checker)
│   └── verify                    (verification)
│
├── bionexus-conformance          the trust layer
│   ├── capability certification  (certification, BNS-010/015 flagship)
│   ├── host conformance          (claim_checker L2 audits, evals/host_eval)
│   └── BioFailureBench           (evals/datasets/biofailurebench.yaml, evals/biofailurebench.py)
│
└── reference capability packs    executable, certified-able skills
    ├── single-cell               (single-cell-rna-qc, scvi-tools)
    ├── spatial                   (spatial-transcriptomics)
    └── reproducibility           (provenance-and-audit, nextflow-development, instrument-data-to-allotrope)
```

## Module mapping (test-enforced)

| Matrix cell | Modules in `src/bionexus/` (+ trees) |
|---|---|
| core: contracts & ABI | `capabilities`, `abi` |
| core: failure taxonomy | `failures` |
| core: fail-closed engine | `intent_router`, `failclosed` |
| core: evidence model | `contracts`, `ledger`, `provenance`, `artifacts`, `interop`, `standards` |
| audit: preflight / audit / verify | `preflight`, `analysis_audit`, `verification` |
| audit: data & claim integrity | `integrity`, `claim_checker` |
| conformance: certification | `certification` |
| conformance: host conformance & bench | `evals/` (runner, host_eval, biofailurebench) |
| reference packs | `skills/` tree (single-cell-rna-qc, spatial-transcriptomics, scvi-tools, provenance-and-audit, nextflow-development, instrument-data-to-allotrope) |

Today these layers ship as one Python package with the boundaries enforced at
module level (imports flow downward only: audit → core; conformance → core;
packs → core via `skill_runtime`). Splitting into separately installable
distributions (`bionexus-core`, `bionexus-audit`, `bionexus-conformance`) is a
packaging decision that MAY follow adoption; the boundary discipline starts
now, not after the split.

## Non-goals (the boundary)

BioNexus deliberately contains none of the following — each of them is a
different product with different failure modes, and adding any of them would
dilute the one thing BioNexus is for (catching analyses that should not have
been run):

- planner / orchestration agent
- memory / persistent agent state
- multi-agent frameworks
- chat UI
- cloud workspace
- notebook replacement
- compute service
- agent marketplace

A pull request that adds any of these should be rejected on scope grounds,
however well implemented.
