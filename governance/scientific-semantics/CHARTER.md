# Scientific Semantics Council Charter

Status: **Draft / Council forming**  
Governance ID: `BNS-SSC-GOV-001`

## 1. Mission and limits

The Scientific Semantics Council (SSC) stewards the technical meaning and
interoperability of the BioNexus Scientific Semantic Conventions. It controls
the public namespace, schemas, compatibility rules, normative conformance
fixtures, and specification maturity.

The SSC does not operate commercial products, set prices, allocate commercial
revenue, license product trademarks, assess implementations, issue badges or
certificates, or endorse vendors. Technical conformance is not certification.

## 2. Formation truth

The Council may call itself **independent** only after all machine-readable
formation gates in `governance-model.json` pass against `council-roster.json`.
Before then its state is `FORMING` and BioNexus maintainers act only as interim
draft stewards.

Interim draft stewards may fix clerical defects, run public tests, publish
development proposals, and convene nominations. They may not:

- declare BNS-019 stable;
- make a breaking semantic change without the future Council process;
- appoint themselves as a permanent independent Council;
- recognize a conformity assessment body;
- certify any implementation or restore badging; or
- describe consultation, sponsorship, or review as endorsement.

## 3. Composition and independence

An active Council has 7–11 voting seats and must satisfy all of these gates:

- at least two thirds of voting seats are not affiliated with BioNexus;
- no employer or related-company group controls more than one third;
- commercial vendors collectively control no more than one third;
- at least two seats represent institutional scientific end users;
- at least two seats have independent implementation or interoperability
  experience;
- at least one seat represents statistics or research methodology;
- at least one seat represents ontology, data standards, or scientific data
  stewardship;
- the Chair is not affiliated with BioNexus; and
- every member has a current public conflict disclosure.

Affiliation includes employment, executive control, board service, material
equity, or more than 25% of professional income from the entity during the
previous 12 months. Disclosed research grants do not automatically disqualify a
member, but may require recusal.

## 4. Selection, terms, and removal

Nominations are public for at least 30 days. A founding selection record must
be reviewed by two independent observers who are not nominees, BioNexus
employees, commercial sponsors, or candidate certification bodies. Formation
requires public gate output and a recorded response to objections.

Terms are two years, staggered where possible, with a maximum of two
consecutive full terms. The Chair serves one year and may be re-elected once.
Members serve as individuals and do not transfer votes to employers.

Removal requires a published rationale and a two-thirds vote of eligible,
non-recused members. Loss of an independence gate triggers immediate suspension
of affected decisions until the roster is repaired and revalidated.

## 5. Decisions

Consensus is preferred. Chairs must address sustained technical objections in
the public record. When consensus cannot be reached:

- routine technical decisions require quorum of two thirds and a simple
  majority of eligible votes;
- a breaking change, move to `stable`, namespace transfer, or governance change
  requires three quarters of all eligible, non-recused voting members;
- silence is abstention, not assent; and
- every vote, recusal, minority rationale, and disposition is recorded.

Ordinary proposals remain open for public comment for at least 14 days;
breaking, stability, namespace, and governance proposals remain open for at
least 30 days. Emergency security actions may be temporary for 14 days and may
not change scientific meaning.

## 6. Formal objections and appeal

Anyone may file a formal objection identifying the decision, technical or
procedural rationale, and a proposed remedy. The Council must answer it in the
decision record.

Appeals are heard by a three-person ad hoc panel whose members did not vote on
the decision and have no commercial or certification conflict. The panel may
affirm, remand, or invalidate the process; it may not author a replacement
technical meaning. Appeal records are public.

## 7. Transparency

Agendas are published seven days before ordinary meetings. Minutes, attendance,
votes, recusals, objections, and action items are published within seven days
after a meeting. Private sessions are limited to security embargoes, personal
safety, or legally protected information; the existence and basis of the
session remain public.

All normative work occurs through public RFCs, immutable decision records, and
versioned release artifacts. Sponsorship, membership fees, or commercial
contracts confer no technical vote or certification outcome.
