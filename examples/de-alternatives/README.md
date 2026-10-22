# DE alternative analyses: a runnable synthetic example

`run_synthetic_deseq2.py` is an optional **caller-side example**. It executes the
installed PyDESeq2, exports actual fitted tables and design matrices, then asks
the passive BioNexus verifier to inspect the returned artifacts. BioNexus does
not install a backend, launch a remote job or become an analysis orchestrator.

```bash
python examples/de-alternatives/run_synthetic_deseq2.py --output review/my-new-synthetic-alternatives
```

Requires NumPy, pandas, SciPy and PyDESeq2 (locally exercised with 0.5.4).
Output must be a new directory. The fixed seed creates 8 synthetic donors and
120 genes. The target gene deliberately includes an influential donor; the
membership manifest is synthetic, not a collection of measured cells.

The script runs a baseline and 8 leave-one-donor-out fits, exports unshrunk Wald
intervals, and preserves the exact returned adjusted P values. Outlier filtering
and independent filtering are explicitly disabled for this planted influence
diagnostic; this is not a recommended universal analysis recipe.

The plan is written before the alternative fits in this script. This is locally
observable execution order, not independent preregistration authentication.

Outputs:

- `plan.json` and `runs.json`: frozen specifications and all returned slots.
- `baseline/` and `lodo-*/`: fitted result, design, metadata, counts, membership,
  model and claim contract, with byte bindings.
- `REVIEW.md` and `review.json`: numerical comparison, donor dependence and limits.
- `local-execution.json`: library/runtime versions, seed, source digest and local
  fit timing. Compute timing is not human review time.

The recorded local example is available in
[the review directory](../../review/de-alternatives-2026-10-01/synthetic-executed/REVIEW-rechecked.md).
Its baseline target estimate was +0.511 (adjusted P = 0.948); removing donor d4
gave -0.588 (adjusted P = 0.638). This demonstrates direction sensitivity, not a
significant biological discovery. All 9 target fits reported convergence.

The core test suite additionally checks method and gene-filter alternatives
using explicitly synthetic artifact fixtures. Those tests do not execute edgeR
or establish cross-method scientific equivalence.

See the [complete contract and interpretation guide](../../docs/de-alternative-analysis.zh-CN.md).
