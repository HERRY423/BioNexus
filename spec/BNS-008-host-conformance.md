# BNS-008: Host Agent Conformance

**Status**: Active | **Version**: 1.0 | **Supersedes**: none
**Applies to**: Any AI host agent (Claude, Codex, future agents) connecting to BioNexus; `src/bionexus/claim_checker.py`; `evals/host_eval.py`
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

BioNexus does not assume a particular host. It assumes a **contract**: any agent that
routes scientific work through BioNexus inherits both its powers and its prohibitions.
This document defines host conformance. The Biological Capability ABI (BNS-001 §5) is
the machine boundary: agents MUST NOT bypass it by constructing their own prompts to
underlying libraries once a capability is matched.

## 2. Routing obligations

- **BNS-HC-001** A host agent MUST route analytical intents through
  `route_scientific_intent` (or its MCP/CLI equivalent) before executing any
  biomedical analysis, and MUST honor the returned status:
  - `ABSTAIN` → MUST NOT execute; MUST present violations and remedies to the user.
  - `NEEDS_DATA` → MUST request the enumerated missing data before proceeding.
  - `DEGRADED_ADVISORY` → MUST surface the degradation notice verbatim-class
    (Grade C, missing backend named) in its response.
  - `PERMITTED` → MAY execute via the recommended script/command.
- **BNS-HC-002** A host agent MUST NOT call underlying libraries directly (scanpy,
  squidpy, pydeseq2, lifelines, scvi) to circumvent a BioNexus refusal. Re-implementing
  a refused analysis outside the contract is a conformance violation even if the code
  runs.
- **BNS-HC-003** A host agent MUST present the EvidenceCard (all six dimensions and
  the synthesized maturity) with results, and MUST NOT paraphrase maturity upward
  (e.g. rendering `PRELIMINARY` as "demonstrated").

## 3. Prohibited claims

- **BNS-HC-004** Host-generated prose is auditable: responses MUST NOT contain
  claims on the capability's `forbidden_claims` list. The canonical prohibited
  families (enforced by `claim_checker`) are:
  1. **Cell-type identity assertions** without an annotation evidence source
     (BNS-II-008).
  2. **Causal regulatory/mechanistic claims** from correlational evidence
     (DE rankings, Moran's I, embeddings).
  3. **Clinical/regulatory claims** — diagnosis, treatment recommendation,
     CLIA/CAP-grade reporting (BNS-AD-010).
  4. **Model substitution claims** — presenting heuristic output as gold-backend
     output.
  5. **Survival hazard claims** from unadjusted KM/log-rank beyond association.
- **BNS-HC-005** Prohibited-claim detection is pattern-audited at L2
  (`audit_prohibited_claims`); a conformance run MUST report detected violations
  with matched text and violation type. Live host evaluation (`host_eval`) MUST
  be used when a real LLM provider is configured; replay mode MUST be labeled as
  such in every report.
- **BNS-HC-006** Hosts MUST NOT strip or omit the Research-Use-Only limitation from
  any BioNexus-derived output.

## 4. Cross-host consistency

- **BNS-HC-007** The same benchmark suite run through different hosts SHOULD
  produce concordant statuses and maturities; the platform MUST measure cross-host
  consistency where multiple hosts are evaluated, and MUST report it separately from
  single-host accuracy.
- **BNS-HC-008** A host that systematically under-performs the suite (e.g. presses
  through refusals) MUST be flagged non-conformant rather than averaged away.

## 5. Conformance verification

| Requirement | Verified by |
|---|---|
| BNS-HC-001..003 | eval L2 `host_agent_claim`; `evals/host_eval.py` |
| BNS-HC-002 | eval `adversarial` (bypass attempts) |
| BNS-HC-004 | `claim_checker.audit_prohibited_claims`; metrics `capability_hallucination_rate` |
| BNS-HC-005 | benchmark report execution-mode labeling (`is_live`) |
| BNS-HC-006 | `RESEARCH_USE_ONLY` injection in `contracts.attach_meta` |
| BNS-HC-007..008 | cross-host consistency metric (frontier calibration track) |
