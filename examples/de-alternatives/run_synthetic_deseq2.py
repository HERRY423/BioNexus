"""Execute a synthetic PyDESeq2 donor-influence example in a NEW output directory.

This is an optional caller-side example, not an executor inside BioNexus. It uses
the installed PyDESeq2 and exports actual fitted tables/designs for passive review.
No result from this example is evidence of biological validity or laboratory gain.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pydeseq2
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats
from scipy.stats import norm

from bionexus.de.alternatives import create_alternative_plan, evaluate_alternative_plan, render_alternatives


def write_json(path, value):
    path.write_bytes((json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))


def reference(root, path):
    return dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def fit_and_export(root, counts, metadata, memberships):
    root.mkdir()
    started = time.perf_counter()
    fitted = DeseqDataSet(counts=counts, metadata=metadata, design="~condition", refit_cooks=False,
                         size_factors_fit_type="ratio", fit_type="parametric", n_cpus=1, quiet=True)
    fitted.deseq2()
    stats = DeseqStats(fitted, contrast=["condition", "disease", "control"], alpha=0.05,
                      cooks_filter=False, independent_filter=False, n_cpus=1, quiet=True)
    stats.summary()
    table = stats.results_df.copy()
    # Unshrunk Wald intervals, in the same log2 units as LFC and lfcSE.
    result = pd.DataFrame(dict(gene=table.index, cell_type="synthetic_T", numerator="disease", denominator="control",
                              log2_fold_change=table.log2FoldChange.to_numpy(), padj=table.padj.to_numpy(),
                              ci_lower=(table.log2FoldChange - norm.ppf(.975) * table.lfcSE).to_numpy(),
                              ci_upper=(table.log2FoldChange + norm.ppf(.975) * table.lfcSE).to_numpy(), ci_level=.95))
    result.to_csv(root / "results.csv", index=False, lineterminator="\n")
    metadata.reset_index().to_csv(root / "metadata.csv", index=False, lineterminator="\n")
    counts.rename_axis("sample_id").reset_index().to_csv(root / "counts.csv", index=False, lineterminator="\n")
    memberships.to_csv(root / "cells.csv", index=False, lineterminator="\n")
    design = fitted.obsm["design_matrix"].copy()
    design.rename_axis("sample_id").reset_index().to_csv(root / "design.csv", index=False, lineterminator="\n")
    columns = list(design.columns)
    condition_column = next(c for c in columns if c != "Intercept")
    model = dict(schema_version="bionexus.de-model-record.v1",
                 artifact_sha256={role: reference(root, root / f"{role}.csv")["sha256"] for role in ("results", "metadata", "design")},
                 cell_type="synthetic_T", numerator="disease", denominator="control", effect_measure="log2_fold_change",
                 fit_status="converged", formula="~1+condition", statistical_unit="independent_donor",
                 design_columns=columns, encodings={"Intercept": dict(kind="intercept"),
                    condition_column: dict(kind="categorical", column="condition", level="disease")},
                 contrast={"Intercept": 0, condition_column: 1})
    # Convergence is exported from the actual per-gene fit diagnostic, not assumed
    # merely because the library returned a table.
    converged = bool(fitted.var.loc["X", "_LFC_converged"])
    model["fit_status"] = "converged" if converged else "failed"
    write_json(root / "model.json", model)
    contract = dict(schema_version="bionexus.de-claim-conditions.v1",
                    analysis=dict(cell_type="synthetic_T", numerator="disease", denominator="control"),
                    metadata_columns=dict(sample="sample", donor="donor", condition="condition"),
                    artifacts={role: reference(root, root / f"{role}.{'json' if role == 'model' else 'csv'}")
                               for role in ("results", "metadata", "design", "model")},
                    claims=[dict(claim_id="X-T", gene="X", direction="up", scope="cohort_association", alpha=.05)])
    write_json(root / "contract.json", contract)
    record = dict(schema_version="bionexus.de-alternative-run.v1", synthetic=True,
                  analysis_spec=dict(method="PyDESeq2", version=pydeseq2.__version__,
                    normalization="ratio;dispersion=parametric;refit_cooks=False",
                    test="Wald;lfc_null=0;cooks_filter=False;independent_filter=False", p_adjustment="BH"),
                  **{role: reference(root, root / name) for role, name in
                     (("contract", "contract.json"), ("counts", "counts.csv"), ("cells", "cells.csv"))})
    write_json(root / "run.json", record)
    print(f"Fitted {root.name}: X log2FC={table.loc['X', 'log2FoldChange']:.4f}, converged={converged}", flush=True)
    return dict(run=root.name, elapsed_seconds=time.perf_counter() - started, target_converged=converged)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    seed = 20261001
    rng = np.random.default_rng(seed)
    samples = [f"s{i}" for i in range(8)]
    genes = ["X", *[f"G{i:03d}" for i in range(119)]]
    means = rng.uniform(40, 140, len(genes))
    values = rng.negative_binomial(20, 20 / (20 + means), size=(8, len(genes)))
    # Planted sensitivity, not a discovery: d4 is deliberately influential.
    values[:, 0] = [60, 62, 58, 61, 220, 40, 42, 39]
    counts = pd.DataFrame(values, index=samples, columns=genes)
    meta = pd.DataFrame(dict(donor=[f"d{i}" for i in range(8)], condition=["control"] * 4 + ["disease"] * 4),
                        index=pd.Index(samples, name="sample"))
    cells = pd.DataFrame([dict(cell_id=f"{s}:synthetic-cell-{i}", sample_id=s) for s in samples for i in range(100)])
    receipts = [fit_and_export(root / "baseline", counts, meta, cells)]
    plan = create_alternative_plan(root / "baseline/run.json", root / "plan.json")
    # Plan bytes are frozen before the alternative fits in this local script.
    # This observation is not an independently timestamped preregistration.
    entries = []
    for spec in plan["specifications"]:
        retained = meta.index[meta.donor != spec["donor_id"]]
        receipts.append(fit_and_export(root / spec["spec_id"], counts.loc[retained], meta.loc[retained],
                                       cells.loc[cells.sample_id.isin(retained)]))
        entries.append(dict(spec_id=spec["spec_id"], status="completed",
                            record=reference(root, root / spec["spec_id"] / "run.json")))
    write_json(root / "runs.json", dict(schema_version="bionexus.de-alternative-results.v1",
                                       plan_sha256=reference(root, root / "plan.json")["sha256"], runs=entries))
    report = evaluate_alternative_plan(root / "plan.json", root / "runs.json")
    write_json(root / "review.json", report)
    (root / "REVIEW.md").write_bytes(render_alternatives(report).encode("utf-8"))
    write_json(root / "local-execution.json", dict(synthetic=True, seed=seed, python=platform.python_version(),
                pydeseq2=pydeseq2.__version__, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                executed_fits=len(receipts), runs=receipts, external_validation="NOT_ESTABLISHED",
                caveats=["Synthetic count data and membership manifest; no measured biological cells.",
                         "Outlier handling intentionally disabled in this planted influence diagnostic.",
                         "Wall-clock compute time is not human review time."]))
    print(json.dumps(report["claims"], indent=2), flush=True)


if __name__ == "__main__":
    main()
