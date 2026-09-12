# BioNexus support

For usage questions, reproducible bugs, and feature requests, open a GitHub
issue at <https://github.com/HERRY423/BioNexus/issues>. Include the BioNexus
version, host (ChatGPT/Codex, Claude Code, or CLI), operating system, exact
command or prompt, and sanitized error output.

Do not post secrets, patient data, raw proprietary datasets, or embargoed
results. Security issues must follow [SECURITY.md](SECURITY.md), including
GitHub Private Vulnerability Reporting where available.

Support is best effort. A plugin response, local test pass, or support reply is
not scientific, clinical, regulatory, or institutional approval.

The current release-candidate line receives best-effort maintenance; no LTS or
response-time SLA is established. See [maintenance policy](MAINTENANCE.md) for
scope, responsibility, version changes and rollback.

The proposed Core 1.x GA contract covers 12 months from actual GA publication,
with precise dates and named maintainer acceptance required in that release.
It is not yet activated; see the maintenance policy for fixes, backports,
scientific rule changes and EOL. No response-time SLA is implied.

For DE handoffs, run `bionexus audit-de-verify BUNDLE_DIRECTORY` and include its
schema, status and sanitized issue codes. Exit 0 means file consistency only.
Old audit-only bundles return LEGACY_LIMITED (exit 3), retaining their evidence
gap. See [bundle compatibility](docs/de-bundle-compatibility.md).
