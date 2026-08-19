# BioNexus Product Matrix & Scope Boundaries

The product is not an ever-growing monolith, and frontier biology is not a
fifth product layer. BioNexus is exactly two planes with hard boundaries:

```text
BioNexus
│
├── BioNexus Core                        the reliability layer IS the product
│   │
│   ├── core                             the scientific contract kernel
│   │   ├── BNS specification series     (spec/BNS-001..016)
│   │   ├── Biological Capability ABI    (capabilities, abi)
│   │   ├── Failure Taxonomy             (failures, BN-F001..F012)
│   │   ├── Fail-Closed Engine           (intent_router, failclosed)
│   │   └── Evidence Model               (contracts, ledger, provenance, artifacts, interop)
│   │
│   ├── audit                            the researcher entry points
│   │   ├── preflight                    (preflight)
│   │   ├── audit                        (analysis_audit, integrity, claim_checker)
│   │   └── verify                       (verification)
│   │
│   └── conformance                      the trust layer
│       ├── capability certification     (certification, BNS-010/015 flagship)
│       ├── backend identity conformance (backend_conformance, BNS-EF-012..016 / BN-F010:
│       │                                 declared_backend == observed_backend,
│       │                                 machine-provably; no silent substitution)
│       ├── host conformance             (claim_checker L2 audits, evals/host_eval)
│       └── BioFailureBench              (evals/datasets/biofailurebench.yaml, evals/biofailurebench.py)
│
└── Capability Plane                     reference implementations, NOT the product core
    ├── stable reference packs           executable, certification-able skills
    │   ├── single-cell                  (single-cell-rna-qc, scvi-tools)
    │   ├── spatial                      (spatial-transcriptomics)
    │   └── reproducibility              (provenance-and-audit, nextflow-development,
    │                                     instrument-data-to-allotrope)
    │
    └── frontier reference packs         opt-in experimental implementations
        ├── foundation models            (scfm, protein-language-models, geneformer/scgpt)
        ├── cluster & big data           (cluster.hpc_dispatch, bigdata.out_of_core_audit)
        ├── spatial deconvolution        (spatial.tangram_deconvolution)
        ├── perturbation & design        (gears, closed_loop.perturbation_to_niche)
        └── experiment design / biology  (experiment-design-agent, biologics-design, ...)
```

The structural rule: foundation models, HPC dispatch, tangram, closed-loop
and every other frontier capability are **reference implementations on the
Capability Plane** — they consume BioNexus Core's contract, routing and
conformance machinery, and they are gated (`EXPERIMENTAL_CAPABILITY_REQUIRES_OPT_IN`
by default). They are not, and must never become, a reason for BioNexus to
grow into a "do-everything biology platform".

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
| conformance: backend identity | `backend_conformance` (BNS-EF-012..016; CLI `backend-identity`) |
| conformance: host conformance & bench | `evals/` (runner, host_eval, biofailurebench, flagship_validation) |
| capability plane: stable packs | `skills/` tree (single-cell-rna-qc, spatial-transcriptomics, scvi-tools, provenance-and-audit, nextflow-development, instrument-data-to-allotrope) |
| capability plane: frontier packs | `scfm`, `cluster`, `bigdata`, tangram/gears/nicheformer capability contracts, closed_loop |

Today these layers ship as one Python package with the boundaries enforced at
module level (imports flow downward only: audit → core; conformance → core;
capability-plane packs → core via `skill_runtime`). Splitting into separately
installable distributions (`bionexus-core`, `bionexus-audit`,
`bionexus-conformance`) is a packaging decision that MAY follow adoption; the
boundary discipline starts now, not after the split. The Capability Plane
never splits upward into Core: a reference pack may graduate from frontier to
stable via certification evidence (BNS-010/015), never into the contract
kernel itself.

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
- a frontier capability promoted to a product layer (frontier stays on the
  Capability Plane as opt-in reference implementations)

A pull request that adds any of these should be rejected on scope grounds,
however well implemented.
