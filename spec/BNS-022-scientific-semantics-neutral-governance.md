# BNS-022: Scientific Semantics Neutral Governance and Institutional Adoption

**Status**: Draft / Council Forming | **Version**: 0.1 | **Supersedes**: none  
**Applies to**: BNS-019 stewardship, interoperability trials, institutional adoption records, BCTK assurance, certification, badging, and all BioNexus commercial operators.  
**Normative language**: RFC 2119 / RFC 8174. Requirement IDs are stable and never reused.

## 1. Purpose

BNS-022 prevents one vendor from simultaneously defining scientific meaning,
selling implementations, judging conformance, and issuing its own endorsement.
It establishes a Scientific Semantics Council (SSC) and separates technical,
commercial, and certification powers.

The governance framework is currently a prospective draft. The SSC is
`FORMING`; it MUST NOT be described as independent until its machine-readable
formation gates pass. No conformity assessment body is recognized and badging
remains suspended.

## 2. Independent Council formation

- **BNS-GV-001** Council status and independence claims MUST be derived from
  `governance/scientific-semantics/council-roster.json`, never from project
  ownership or maintainer assertion.
- **BNS-GV-002** `ACTIVE_INDEPENDENT` requires 7–11 voting seats, at least two
  thirds non-BioNexus affiliation, employer and commercial-vendor caps, the
  representation mix in `governance-model.json`, an independent Chair, public
  current disclosures, two independent selection observers, and at least a
  30-day public nomination period.
- **BNS-GV-003** Before every formation gate passes, the status MUST remain
  `FORMING`, the independence claim MUST remain `NOT_YET_ESTABLISHED`, and the
  governance effect MUST remain `PROSPECTIVE_DRAFT`.
- **BNS-GV-004** Interim maintainers MAY publish development proposals, run
  conformance tests, fix clerical defects, and convene nominations. They MUST
  NOT declare BNS-019 stable, accept a Council decision, recognize an assessor,
  issue a certificate, or restore badging.

## 3. Separation of powers

- **BNS-GV-005** Technical authority owns semantic meaning, namespaces,
  registry/schema releases, normative conformance specifications, and technical
  appeals. It MUST NOT operate certification or commercial pricing.
- **BNS-GV-006** Commercial authority owns product operation, pricing, funding,
  marketing, and trademark licensing under public policy. Funding or membership
  MUST NOT confer a technical vote, shortened review, assessor selection, or
  certification outcome.
- **BNS-GV-007** Certification authority alone may recognize eligible CABs,
  assess named implementations, and issue, suspend, or revoke certificates. A
  CAB MUST be independent of BioNexus commercial control and the applicant.
- **BNS-GV-008** Reserved actions MUST have exactly one owner. The governance
  validator MUST reject overlapping allowed actions or a reserved action not
  explicitly prohibited for the other powers.

## 4. Technical due process

- **BNS-GV-009** Every normative semantic change MUST use a public RFC with use
  cases, exact meaning, regime limitations, collision analysis, compatibility,
  migration, language-neutral tests, implementation evidence, and conflicts.
- **BNS-GV-010** Ordinary review MUST remain open at least 14 days. Breaking,
  stability, namespace, and governance changes MUST remain open at least 30
  days and require three quarters of all eligible non-recused Council members.
- **BNS-GV-011** Decisions MUST record eligible voters, votes, abstentions,
  recusals, formal objections, rationale, immutable source commit, and outcome.
  Rejected and withdrawn proposals MUST remain archived.
- **BNS-GV-012** Anyone MAY file a formal objection. Appeals MUST be heard by an
  ad hoc panel that did not vote on the decision and has no material commercial
  or certification conflict.

## 5. Conflicts and transparency

- **BNS-GV-013** Council members, selection observers, assurance overseers, CAB
  assessors, and appeal panelists MUST publish current conflict disclosures and
  update them after material change.
- **BNS-GV-014** A conflicted participant MUST NOT chair, deliberate privately,
  vote, select reviewers, or count toward quorum for the affected matter.
- **BNS-GV-015** Agendas, minutes, attendance, votes, recusals, objections,
  funding, and dispositions MUST be public except for narrowly bounded security,
  personal-safety, or legally protected material.

## 6. Institutional adoption

- **BNS-GV-016** Downloads, mentions, forks, sponsorship, trial registration,
  BioNexus self-use, and standards liaison activity MUST NOT be counted as
  institutional adoption.
- **BNS-GV-017** An adoption record MUST bind an organization, adoption role,
  exact BNS-019 release digest, implementation version, immutable evidence and
  SHA-256, scope, semantic loss, accountable contact, publication consent,
  status, and expiry.
- **BNS-GV-018** Adoption declarations expire after at most 18 months unless
  renewed. Withdrawal, expiry, or misrepresentation MUST remain visible in
  registry history and MUST reduce the active count.

## 7. Assurance and badging

- **BNS-GV-019** The SSC publishes technical requirements but MUST NOT assess a
  named product or issue its certificate. Scheme oversight and CAB execution
  MUST remain separate from technical and commercial decisions.
- **BNS-GV-020** Assurance status MUST remain
  `SUSPENDED_NO_INDEPENDENT_BODY`, certificates MUST remain empty, and
  `badge_issuance_enabled` MUST be false until at least one independent CAB is
  recognized and the SSC is `ACTIVE_INDEPENDENT`.
- **BNS-GV-021** Any future certificate MUST bind the exact standard release,
  assessment artifact, CAB identity, issuance/expiry, status, and public
  revocation record. Recognition MUST NOT be marketed as ISO accreditation
  unless the exact accreditation scope and evidence are independently verified.
- **BNS-GV-022** BCTK development diagnostics MUST remain
  `NOT_ASSESSED` and badge generation MUST fail closed while BNS-GV-020 is unmet.

## 8. Release and verification boundary

- **BNS-GV-023** This draft MUST NOT retroactively alter the frozen BNS-019
  0.1.0 release or interoperability trial digest. A future release incorporates
  governance only through its normal versioned release and RFC process.
- **BNS-GV-024** `python scripts/validate_semantic_governance.py` MUST validate
  schemas, role exclusivity, formation gates, disclosures, decisions, adoption
  evidence, CAB independence, assurance suspension, and BCTK badge refusal.

## 9. Current computed state

```text
Council                 FORMING
Independence claim      NOT_YET_ESTABLISHED
Normative effect        PROSPECTIVE_DRAFT
Verified adopters       0
Recognized CABs         0
Certification           SUSPENDED_NO_INDEPENDENT_BODY
Badge issuance          false
```

This state is a governance baseline, not evidence that an independent Council
or institutional ecosystem already exists.
