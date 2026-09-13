# Versioning and support contract

BioNexus uses MAJOR.MINOR.PATCH versioning. `src/bionexus/versions.py` is the
package version source; release tags and generated manifests must agree.
An RC version does not activate a stable support commitment.

The Core 1.0 supported surface is explicitly frozen in
[`core-support.v1.json`](../src/bionexus/data/core-support.v1.json).
[GA_CRITERIA.md](../GA_CRITERIA.md) defines acceptance and
[MAINTENANCE.md](../MAINTENANCE.md) is the support-policy authority.

| Change | Version and migration obligation |
|---|---|
| Breaking supported API, CLI, schema or scientific meaning | Major version, new incompatible contract identifier, migration and historical reader fixtures |
| Compatible optional fields or supported features | Minor version with documented scope; adding capabilities does not automatically add Core support |
| False-pass/false-refusal correction or compatible fix | Patch, rule IDs, affected contexts, before/after cases and reassessment notice |
| Documentation or reporting view | Preserve historical execution identity; never rebind old reports to the new version |

Scientific corrections are not permission to silently change claim meanings.
Existing assessments retain their original source, rule and evidence identities;
reassessment creates a new artifact linked to the old one.

## Support activation and lifecycle

The proposed Core 1.x window is **12 calendar months from actual Core 1.0 GA**.
Publish exact start and EOL dates and named accepting maintainers in
`release/GA_ACTIVATION.json` and the release notes. Until then support is
**PROPOSED / NOT ACTIVATED** and RC maintenance remains best effort.
The activation record's version remains `1.0.0` for later 1.x releases; minor
and patch publication do not restart its twelve-month clock. Extending the
commitment requires a separately reviewed, dated support-contract change.

Fixes ship on the newest supported 1.x minor. Prior minors receive critical
security and scientific false-pass backports for **90 days** after their
successor, bounded by the published 1.x EOL. A compatible-fix exception requires
a public mitigation and upgrade notice. Give at least **90 days**' EOL notice.
There is no separate six-month prior-minor support promise.

Supported API removal requires a major release after at least two minor
releases and six months of deprecation, whichever is longer. This compatibility
notice period does not extend the published support/backport window. The
[deprecation policy](deprecation-policy.md) uses the same distinction.

## Release evidence

Release gates validate version agreement, frozen support scope, actual named
activation for stable releases, types, fixed coverage, regression cases,
source/wheel compatibility, checksums and build provenance. Execution evidence,
scientific validation, external host acceptance and human authority are
different records. An aggregate benchmark score cannot substitute for a
known severe failure closure or establish scientific validity.
