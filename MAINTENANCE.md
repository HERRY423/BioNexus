# Maintenance and stable boundaries

Executable core quality gates, CLI compatibility and bounded DE requirement
evidence are documented in [engineering quality](docs/engineering-quality.md).

The first supported integration target is passive review of completed
multi-donor DE artifacts. Hosts choose tools and execute workflows; named
scientific owners adjudicate conclusions. Autonomous planning, scheduling,
hosted services and institution-wide certification are outside this boundary.
Existing experimental capabilities do not gain support guarantees by sharing
the package. See [scope](docs/product-matrix.md) and
[consumer compatibility](docs/de-bundle-compatibility.md).

## Support scope

`src/bionexus/versions.py` is the synchronized package version source. BioNexus
is in the 1.0.0 release-candidate series. Maintenance of the current RC line is
best effort. No GA/LTS window, paid SLA, staffed on-call rota or standing
independent scientific council is established. Older pinned versions remain
useful for reproduction but have no automatic backport commitment. A future
stable release must declare its support window and actual staffing capacity.

Core CI is configured for Python 3.10–3.12 on Linux, macOS and Windows. That is
a test target, not evidence that the current hosted run passed. Scientific
backends and host installation have separate acceptance requirements; a local
or no-dependency install does not establish clean-machine compatibility.

## Responsibility and triage

Repository maintainers receive issues through the existing GitHub forms. Each
accepted issue/PR needs an actual named assignee and reviewer; do not invent
standing appointments. The release operator is the person dispatching/tagging
that release and must link completed checks. The laboratory scientific owner
retains responsibility for adjudication.

| Issue | Required before closure |
|---|---|
| Scientific false acceptance/refusal | Reproduce the case; record affected rule/version/context; preserve the old result; add a regression and disclose changed interpretations |
| Compatibility or installation | Record OS/host/package/schema versions; reproduce with sanitized fixtures; verify the built wheel and migration |
| Data exposure/security | Follow private reporting in SECURITY.md; retain incident history and affected versions without posting research data |
| New capability | Identify user need, bounded interface, maintainer and test cost; defer expansion without maintenance capacity |

Closure links implementation, counterexample, completed checks and limitations.
Documentation or a new schema alone is not a fix. Missing expert review remains
unverified; it must not be relabelled independent approval.

## Compatibility and scientific changes

1. Preserve documented CLI flags, historical fixtures and v1 reader meanings.
   Additive metadata is allowed; unknown statuses/profiles fail closed.
2. Separate transport compatibility from scientific validity. A rule correction
   can change new assessments; it must not rewrite old reports or upgrade their
   NOT_ASSESSED states. Disclose contexts requiring fresh evaluation.
3. Breaking consumer changes need a new identifier, migration notes, old/new
   fixture coverage and an explicit transition. Never reuse an old meaning.
4. Pin exact versions/dependencies for reproduction. Review dependency changes
   in bounded PRs with affected tests; upgrades do not prove scientific validity.

## Release and rollback

- Select an existing tag and check out that exact tag's commit. Verify tag,
  source and package versions agree before build/publish.
- Complete source, registry and historical bundle checks. Record scope and
  failures; unavailable checks stay unverified.
- Install the exact wheel in an isolated environment, read historical bundles
  and verify packaged schemas there, then exercise current output. Retain source,
  resolved dependencies and wheel checksums.
- Attach before/after cases for changed scientific rules and list contexts
  requiring reassessment. Preserve negative studies and remaining limitations.
- Publish only after required hosted jobs complete. A workflow file alone is
  not a passed release. Keep previous artifacts/hashes available; roll back by
  installing the pinned earlier version in a separate environment, retaining
  both generations of evidence. Never edit an old bundle to appear current.

## Sustainable cadence

The existing scheduled CI provides recurring technical signals. Triage its
actionable failures, review dependencies before release, and periodically
review scope, stale issues and maintenance capacity. This document does not
create a new scheduled service. Mark unmaintained capabilities experimental or
narrow support rather than promise unavailable staffing.

Engineering guidance: [nf-core pipeline practices](https://nf-co.re/docs/guidelines/pipelines/overview).
BioNexus is not an nf-core pipeline; this is not an endorsement.
