# Run 01 setup failure

- Stage: candidate import, before any of the 54 cases were executed.
- Cause: `run_guard.py` snapshotted only `*.py` files and omitted the packaged
  `bionexus/data/rule_registry.json` resource required during import.
- Error: `RuleRegistryError: Rule provenance registry not found`.
- Result: no endpoint was calculated and this attempt provides no performance
  evidence.
- Preservation: the incomplete `candidate-source/`, `IDENTITY.json`,
  `INPUT_MANIFEST.json`, and `candidate.patch` are retained and will not be
  overwritten. The corrected attempt uses `attempt-02/`.
