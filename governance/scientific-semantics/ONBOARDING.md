# Onboarding: the first non-author participant

**State: no external participant has joined yet.** The Scientific Semantics
Council is `FORMING` (`council-roster.json`: `independence_claim:
NOT_YET_ESTABLISHED`, all formation gates unmet). This document is the shortest
concrete path from that state to its first non-author participant. It is
authored by an interim draft steward (permitted under the charter's formation
truth clause); every decision slot in it is reserved for external participants.

## Why the first participant matters more than the roster size

The formation gates (`minimum_voting_seats`, `minimum_non_bionexus_fraction`,
`independent_chair`, `public_current_disclosures`, …) all require people who
are not the maintainer. Nothing in this repository can substitute for that
first person. Conversely, one qualified participant unlocks: a real public
nomination period, the first independent disclosure on file, and a review
period for the first RFC.

## The three participation tracks (pick one)

| Track | Commitment | You qualify if | First deliverable |
|---|---|---|---|
| **Council member** (voting seat) | ~2–4 h/month | Domain researcher (single-cell / spatial / biostatistics); no maintainer relationship; public disclosures | Your `member` entry + disclosures in a PR updating `council-roster.json` |
| **External reviewer** (non-voting, evidence track) | One review, ~4–8 h | Research-level expertise in ≥1 flagship case (see `review/external-review/REVIEWER_PACKET.md`) | A signed `SIGNOFF-<id>.json` — an AGREE_WITH_LIMITS or negative review is equally publishable |
| **Selection observer** | ~1 h | Any independent party (journal club, 机构, colleague) | Observer entry + confirmation that the nomination process was followed |

## Mechanics

1. Open a PR adding yourself (member/observer) with the disclosures object
   filled — "none" must be stated explicitly. The maintainer may not edit your
   disclosure text; corrections go through your own follow-up PR.
2. For reviewers: reproduce from a clean clone (commands in the reviewer
   packet), record the HEAD you reviewed.
3. The first voting-seat member triggers the `public_nomination_period` gate;
   the first non-BioNexus-affiliated member starts the
   `minimum_non_bionexus_fraction` clock.

## What the maintainer cannot do (charter §2)

Label any RFC a Council decision, select the chair, count maintainer-affiliated
participants toward independence gates, or edit participant disclosures. The
first external participant is therefore the gate on every "adoption" claim in
this repository — including the ones this PR deliberately leaves open.
