# BioNexus Scientific Semantic Conventions

## Product thesis

The durable asset is not another analysis wrapper. It is a shared language for
what a scientific result means and what its evidence permits.

```text
unchanged workflow ──> Workflow Run RO-Crate ──> artifact entities
                                                   │
explicit producer/domain adapter ──────────────────┤
                                                   ├─ artifact A -> BNS-019
                                                   ├─ artifact B -> BNS-019
                                                   └─ artifact C -> unannotated
```

When every producer independently invents fields such as `unit`, `scale`,
`confidence`, or `validated`, downstream tools cannot tell whether the same
words mean the same thing. BNS-019 replaces those loose labels with a
versioned vocabulary, group requirements, fail-closed producer behavior, and
forward-compatible consumer behavior.

## Why this is a standards layer

OpenTelemetry Semantic Conventions define common names, types, meanings, and
allowed values so telemetry from different languages and vendors can be
correlated and consumed consistently. BioNexus applies that interoperability
pattern to scientific evidence meaning; it does not copy telemetry concepts or
claim OpenTelemetry compatibility.

The conventions are published independently from BioNexus Core so Python,
R, JavaScript, workflow engines, plugins, and archival systems can consume the
same bytes. BioNexus Core is one reference consumer. A capability can produce
better evidence, but neither BioNexus nor an external adapter can privately
redefine `claim.type=causal` or treat a conflicted result as a high warrant
level.

## The first development registry

| Namespace | Examples | Boundary enforced |
|---|---|---|
| `biological.unit` | `donor`, `sample`, `cell`, `spot`, `transcript`, `field_of_view` | Evaluation unit is explicit |
| `matrix.state` | `raw_counts`, `normalized_counts`, `log_normalized`, `scaled` | No ambiguous `normalized_expression` |
| `claim.type` | `descriptive`, `associative`, `population_effect`, `predictive`, `mechanistic`, `causal`, `clinical_actionable` | Strongest proposition is explicit |
| `evidence.type` | computation, orthogonal measurement, perturbation, replication, literature, external validation | Evidence classes are not collapsed into confidence |
| `confound.type` | donor, batch, segmentation, leakage, size, density, geometry and spatial sensitivity terms | Alternatives remain visible |
| `warrant.level` | `unassessed` through `replicated` | Positive support ceiling only |
| `warrant.status` | `unassessed`, `assessed`, `conflicted`, `abstained` | Conflict/abstention stay orthogonal |

The source of truth is the manifest-bound release under
`standards/scientific-semantic-conventions/`. `registry.json`, JSON Schemas,
and conformance fixtures are normative; Python modules and prose are
implementations or explanations.

RO-Crate owns execution provenance; BNS-019 does not duplicate it. The run is
only the container. Scientific meaning attaches to an individual output entity
and only when the meaning is explicitly supplied. A successful run, a familiar
filename, a samplesheet column, or a numeric matrix pattern is never sufficient
to infer scientific semantics.

## Minimal public contract

The independently releasable artifact contains:

- a versioned JSON registry;
- registry and envelope JSON Schemas;
- valid and invalid JSON conformance cases with canonical expected outputs or
  stable failure classes;
- compatibility and governance policies; and
- a complete SHA-256 release manifest.

The release can be parsed without Python. The BioNexus reference runtime reads
an unpacked artifact through `BIONEXUS_SEMCONV_ROOT`, verifies every listed
file, and fails closed on missing or mutated content. It has no internal
registry fallback.

## Interoperability contract

Producers are strict. A producer cannot invent an unversioned enum value,
silently reinterpret a matrix, omit a required attribute, or use a custom name
outside `x.<vendor>.*`.

Consumers are loss-preserving. A consumer accepts an unknown well-formed
future enum value or canonical attribute with a warning, allowing an older
reader to carry new meaning without pretending it understands it. Invalid
types, missing requirements, malformed namespaces, and fingerprint mismatch
still fail.

This asymmetry is intentional:

```text
producer uncertainty  ──> refuse to mint ambiguous semantics
consumer novelty      ──> preserve + warn, never silently discard
tampered envelope     ──> refuse
```

## Spatial is the first proving ground

`spatial.inference_validity` now emits a fingerprinted
`scientific.observation` envelope. The current adapter records:

- cell or spot resolution;
- counts or log-normalized matrix state;
- an associative claim ceiling;
- computational evidence;
- the represented alternative-explanation families; and
- the battery verdict as separate warrant level and status.

This is deliberately conservative. A ligand-receptor or contact-expression
result remains `associative`; running a battery does not manufacture
mechanistic or causal evidence.

## Adoption gates

Development 0.1.0 is an executable proposal, not yet a public standard. The
path to a defensible network effect is:

1. **Native dogfooding** — every BioNexus flagship emits an envelope and round
   trips it through a consumer.
2. **First-party adapters** — CellTypePilot and Spatial Evidence Layer map
   without semantic loss; ambiguous legacy fields are surfaced to researchers.
3. **Workflow and ecosystem adapters** — unchanged workflows emit native or
   RO-Crate provenance; an external adapter annotates only explicitly understood
   artifacts. Scanpy and Seurat exporters use the same conformance fixtures.
4. **Cross-agent consumption** — Claude/Codex plugins preserve unknown values,
   source hashes, and warrant boundaries.
5. **External governance** — independent maintainers review names, collision
   risks, biological regime coverage, and deprecations before `stable`.

A target is not marked adopted merely because documentation mentions it. The
minimum evidence is an identifiable adapter version, emitted fixture,
round-trip conformance result, and maintainer/reviewer ownership.

Likewise, `development 0.1.0` is not described as an industry standard. The
independent package makes adoption technically possible; independent
implementations, public change review, and neutral governance remain future
evidence gates.

## Change governance

Every proposed semantic change must include:

- a concrete producer and consumer use case;
- a definition that does not encode a method-specific score;
- collision analysis against existing meanings;
- cardinality and bounded-value design;
- compatibility classification;
- tests for strict production and forward-compatible consumption; and
- a named review owner.

Magic thresholds do not belong in this registry. Threshold selection remains
in the Empirical Calibration Layer, conditioned on tissue, platform,
reference, task, and evidence source. The conventions describe the meaning of
the resulting evidence; they do not smuggle a universal threshold into a field
name.

## References

- [OpenTelemetry Semantic Conventions](https://opentelemetry.io/docs/specs/semconv/)
- [OpenTelemetry naming guidance](https://opentelemetry.io/docs/specs/semconv/general/naming/)
- [OpenTelemetry semantic convention groups](https://opentelemetry.io/docs/specs/semconv/general/semantic-convention-groups/)
- [OpenTelemetry versioning and stability](https://opentelemetry.io/docs/specs/otel/versioning-and-stability/)

BioNexus is not affiliated with or endorsed by OpenTelemetry.
