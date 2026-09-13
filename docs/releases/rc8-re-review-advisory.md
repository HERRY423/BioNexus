# BioNexus rc8 Advisory: Re-review Guidance for Historical Reports

## Summary
In **BioNexus v1.0.0-rc.8**, several claim-evaluation and provenance rules have been hardened to eliminate severe semantic failure modes:
1. **Clause Independence**: Multi-clause assertions with contradictory, non-significant, or unverified secondary claims no longer inherit a passing verdict from an initial valid clause.
2. **Directional Effect Requirements**: Directional statements (\upregulated\, \downregulated\, \上调\, \下调\) require finite, non-zero, and sign-consistent effect size estimates.
3. **Multi-Gene Disambiguation**: Claims referencing multiple genes or ambiguous rows without separate per-gene clauses yield \MISSING_EVIDENCE\.
4. **Historical Report Provenance Quarantine**: The legacy report synchronizer (\sync_flagship_reports.py\) has been retired to read-only mode. Reports whose metadata was historically synced without fresh pipeline execution are quarantined under \alidation/history/pre-ga-provenance-01/\.

## Impact on Existing Reports
- **Legacy Reports with \ROBUST_PASS\**: If an older report relied on composite multi-gene phrasing, missing log2FC values, or unverified extrapolation, it will evaluate to \MISSING_EVIDENCE\ or \ISSUE_FOUND\ under rc8 rules.
- **Legacy DE Bundles (v1)**: Historical bundles remain readable with \LEGACY_LIMITED\ status. Their raw files and historical contents are byte-preserved and completely usable, but their legacy wording does not receive automatic endorsement under the new standard.

## Recommended Re-Review Procedure
To re-evaluate historical reports under rc8:
1. **Preserve Original Artifacts**: Do not overwrite historical report directories or manifests. Keep the legacy files intact for provenance and auditing.
2. **Create a Fresh Directory**: Execute the audit or verification into a new output directory:
   \\\ash
   bionexus audit-de --de-table path/to/results.csv --sample-metadata path/to/samples.csv --claim "GENE is significant." --bundle path/to/new_review_output/
   \\\
3. **Split Composite Claims**: If historical claims combined multiple findings in a single sentence without explicit per-gene subject bindings, split them into single-gene or separately scoped clauses:
   - *Previous*: \"POS1 is upregulated and NEG1 also changed."\
   - *Recommended*: \"POS1 is upregulated in the supplied table. NEG1 was not significant."\
4. **Verify Output with Manifest Anchor**:
   \\\ash
   bionexus audit-de-verify path/to/new_review_output/ --expected-manifest-sha256 <SHA256>
   \\\

## Authority and Scope Boundary
- All re-reviews emit:
  - \scientific_authorization: NONE\
  - \producer_authentication: NOT_ESTABLISHED\
  - \nalysis_execution_verification: NOT_PERFORMED\
- Compliance verification confirms consistency between data tables and natural language claims; it does not grant biological truth or independent experimental confirmation.
