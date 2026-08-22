# BioNexus Scientific Semantic Conventions

This directory is the independently releasable, language-neutral distribution
of BNS-019. It is the normative source for BioNexus scientific semantics; the
BioNexus Python package is only one consumer.

Status: **development 0.1.0**. Conformance means that an implementation passes
the published contract cases. It does not establish biological correctness,
empirical calibration, external validation, community adoption, or BioNexus
endorsement.

## Normative files

- `registry.json` defines names, values, aliases, blocked legacy values, and
  convention-group requirements.
- `schemas/registry.schema.json` validates the registry document.
- `schemas/envelope.schema.json` validates the portable envelope shape.
- `schemas/conformance-manifest.schema.json`, `conformance/manifest.json`, and
  its JSON inputs define implementation-neutral producer conformance cases.
- `release-manifest.json` binds the release identity to SHA-256 digests of all
  distributed files except the manifest itself.

All normative data is JSON encoded as UTF-8. No Python module, package import,
or BioNexus runtime is needed to read the contract. The prose specification is
`spec/BNS-019-scientific-semantic-conventions.md` in the parent repository.

## Consumer integration

An implementation MUST verify `release-manifest.json` before consuming a
registry. A producer MUST reject unknown or ambiguous registered semantics. A
consumer may preserve well-formed future values with an explicit warning, as
defined by BNS-019.

The manifest detects incomplete or mutated release contents but does not by
itself authenticate a publisher. Its `attestation_profile` reuses the
`bionexus.evidence-attestation.v1` contract: a signature binds the exact ZIP or
manifest bytes by artifact SHA-256 and carries `release_digest_sha256` as a
required claim. Development 0.1.0 ships no self-issued endorsement or trust
anchor.

The BioNexus Python reference consumer discovers this directory in a source
checkout or reads `BIONEXUS_SEMCONV_ROOT`. It deliberately has no private
fallback registry.

## Release

Run `python scripts/build_semantic_standard_release.py --output-dir <dir>` from
the repository root. The command verifies the manifest and creates a
deterministic ZIP distribution plus its SHA-256 sidecar.

Licensed under Apache-2.0; see `LICENSE` in this distribution.
