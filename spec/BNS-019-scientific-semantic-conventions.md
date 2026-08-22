# BNS-019 — BioNexus Scientific Semantic Conventions

Status: **Development 0.1.0**  
Independent distribution: `standards/scientific-semantic-conventions/`  
Normative registry: `standards/scientific-semantic-conventions/registry.json`  
Envelope schema: `standards/scientific-semantic-conventions/schemas/envelope.schema.json`  
Conformance manifest: `standards/scientific-semantic-conventions/conformance/manifest.json`

## 1. Purpose

BioNexus Scientific Semantic Conventions define a shared, machine-readable
language for the meaning and evidence boundary of scientific AI outputs. They
are modeled after the interoperability role of OpenTelemetry Semantic
Conventions: a common vocabulary, not a workflow engine or analysis method.

The conventions SHALL let a producer describe at least:

- what biological unit a record concerns;
- what mathematical state a matrix is in;
- what kind of scientific claim is being made;
- what kinds of evidence are actually present;
- which alternative explanations are represented;
- how much positive support exists; and
- whether assessment is unassessed, assessed, conflicted, or abstained.

Conformance to BNS-019 is a software-contract statement. It is not evidence of
biological correctness, empirical calibration, external validation, or
community adoption.

## 1.1 Distribution boundary

BNS-019 is released as a language-neutral standards artifact, not as private
Python package data. Its normative contract uses UTF-8 JSON, JSON Schema
Draft 2020-12, and JSON conformance fixtures. An implementation MUST be able to
consume the unpacked distribution without importing `bionexus` or executing
Python.

The release manifest binds `BNS-019`, the artifact name, version, complete file
inventory, byte sizes, and SHA-256 digests. Consumers MUST verify it before
loading the registry. A missing, incomplete, path-unsafe, version-mismatched,
or digest-mismatched distribution MUST fail closed.

The manifest establishes content identity and completeness, not publisher
authenticity. Its attestation profile reuses
`bionexus.evidence-attestation.v1`: the attestation subject binds exact ZIP or
manifest bytes through `artifact_sha256`, while its claims bind the internal
`release_digest_sha256`. Existing trust-key authorization, expiry, signature,
and signed-revocation rules apply. An unsigned development release MUST NOT be
described as endorsed, certified, or authenticated.

The BioNexus Python runtime is a reference consumer. It MUST NOT maintain a
private fallback registry. In a source checkout it discovers the public
distribution; in an installed environment the same unpacked distribution is
selected with `BIONEXUS_SEMCONV_ROOT`.

## 2. Naming and ownership

Canonical attribute names SHALL be lowercase dotted namespaces with
`snake_case` components. BioNexus owns the unprefixed canonical namespace.
Third-party extensions MUST use `x.<vendor>.*`; an unowned custom attribute is
invalid for a producer.

Canonical names MUST NOT be reused for a different meaning. A released name or
value is deprecated before removal. Every registry document has one version,
one schema URL, one stability marker, and one content SHA-256.

The development registry defines:

| Attribute | Cardinality | Meaning |
|---|---:|---|
| `biological.unit` | one | Biological or acquisition unit represented |
| `matrix.state` | one | Mathematical expression-matrix state |
| `claim.type` | one | Strongest proposition asserted |
| `evidence.type` | many | Evidence classes actually present |
| `confound.type` | many | Alternative explanations assessed or unresolved |
| `warrant.level` | one | Ordered positive support ceiling |
| `warrant.status` | one | Orthogonal assessment state |

The JSON registry is normative for exact allowed values.

## 3. Warrant semantics

`warrant.level` and `warrant.status` MUST remain separate.

- `warrant.level` is ordered positive support:
  `unassessed < fragile < preliminary < supported < robust < replicated`.
- `warrant.status` describes assessment state:
  `unassessed | assessed | conflicted | abstained`.

`CONFLICTED` MUST NOT be encoded as a stronger or weaker rung in an ordinal
support ladder. `ABSTAIN` MUST NOT be encoded as weak positive evidence.

The current compatibility mapping is:

| BioNexus maturity | `warrant.level` | `warrant.status` |
|---|---|---|
| `UNASSESSED` | `unassessed` | `unassessed` |
| `ABSTAIN` | `unassessed` | `abstained` |
| `FRAGILE` | `fragile` | `assessed` |
| `CONFLICTED` | `fragile` | `conflicted` |
| `PRELIMINARY` | `preliminary` | `assessed` |
| `SUPPORTED` | `supported` | `assessed` |
| `ROBUST` | `robust` | `assessed` |
| `REPLICATED` | `replicated` | `assessed` |

## 4. Matrix-state integrity

`raw_counts`, `normalized_counts`, `log_normalized`, and `scaled` are distinct.
They describe representation, not data quality.

The legacy value `normalized_expression` is ambiguous and MUST fail closed.
An adapter MUST declare whether values are normalized but unlogged, or
log-normalized. BioNexus MUST NOT infer this from numeric appearance.

## 5. Convention groups

The development registry defines three groups:

- `scientific.dataset`: description of a dataset or matrix without asserting a
  finding;
- `scientific.claim`: a claim and its evidence boundary without requiring a
  matrix resource; and
- `scientific.observation`: a claim-bearing observation exchanged between
  tools.

Each group declares every referenced attribute as `required`, `recommended`,
or `opt_in`. Missing required attributes invalidate a record. Missing
recommended attributes emit warnings and are never silently filled.

## 6. Producer and consumer behavior

A conformant producer MUST:

1. resolve safe aliases to canonical names and values;
2. reject conflicting alias and canonical values;
3. reject unknown registered values;
4. reject ambiguous blocked legacy values;
5. emit deterministic, sorted, duplicate-free multi-value attributes; and
6. emit an envelope fingerprint over the complete semantic payload.

A conformant consumer MUST preserve unknown future enum values and unknown
well-formed future canonical attributes with explicit warnings. It MUST still
reject malformed names, type/cardinality violations, missing required fields,
and fingerprint mismatches.

## 7. Envelope

Every portable semantic envelope contains:

```json
{
  "schema_url": "urn:bionexus:scientific-semantic-conventions:0.1.0",
  "convention": "scientific.observation",
  "producer": "bionexus.spatial.inference_validity",
  "record_id": "observation-42",
  "source_record_sha256": "<64 lowercase hex characters>",
  "attributes": {
    "biological.unit": "cell",
    "matrix.state": "log_normalized",
    "claim.type": "associative",
    "evidence.type": ["computational_result"],
    "confound.type": ["segmentation", "transcript_leakage"],
    "warrant.level": "fragile",
    "warrant.status": "assessed"
  },
  "semantic_fingerprint_sha256": "<64 lowercase hex characters>"
}
```

The fingerprint is SHA-256 over UTF-8 canonical JSON of every envelope field
except `semantic_fingerprint_sha256`, using sorted object keys and compact
separators. It protects meaning-bearing metadata from silent mutation; it does
not authenticate the producer.

## 8. Evolution and stability

Registry stability follows:
`development -> alpha -> beta -> release_candidate -> stable`.

Before `stable`, changes remain possible but MUST change the schema version and
schema URL. After `stable`, the following are breaking and require a new major
version or a separately named convention:

- removing an attribute, group, or enum value;
- changing type or cardinality;
- making an optional/recommended attribute required;
- reducing stability; or
- changing content while retaining the same schema URL.

Additive attributes, groups, and enum values are compatibility candidates.
They still require a versioned registry release and producer/consumer contract
tests.

## 9. Current conformance boundary

The Spatial Alternative Explanation Battery is the first native producer. It
emits `scientific.observation` semantics without promoting a spatial
association to mechanism or causality.

CellTypePilot, Spatial Evidence Layer, nf-core, Scanpy, Seurat, Claude, Codex,
and third-party plugins are target integrations, not current conformance or
adoption claims. A target may be listed as conformant only after it emits or
consumes a versioned envelope and passes the published contract suite.

The distribution's conformance manifest names each JSON input, validation
posture, expected validity, canonical normalized output, or stable failure
class. A language implementation conforms only when it passes every applicable
case against an unmodified, manifest-verified release. Passing one BioNexus
Python test suite does not certify another implementation.

## 9.1 Reproducible release artifact

`scripts/build_semantic_standard_release.py` verifies the complete release and
produces a deterministic ZIP plus a SHA-256 sidecar. Rebuilding identical
inputs MUST produce identical archive bytes. The ZIP is a transport container;
`release-manifest.json` remains the internal identity and integrity contract.

## 9.2 Multi-implementation interoperability trial

The non-normative implementation and public-trial kit lives under
`interoperability/bns019/`. Python and R are separate validator
implementations; Scanpy/AnnData, Seurat, and nf-core/Nextflow are host or
workflow adapters. An adapter that reuses a validator MUST NOT be counted as an
additional independent semantic implementation.

Every entry binds the exact release digest, executes the public fixtures, and
reports `PASS`, `FAIL`, `NOT_RUN`, or `ERROR`. Missing host runtimes and adapter
core-only checks are `NOT_RUN`, never implied conformance. The public success
gate additionally requires published CI evidence and at least one reproducible
implementation from a party independent of BioNexus maintainers. Maintainer
self-tests cannot satisfy that gate and do not reactivate BCTK badging.

## 9.3 Neutral stewardship

BNS-022 defines the prospective governance transition for BNS-019. Technical
semantic authority, commercial product authority, and certification authority
are reserved to separate bodies. The proposed Scientific Semantics Council is
currently `FORMING`, not independently constituted. Until its public formation
gates pass, interim maintainers may publish development proposals but cannot
declare the standard stable, certify implementations, or restore badges.

This governance proposal does not retroactively change the frozen BNS-019 0.1.0
release. A future release adopts it only through a versioned RFC and public
decision record.

## 10. Design provenance

The design follows OpenTelemetry's published principles for common attributes,
dotted naming, semantic convention groups, stability, and forward-compatible
enum consumption:

- <https://opentelemetry.io/docs/specs/semconv/>
- <https://opentelemetry.io/docs/specs/semconv/general/naming/>
- <https://opentelemetry.io/docs/specs/semconv/general/semantic-convention-groups/>
- <https://opentelemetry.io/docs/specs/otel/versioning-and-stability/>

BioNexus does not claim affiliation with or endorsement by OpenTelemetry.
