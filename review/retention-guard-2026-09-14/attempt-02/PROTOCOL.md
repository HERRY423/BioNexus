# BN-DE-RETENTION-GUARD-20260914 attempt 02

This attempt follows the parent `PROTOCOL.md` without changing any endpoint,
input, audit call, or pass threshold. Attempt 01 stopped before case execution
because its candidate snapshot omitted packaged data files. Attempt 02 uses a
new output directory and snapshots every package file except caches and compiled
bytecode, including `bionexus/data/rule_registry.json`.

The gate remains exactly: valid retention 12/12, invalid acceptance 0/42, and
42/42 invalid cases with at least one `HIGH_IMPACT` or `BLOCKER` finding.

The evidence ceiling remains local developer-labelled regression only, with
scientific authorization `NONE`.
