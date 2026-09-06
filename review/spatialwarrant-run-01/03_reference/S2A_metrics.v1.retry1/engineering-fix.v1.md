# S2A retry1 minimal engineering fix

- Failed script SHA-256: 3539e9de7865a7e5f01f8135ccee8dfb516dd0eae9815e0f7ed9b02591999e20
- Retry1 script SHA-256: c94fd2bc5acc36330b32409fdbb79c0ef39f2c664efc52e36867462de83ab212
- Failed record SHA-256: 8613e81eaf5a8ecf97953f0eb2b5477dd5823717cbf06112a9c4f488ec576767
- Failed directory retained unchanged: C:\Plugin\BioNexus\review\spatialwarrant-run-01\03_reference\S2A_metrics.v1
- Retry output directory: C:\Plugin\BioNexus\review\spatialwarrant-run-01\03_reference\S2A_metrics.v1.retry1

Authorized changes only:
1. Changed the fixed output directory from `S2A_metrics.v1` to `S2A_metrics.v1.retry1`.
2. Added recursive conversion of NumPy integer, floating, boolean and ndarray values to strict JSON-native values; non-finite floating values become null and fields that can be missing retain separate missing flags.
3. Added a strict JSON serialization self-test before the complete matrix scan.
4. Added lineage references to the failed script and `failure.v1.json`, including their exact approved hashes.

Matrix parsing, formulas, identity handling, MT- prefix rule, index base, summaries, scientific scope and stop conditions are unchanged. See `engineering-fix.v1.diff` for the exact textual diff.
