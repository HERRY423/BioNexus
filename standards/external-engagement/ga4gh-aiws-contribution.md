# Draft contribution to the GA4GH Artificial Intelligence Work Stream

BioNexus offers a small, implementation-backed vocabulary and profile for
carrying evidence boundaries in Workflow Run RO-Crates. The contribution is
intended for technical discussion, not as a request for endorsement of the
BioNexus product.

The portable pieces are:

1. JSON-LD terms for execution state, conclusion maturity, evidence status,
   and six evidence dimensions;
2. a Workflow Run RO-Crate extension profile that preserves the authoritative
   RO-Crate and Workflow Run profile chain;
3. fail-closed export and official-validator CI tests; and
4. explicit semantics that forbid technical conformance from being converted
   into scientific or clinical evidence.

Requested review: whether these terms overlap existing or planned AI model,
dataset, provenance, or evaluation metadata work; which AIWS subgroup should
own further discussion; and what changes would make the fixtures useful
outside BioNexus.

Accountable submitter, affiliation, and contact: **REQUIRED BEFORE SUBMISSION**.
