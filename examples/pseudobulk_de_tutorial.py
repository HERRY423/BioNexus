#!/usr/bin/env python3
"""Tutorial analysis: donor-aware pseudobulk DE on the Kang 2018 IFN-beta cohort.

Aggregates single cells to donor x condition pseudobulk samples (8 donors x
2 conditions), runs the canonical PyDESeq2 Wald test, writes ranked results,
and records the scientific claim in a Claim-Evidence Ledger (BNS-012) that
`bionexus verify` can audit. The claim is deliberately worded as ASSOCIATIONAL:
the design supports differential expression, not causation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_SRC = Path(__file__).resolve().parents[1] / "src"
_SKILL_SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "single-cell-rna-qc" / "scripts"
for _p in (_SRC, _SKILL_SCRIPTS):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from scrna_deseq import run_pydeseq2  # noqa: E402

from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef  # noqa: E402
from bionexus.provenance import sha256_file  # noqa: E402

DATASET = Path(__file__).resolve().parents[1] / "data" / "flagship" / "kang2018_pbmc_ifnb" / "pbmc_ifnb_counts.h5ad"


def pseudobulk(adata, donor_key: str = "donor", condition_key: str = "condition"):
    """Sum raw counts per donor x condition; returns (counts DataFrame, design DataFrame)."""
    import scipy.sparse as sparse

    x = adata.raw.X if adata.raw is not None else adata.X
    x = sparse.csr_matrix(x)
    genes = [str(g) for g in (adata.raw.var_names if adata.raw is not None else adata.var_names)]
    groups = (adata.obs[donor_key].astype(str) + "|" + adata.obs[condition_key].astype(str)).to_numpy()
    totals = np.zeros((len(np.unique(groups)), x.shape[1]), dtype=np.int64)
    unique_groups = list(dict.fromkeys(groups.tolist()))
    row_of = {g: i for i, g in enumerate(unique_groups)}
    for i, g in enumerate(groups):
        totals[row_of[g]] += np.asarray(x[i].todense()).ravel().astype(np.int64)
    counts = pd.DataFrame(totals, index=unique_groups, columns=genes)
    design = pd.DataFrame(
        {
            "sample_id": unique_groups,
            "donor": [g.split("|")[0] for g in unique_groups],
            "condition": [g.split("|")[1] for g in unique_groups],
        }
    )
    return counts, design


def main() -> int:
    parser = argparse.ArgumentParser(description="Donor-aware pseudobulk DE (tutorial)")
    parser.add_argument("--out", default="results", help="Output directory")
    args = parser.parse_args()

    import anndata as ad

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    adata = ad.read_h5ad(DATASET)
    counts, design = pseudobulk(adata)
    per_condition = design["condition"].value_counts().to_dict()
    assert min(per_condition.values()) >= 2, (
        "pseudobulk DE requires >= 2 biological replicates (donors) per condition; "
        f"got {per_condition}"
    )

    table, contract = run_pydeseq2(
        counts, design, condition="condition", reference="ctrl", contrast_level="stim"
    )
    table = table.sort_values("padj").reset_index(drop=True)
    table.to_csv(out / "pseudobulk_de_results.csv", index=False)

    significant = table[table["padj"] < 0.05]
    strong = significant[significant["log2FoldChange"].abs() >= 1.0]
    summary = {
        "n_pseudobulk_samples": int(len(design)),
        "donors_per_condition": per_condition,
        "n_genes_tested": int(len(table)),
        "n_significant_padj_lt_0_05": int(len(significant)),
        "n_significant_abs_lfc_ge_1": int(len(strong)),
        "top5": table.head(5)[["gene", "log2FoldChange", "padj"]].to_dict(orient="records"),
    }
    (out / "de_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    # Claim-Evidence Ledger (BNS-012): associational claim, three evidence nodes.
    ledger = ClaimLedger()
    dataset_hash = sha256_file(DATASET)
    ledger.add_evidence(EvidenceRef(
        ref_id="EVID-DATASET-KANG2018",
        kind="dataset",
        summary="Kang et al. 2018 GSE96583 PBMC, 8 donors x 2 conditions (IFN-beta stim vs ctrl), raw counts",
        maturity="PRELIMINARY",
        provenance={"path": str(DATASET), "sha256": dataset_hash},
    ))
    ledger.add_evidence(EvidenceRef(
        ref_id="EVID-METHOD-PSEUDOBULK-DESEQ2",
        kind="method_run",
        summary=(
            "Cells aggregated to donor x condition pseudobulk samples; PyDESeq2 Wald test "
            "with contrast stim vs ctrl (canonical gold backend, no cell-level testing)"
        ),
        maturity="PRELIMINARY",
        provenance={"backend": "pydeseq2", "aggregation": "donor x condition sum of raw counts"},
    ))
    ledger.add_evidence(EvidenceRef(
        ref_id="EVID-STAT-BH-WALD",
        kind="statistical_result",
        summary=f"{len(significant)} genes with BH-adjusted padj < 0.05; {len(strong)} with |log2FC| >= 1",
        maturity="PRELIMINARY",
        provenance={"multiple_testing": "Benjamini-Hochberg via PyDESeq2 IndependentFiltering"},
    ))
    ledger.add_claim(ClaimRecord(
        claim_id="CLAIM-IFNB-ASSOCIATIONAL-DE",
        statement=(
            f"IFN-beta stimulation is associated with differential expression of {len(significant)} "
            f"genes (padj < 0.05; {len(strong)} with |log2FC| >= 1) in a donor-aware pseudobulk "
            "design (8 donors per condition). This claim is associational: the within-donor "
            "stimulation design supports a stimulation response, but the analysis does not by "
            "itself establish the causal mechanism."
        ),
        capability_id="scrna.pseudobulk_de",
        supported_by=["EVID-DATASET-KANG2018", "EVID-METHOD-PSEUDOBULK-DESEQ2", "EVID-STAT-BH-WALD"],
    ))
    ledger.save(out / "bionexus.ledger.json")
    print(json.dumps({"summary": summary, "ledger": str(out / "bionexus.ledger.json")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
