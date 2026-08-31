# BioNexus external standards contribution packet

This directory contains portable artifacts offered for review. It does not
claim that BioNexus is a standard or that any external body has adopted,
endorsed, or certified these materials.

- `bionexus-context.jsonld` is the small JSON-LD vocabulary used inside
  Workflow Run RO-Crates.
- `bionexus-workflow-run-profile.md` states the proposed profile constraints
  and their evidence boundary.
- `ga4gh-aiws-contribution.md` is the human-reviewed contribution text for the
  GA4GH Artificial Intelligence Work Stream.
- `elixir-interoperability-contribution.md` is the human-reviewed contribution
  text for the ELIXIR Interoperability Platform.
- `SUBMISSION_TRACKER.json` records actual submission state. A prepared packet
  is never counted as submitted without a receipt or public URL.

WorkflowHub publication uses the official authenticated RO-Crate Submission
API. CI produces the validator-passing `crate.zip`; publication additionally
requires the accountable submitter's WorkflowHub API token and Team ID.
