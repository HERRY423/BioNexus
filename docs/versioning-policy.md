# BioNexus Semantic Versioning & Release Policy

BioNexus adheres to **Semantic Versioning 2.0.0** (`MAJOR.MINOR.PATCH`), adapted specifically for a **Scientific Reliability & Agent Skill Pack Layer** operating on AI coding agents (Codex, Claude Code, Cursor, Antigravity).

---

## 🏛️ 1. Semantic Versioning Specification

```text
MAJOR.MINOR.PATCH (e.g. 0.8.0 -> 1.0.0)
  │     │     │
  │     │     └── Bug fixes, heuristic calibration, backend compatibility updates
  │     └──────── New scientific capabilities, new skills, backwards-compatible contract extensions
  └────────────── Breaking schema changes (EvidenceCard, CapabilityContract), removal of deprecated capabilities
```

### 🔴 MAJOR Version Bumps (`X.0.0`)
A MAJOR bump is required when backward-incompatible changes are introduced to:
1. **EvidenceCard Schema**: Changes to the structure, required fields, or enum definitions of `ExecutionState`, `DimensionGrade`, or `ConclusionMaturity`.
2. **Capability Contract Schema**: Incompatible alterations to `CapabilityContract`, semantic input definitions, or refusal trigger interfaces.
3. **Core API / CLI Signatures**: Removal or breaking parameter changes in `bionexus` CLI subcommands or core Python APIs (`route_scientific_intent`, `evaluate_capability_preconditions`, `attach_meta`, `refuse`).
4. **Skill Removal**: Deleting any previously deprecated capability or skill.
5. **Platform Manifest Format**: Incompatible changes to generated `plugin.json`, `mcp.json`, or `.codex/config.json`.

---

### 🟡 MINOR Version Bumps (`0.X.0` / `X.Y.0`)
A MINOR bump is issued when new functionality is added in a backward-compatible manner:
1. **New Scientific Capabilities**: Registering new `CapabilityContract`s (e.g., spatial deconvolution, multiome integration).
2. **New Skills**: Adding new standard skill directories under `skills/`.
3. **New MCP Connectors**: Integrating additional remote scientific MCP servers into `bionexus.registry.yaml`.
4. **EvidenceCard Non-Breaking Enhancements**: Adding optional metadata keys or qualitative dimensions while preserving compatibility aliases.
5. **Benchmark Extensions**: Adding new benchmark evaluation suites or metric aggregators to `evals/`.

---

### 🟢 PATCH Version Bumps (`0.8.X` / `X.Y.Z`)
A PATCH bump is issued for backward-compatible bug fixes and optimizations:
1. **Heuristic Calibration**: Improvements to local numerical calculations (e.g. adjusted Rand index, Kabsch superposition).
2. **Backend Compatibility Patches**: Handling deprecations or upstream API changes in pinned bioinformatics libraries (`scanpy`, `squidpy`, `pydeseq2`, `lifelines`).
3. **Intent Regex Refinements**: Expanding pattern matching in `_INTENT_PATTERNS` to improve routing recall without changing behavior.
4. **Documentation & Benchmarks**: Updates to guides, docstrings, or test fixtures.

---

## 📅 2. Support Window & Lifecycle Policy

BioNexus follows a predictable **Active / Maintenance / End-of-Life (EOL)** support lifecycle:

| Branch / Release Stream | Status | Support Scope | Duration |
|---|---|---|---|
| **Latest Minor (`0.8.x`)** | 🟢 **Active** | Full feature additions, performance improvements, bug fixes, and security patches. | Until next Minor release |
| **Previous Minor (`0.7.x`)** | 🟡 **Maintenance** | Critical scientific correctness bugs and high-severity security patches only. | 6 months post-supersession |
| **Older Versions (`<= 0.6.x`)** | 🔴 **End-of-Life** | No further updates or patches. Users must migrate to latest release. | Immediate upon EOL |

---

## 🔒 3. Release Artifact Integrity & Provenance

Every official BioNexus release published to GitHub and PyPI must meet the following cryptographic requirements:
1. **SHA-256 Checksums**: Generated for all binary wheels (`.whl`) and source tarballs (`.tar.gz`).
2. **Provenance Record**: Captured using `bionexus.provenance.capture_environment()` and stored in the release payload.
3. **Zero Configuration Drift**: Verified against `bionexus registry --check` ensuring 100% synchronization across all platform manifests.
4. **Eval Benchmark Verification**: Must pass `bionexus eval` with a Composite Reliability Index $\ge 95.0\%$ and zero unsafe invocations.
