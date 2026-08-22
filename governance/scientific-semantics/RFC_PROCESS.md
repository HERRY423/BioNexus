# Scientific semantics RFC process

Every normative change starts as `SSC-RFC-YYYY-NNNN` and includes:

1. producer and consumer use cases;
2. exact scientific meaning and out-of-scope interpretations;
3. regime limitations and risks of semantic overclaim;
4. namespace collision and external-standard analysis;
5. compatibility classification and migration plan;
6. language-neutral registry/schema patch;
7. conformance fixtures from at least two implementation paths;
8. institutional impact and accessibility review;
9. conflicts and funding disclosures; and
10. proposed decision class and review period.

The lifecycle is `DRAFT -> PUBLIC_REVIEW -> COUNCIL_REVIEW -> ACCEPTED | REJECTED | WITHDRAWN`.
Only an operational SSC may accept a normative RFC. Interim maintainers may
publish drafts and implementation experiments but cannot label them Council
decisions.

Accepted RFCs bind the decision record, exact source commit, registry diff,
tests, votes, recusals, objections, and target release. Rejected and withdrawn
RFCs remain archived so identifiers and rationales are never silently reused.
