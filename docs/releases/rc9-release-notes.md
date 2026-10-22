# BioNexus v1.0.0-rc.9

This engineering prerelease closes false-pass and evidence-escalation paths while retaining legitimate conditional conclusions. It includes the accumulated implementation since rc.8, including DE selection/claim-condition review, deployment exchange contracts and Nextflow provenance admission.

## Corrected behavior

- DE admission rejects insufficient or malformed premises instead of permitting unsupported analyses.
- Failed Rosalind execution evidence stays failed or unaccepted; a receipt or caller assertion does not authenticate successful scientific execution.
- Reopened compliance ledgers continue their existing evidence chain.
- CLI, Python and MCP output contracts distinguish declared premises, integrity checks, execution, independent review and scientific authority. A positive conditional calculation is not a verified fact.
- SDK and legacy MCP transports share strict schemas, error handling and consistent text/structured payloads. Invalid arguments and exceptions return failures; unresolved intent remains NEEDS_DATA; insufficient replication remains ABSTAIN.
- MCP responses expose the local package-tree digest observed at process startup. Hash equality proves neither scientific validity nor which equal-byte checkout a host loaded.
- Version synchronization updates package manifests without changing historical scientific-review identity.

## Reassessment and compatibility

Reassess earlier positive reports that relied only on caller-declared metadata, failed external execution, coerced Boolean/count inputs or broken ledger continuation. Preserve the original report and create a linked new assessment; never silently overwrite old evidence. Existing narrow descriptive and conditional conclusions remain available when their own contract permits them.

Unsupported independent-truth, generated reviewer-approval and simulated host claims are withdrawn in `docs/trust-restoration.md`. Original evidence and correction inventories are retained. Historical review and validation versions intentionally need not match the current package version.

## Validation boundaries

The release workflow verifies version agreement, lint, unit and core quality gates, public/synthetic validation checks, package build and clean installed-wheel behavior before publishing assets. Consult the workflow for the tagged commit for actual outcomes; the existence of this document is not a passing run.

Earlier frozen working-candidate SDK, legacy and isolated Codex app-server checks remain engineering evidence for those exact bytes. Local desktop binding was configured with rollback, but its final reload/native-path acceptance was not completed in the recorded handoff. This prerelease does not convert that pending state into acceptance, and publishing does not automatically update an already running desktop MCP process.

No new real laboratory pilot was run. External scientific validity, real workflow benefit, named human sign-off and GA support activation remain unestablished. Research use only.

## Installation

Use the rc.9 wheel attached to this GitHub Release when preparing a runtime, with the `mcp` extra for SDK transport. Verify `bionexus --version` and the runtime package digest after restarting the host. Python metadata normalizes the version to `1.0.0rc9`; plugin manifests and Git use `1.0.0-rc.9` / `v1.0.0-rc.9`.

The MCP extra pins SDK 1.28.1, the transport API verified for this candidate. MCP 2.x changed the server API and is not an accepted runtime for rc.9. The pinned dependency prevents a fresh installation from silently selecting that incompatible major version.

Machine-local configuration backups, raw desktop logs, private paths and unpublished research materials are not release assets. They remain preserved locally. A GitHub prerelease is not a PyPI publication.
