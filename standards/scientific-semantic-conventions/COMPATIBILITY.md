# Compatibility policy

The registry version uses semantic versioning for the public data contract.

- Patch: editorial or distribution changes that do not change normative
  registry or conformance behavior.
- Minor: additive attributes, groups, enum values, aliases, or non-required
  group attributes. Strict producers need the new version to emit additions;
  older consumers preserve well-formed future values with warnings.
- Major: removals, type/cardinality changes, new required group attributes,
  stability regression, or reuse of an existing name for a new meaning.

Every normative change MUST update `schema_version`, `schema_url`, conformance
cases, and `release-manifest.json`. Content changes under an unchanged
`schema_url` are invalid.

Development versions may still change, but they follow the same explicit
version and manifest discipline. No compatibility statement implies empirical
or biological validity.
