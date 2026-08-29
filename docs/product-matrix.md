# BioNexus Product Matrix & Scope Boundaries

BioNexus is the **Scientific Reliability Layer / Scientific Warrant Engine** for
agentic biology: it assesses what the evidence warrants (policy-independent),
caps claims that exceed their evidence, and blocks execution only where a true
invariant is violated. The product is not an ever-growing monolith, and
frontier biology is not a fifth product layer. BioNexus is exactly two planes
with hard boundaries:

```text
BioNexus
│
├── BioNexus Core                        the reliability layer IS the product
│   │
│   ├── core                             the scientific contract kernel
│   │   ├── BNS specification series     (spec/BNS-001..020)
│   │   ├── Biological Capability ABI    (capabilities, abi)
│   │   ├── Scientific Semantics          (consumes independent BNS-019 release)
│   │   ├── Spatial Empirical Gold        (Xenium/CosMx/MERSCOPE calibration only)
│   │   ├── Warrant Engine               (warrant: WarrantAssessment / PolicyDecision,
│   │   │                                 rule_classification: EpistemicKind taxonomy)
│   │   ├── Failure Taxonomy             (failures, BN-F001..F012)
│   │   ├── Fail-Closed Engine           (intent_router, failclosed)
│   │   ├── Evidence Model               (contracts, ledger, provenance, artifacts, interop)
│   │   └── Evidence Debt Engine         (debt, BNS-021: Epistemic DAG amortization & payoff)
│   │
│   ├── audit                            the researcher entry points
│   │   ├── preflight                    (preflight)
│   │   ├── audit                        (analysis_audit, integrity, claim_checker)
│   │   ├── debt                         (bionexus debt: audit, payoff schedule, DAG graph)
│   │   └── verify                       (verification)
│   │
│   └── conformance                      the trust layer
│       ├── BCTK (Diagnostic Test Kit)   (bctk, bionexus conformance, BNS-020:
│       │                                 OpenTelemetry-style compliance kit for any
│       │                                 agent/plugin/tool across 8 scientific dimensions)
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
| core: contracts, ABI & semantics | `capabilities`, `abi`, `scientific_semantics` |
| core: failure taxonomy | `failures` |
| core: fail-closed engine | `intent_router`, `failclosed` |
| core: evidence model | `contracts`, `ledger`, `provenance`, `artifacts`, `interop`, `ecosystem_intake`, `standards` |
| audit: preflight / audit / verify | `preflight`, `analysis_audit`, `verification` |
| audit: data & claim integrity | `integrity`, `claim_checker` |
| conformance: certification | `certification` |
| conformance: backend identity | `backend_conformance` (BNS-EF-012..016; CLI `backend-identity`) |
| conformance: host conformance & bench | `evals/` (runner, host_eval, biofailurebench, flagship_validation) |
| capability plane: stable packs | `skills/` tree (single-cell-rna-qc, spatial-transcriptomics, scvi-tools, provenance-and-audit, external-evidence-audit, nextflow-development, instrument-data-to-allotrope) |
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
dilute the one thing BioNexus is for: **warrant-first scientific assessment —
determining what the evidence actually warrants, capping claims that exceed
their evidence, and blocking execution only where a true invariant is
violated**:

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

## Capability freeze (current phase)

The current development phase imposes a freeze on **horizontal capability
expansion**: no new protein, clinical, or additional omics tool capabilities
will be added. The three flagship capabilities —

| Flagship | Capability ID | Certification track |
|---|---|---|
| Pseudobulk differential expression | `scrna.pseudobulk_de` | BNS-015 external validation vs published DE truth (Kang 2018) |
| Annotation evidence assessment | `scrna.annotation_evidence` | BNS-015 distrust calibration on CITE-seq/FACS-sorted PBMC |
| Spatial Alternative Explanation Battery | `spatial.inference_validity` v2 | BNS-015 segmentation/leakage/geometry/field/null/label challenges, followed by real platform-separated Xenium/CosMx/MERSCOPE calibration |

— are the priority: they must reach genuinely **CERTIFIED** status (14/14
evidence gates, Backend Identity CONFORMANT, external real-data validation).
Three certified flagships prove the core thesis — policy-independent warrant
assessment with evidence-capped claims — better than a broad catalog of
uncertified capabilities. Existing frontier packs remain opt-in reference
implementations; the freeze governs *new* capability surface, not maintenance
or certification of what already exists.
