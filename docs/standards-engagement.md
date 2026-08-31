# BioNexus Standards Engagement (BNS-016)

**Positioning (normative honesty):** BioNexus is **not** an industry standard and
does not claim to be one. The BNS specification series is an *implementation
proposal* — discussable, criticizable, contributable. World-class standards are
not self-declared; they form when other projects start adopting the vocabulary,
schemas, and tests. Until then, every "standards" claim BioNexus makes is
scoped to what is implemented here (see `bionexus standards`).

Implementation and verification are deliberately separate. The Workflow Run
RO-Crate fixture is checked in CI by the official `roc-validator==0.11.2`
against Provenance Run Crate 0.5 at REQUIRED severity (including its four
inherited profiles). The resulting hash-bound receipt says
`THIRD_PARTY_TOOL_VALIDATED`; it explicitly does not say certified, endorsed,
or adopted.

## Why now: the GA4GH AI standardization window

GA4GH launched its **Artificial Intelligence Work Stream** (April 2026) to build
responsible, interoperable standards and governance for genomics/health AI.
That mandate intersects what BioNexus already is, mechanically:

| GA4GH AI Work Stream focus | BioNexus contribution (concrete artifact) |
|---|---|
| Responsible AI in genomics/health | Fail-closed engine (`bionexus.failclosed`), deterministic refusal vocabulary (BNS-AD-014) |
| Interoperability of AI components | Biological Capability ABI (`bionexus.abi`), machine-readable capability contracts (`bionexus.capabilities`) |
| Evidence & evaluation boundaries | EvidenceCard 2.0 maturity ladder + evidence ceilings (`contracts`, `abi.enforce_evidence_ceiling`) |
| Provenance & reproducibility | PROV-O sidecars, RO-Crate / Workflow Run Crate exports (`bionexus interop wfrun-crate` ships full Research Object bundles: inputs, software, execution, steps, outputs, EvidenceCard, Claim Ledger), IEEE 2791 BCO exports (`bionexus.interop`) |
| AI agent conformance & safety | Host conformance spec (BNS-008), prohibited-claims auditor (`claim_checker`), L2 host benchmark |
| Shared test suites / benchmarks | BioFailureBench trap corpus (BNS-014): host-agnostic, ground-truthed, runnable by any agent framework |

What BioNexus would bring into such a forum is not a slogan but four portable
artifacts: (1) the BN-Fxxx failure taxonomy with detection rules, (2) the
capability-contract schema, (3) refusal/claim-boundary semantics, and (4) the
trap corpus with ground truth. All four are MIT/Apache-2.0 open, deterministic,
and testable without BioNexus infrastructure.

## Engagement venues and honest status

| Venue | Relationship | Status |
|---|---|---|
| GA4GH (AI Work Stream) | Contribution packet prepared; joining/submission requires a named human participant | `tracked` |
| ELIXIR | Interoperability packet prepared; contact requires a named human/Node relationship | `tracked` |
| nf-core | Samplesheet schemas; pipeline provenance alignment | `aligned` |
| scverse | Single-cell Python ecosystem feedback loop | `tracked` |
| Bioconductor | R-side failure vocabulary exchange | `tracked` |
| WorkflowHub | Official-validator-passing crate prepared; API publication requires a user token and Team ID | `tracked` |

The machine-readable version of this table lives in
`src/bionexus/standards.py` (`bionexus standards`), where statuses are a closed
vocabulary (`implemented` / `aligned` / `proposal` / `tracked`) that MUST
reflect reality.

The reproducible vocabulary/profile packet and a fail-closed submission
tracker live under `standards/external-engagement/`. `READY_BLOCKED_IDENTITY`
means the technical payload is ready but no form, email, or authenticated API
request has been sent without a real accountable submitter. It is not a
submission receipt.

## Contribution strategy

1. **Never announce; offer.** "Here is an implementation proposal + tests" —
   not "BioNexus is a standard."
2. **Ship the boring parts first.** PROV-O → RO-Crate → BCO projections make
   BioNexus outputs ingestible by existing institutional pipelines (Galaxy,
   DNAnexus, Seven Bridges, WorkflowHub) today, without asking anyone to adopt
   BNS.
3. **Contribute vocabulary, not infrastructure.** The taxonomy IDs, contract
   schema, and trap corpus are adoptable piecemeal; nothing requires running
   BioNexus.
4. **Let adoption invert the direction.** If a community adopts the failure
   taxonomy or the trap corpus, the standard grows there, not here.

## Verification hooks

- `bionexus standards` — registry with verbatim disclaimer (BNS-IO-008).
- `tests/unit/test_standards.py` — statuses honest, disclaimer verbatim.
- `tests/unit/test_interop.py` — projections valid (BNS-IO-001..006).
- `.github/workflows/ro-crate-conformance.yml` — official validator gate and
  downloadable crate/log/receipt artifact (BNS-IO-010).
