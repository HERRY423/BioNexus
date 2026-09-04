# Annotation and clustering evidence handoffs

These changes keep BioNexus passive: the host supplies evidence or explicitly
invokes a bounded local analysis. No autonomous planning or tool selection is added.

## One annotation assessment

`assess_annotation_metadata(metadata)` uses the same engine as
`assess_annotation_evidence(label, AnnotationEvidence(...))`. Router output and
`enforce_evidence_ceiling` / `enforce_statistical_warrant` use this engine too.
Pass the same metadata to the ABI's `annotation_metadata` argument.

```python
from bionexus.annotation_evidence import assess_annotation_metadata
from bionexus.abi import enforce_statistical_warrant

metadata = {
    "candidate_label": "candidate T cell",
    "annotation_evidence": {
        "reference_mapping_score": 0.9,
        "marker_consistency": 0.85,
    },
    "negative_markers_tested": False,
    "calibration_context": {
        "tissue": "PBMC", "platform": "10x", "reference": "declared-reference-version",
        "task": "annotation", "default_evidence_source": "declared-scorer-version",
    },
}
assessment = assess_annotation_metadata(metadata)
ceiling = enforce_statistical_warrant(
    "scrna.annotation_evidence", "SUPPORTED", annotation_metadata=metadata,
)
assert ceiling == assessment.warrant_ceiling == "TENTATIVE"
```

The example values are declarations, not measured study results. Positive scores
without approved context-specific calibration remain TENTATIVE. A legacy
`annotation_evidence_available: true` records source existence only; it creates
no numerical measurement. Missing evidence, invalid/conflicting inputs, open-set
populations and discordant protein evidence retain their explicit negative states.
An external-validation boolean alone cannot bypass the annotation assessment.

The router stores the canonical result in `annotation_assessment`; its identity
ceiling, warrant assessment, remedies and blocked claims derive from that result.
Earlier technical preflight information is retained under `execution_preflight`.
Research purpose still describes intended-use requirements, not stronger evidence.

## Measure clustering stability before claiming it

The router requests perturbation evidence for stable/robust clustering language
at any cell count. It does not impose a new N=30 cutoff. Ordinary exploratory
clustering remains available. Backend and integrity refusal still take precedence.

Run a declared grid using installed canonical scientific backends:

```bash
python skills/single-cell-rna-qc/scripts/scrna_cluster_stability.py input.h5ad --output results/stability-run-1 --resolutions 0.4 0.8 --fractions 1.0 0.8 --seeds 42 --min-ari 0.8
```

The output directory must be new. The script copies the input AnnData, executes
all four declared runs, and retains cell IDs, numeric cluster labels and backend
contracts in `partitions.json`. It writes a separate `assessment.json`. A fallback
backend is rejected rather than counted as a Leiden run. A runtime failure produces
no completed stability assessment. The CLI success code means the measurement was
produced: inspect `criterion_met` to decide whether the declared criterion was met.

For host intake, supply the raw partitions as `data_metadata.clustering_stability`
and the current input's SHA-256 as `data_metadata.dataset_sha256`. Summary booleans
are ignored: ARI is recomputed after aligning shared cells by ID. Duplicate IDs,
non-finite criteria, wrong dataset binding, identical perturbation declarations,
and one-cluster/all-singleton partitions cannot establish stability. Pairwise
shared-cell counts and coverage remain visible; an overall ARI cannot establish
stability for rare populations omitted by resampling.

`--min-ari` is an explicitly declared engineering acceptance criterion, not an
empirically approved universal cutoff. Omit it to obtain measurements without a
pass criterion. Even a perfect score on synthetic partitions does not establish
cell identity, independent validation, or a population-level discovery.

## Benchmark behavior changes

The previous BF-026 and 30-cell frontier inputs now reach their intended limits.
Three existing single-resolution ROBUST-claim cases (BF-018, BF-038 and frontier
008) now additionally emit DEGRADED_ADVISORY. Their expected status was made more
conservative; their PRELIMINARY claim ceiling was not raised. Original historical
reports remain unchanged. Frontier accounting tests count actual failures instead
of requiring at least one bug to remain. TENTATIVE remains visible in the diagnostic
confusion matrix; its ordinal rank is a reporting convention, not empirical proof.

## Source and dependency freeze

From a clean committed checkout, run:

```bash
python scripts/capture_reproducibility.py --output .codex-reproduction-1
```

The new directory contains the exact Git source archive, commit/tree identity,
SHA-256 checksums, Python/OS metadata, and installed dependency version pins.
Dirty source is refused. Core and scientific CI jobs retain this snapshot even
when a test fails, so a captured environment never implies a successful job.
Install BioNexus from the source archive rather than substituting a package with
the same version number. Dependency pins apply to the recorded Python and OS;
they are not a portable wheel lock. Ignored datasets require separate acquisition
and checksum verification. External biological validation remains a separate gate.
