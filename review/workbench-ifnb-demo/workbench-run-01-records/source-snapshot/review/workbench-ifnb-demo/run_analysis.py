#!/usr/bin/env python3
"""Rebuild and analyse the public Kang 2018 IFN-beta scRNA-seq cohort."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import anndata as ad
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import io, sparse

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/flagship/kang2018_pbmc_ifnb"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_member(tf: tarfile.TarFile, name: str):
    handle = tf.extractfile(name)
    if handle is None:
        raise FileNotFoundError(name)
    return gzip.GzipFile(fileobj=handle)


def reconstruct() -> ad.AnnData:
    genes = pd.read_csv(
        Path(__file__).with_name("GSE96583_batch2.genes.tsv.gz"), sep="\t", header=None,
        names=["ensembl_id", "gene_symbol"], dtype=str,
    )
    meta = pd.read_csv(DATA / "GSE96583_batch2.total.tsne.df.tsv.gz", sep="\t", index_col=0)
    meta = meta.loc[meta["multiplets"].eq("singlet")].copy()
    matrices, barcodes, conditions = [], [], []
    specs = [("GSM2560248_2.1.mtx.gz", "GSM2560248_barcodes.tsv.gz"),
             ("GSM2560249_2.2.mtx.gz", "GSM2560249_barcodes.tsv.gz")]
    with tarfile.open(DATA / "GSE96583_RAW.tar") as tf:
        for condition, (matrix_name, barcode_name) in zip(["ctrl", "stim"], specs):
            with read_member(tf, matrix_name) as fh:
                matrices.append(io.mmread(fh).tocsr().T)
            with read_member(tf, barcode_name) as fh:
                names = [x.decode().strip() for x in fh if x.strip()]
                barcodes.extend(names)
                conditions.extend([condition] * len(names))
    x = sparse.vstack(matrices, format="csr")
    # Author combined metadata appends '1' to overlapping stimulated barcodes.
    # Resolve within condition, never join a barcode across the two libraries.
    source_index = pd.MultiIndex.from_arrays([conditions, barcodes])
    resolved_barcodes = meta.index.to_series().str.replace(r"-11$", "-1", regex=True)
    target_index = pd.MultiIndex.from_arrays([meta.stim, resolved_barcodes])
    if (x.shape != (len(barcodes), len(genes)) or not source_index.is_unique
            or not target_index.is_unique or not target_index.isin(source_index).all()
            or not genes.ensembl_id.is_unique):
        raise RuntimeError("GEO matrix, genes, barcodes, and author metadata do not align")
    row = pd.Series(np.arange(len(barcodes)), index=source_index).loc[target_index].to_numpy()
    x = x[row]
    if x.data.size and (not np.isfinite(x.data).all() or np.any(x.data < 0)
                        or not np.allclose(x.data, np.rint(x.data))):
        raise RuntimeError("input is not a non-negative integer count matrix")
    obs = meta.rename(columns={"ind": "donor", "stim": "condition", "cell": "source_cell_type"})
    out = ad.AnnData(x.astype(np.int64), obs=obs, var=genes.set_index("ensembl_id"))
    out.obs["total_counts"] = np.asarray(out.X.sum(axis=1)).ravel()
    out.obs["n_genes"] = np.asarray((out.X > 0).sum(axis=1)).ravel()
    mito = out.var.gene_symbol.str.startswith("MT-")
    out.obs["pct_mt"] = 100 * np.asarray(out[:, mito].X.sum(axis=1)).ravel() / out.obs.total_counts
    if not (out.obs.total_counts > 0).all():
        raise RuntimeError("zero-count cells: revise and version the QC plan before proceeding")
    return out


def aggregate(adata: ad.AnnData, cell_type: str):
    use = adata[adata.obs["source_cell_type"].eq(cell_type)]
    design = (use.obs[["donor", "condition"]].astype(str).drop_duplicates()
              .sort_values(["donor", "condition"]))
    design.index = design["donor"] + "|" + design["condition"]
    totals = []
    for _, r in design.iterrows():
        keep = use.obs["donor"].astype(str).eq(r.donor) & use.obs["condition"].eq(r.condition)
        totals.append(np.asarray(use[keep].X.sum(axis=0)).ravel())
    counts = pd.DataFrame(np.asarray(totals, dtype=np.int64), index=design.index, columns=use.var_names)
    design["sample_id"] = design.index
    if (len(design) != 16 or design.donor.nunique() != 8
            or set(design.condition) != {"ctrl", "stim"}
            or design.groupby("donor")["condition"].nunique().min() != 2):
        raise RuntimeError("expected eight donors, each with ctrl and stim")
    return use, counts, design


def run_de(counts: pd.DataFrame, design: pd.DataFrame) -> pd.DataFrame:
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats
    keep = (counts >= 10).sum(axis=0) >= 4
    model_counts = counts.loc[:, keep]
    metadata = design.set_index("sample_id")[["donor", "condition"]].loc[model_counts.index]
    dds = DeseqDataSet(counts=model_counts, metadata=metadata,
                       design="~ donor + condition", refit_cooks=True, n_cpus=1)
    matrix = np.asarray(dds.obsm["design_matrix"])
    if np.linalg.matrix_rank(matrix) != matrix.shape[1]:
        raise RuntimeError("paired design is not full rank")
    dds.deseq2()
    stats = DeseqStats(dds, contrast=["condition", "stim", "ctrl"], n_cpus=1)
    stats.summary()
    out = stats.results_df.reset_index(names="ensembl_id")
    return out.sort_values(["padj", "ensembl_id"], na_position="last")


def make_figure(adata, mono, counts, design, de, out: Path):
    rng = np.random.default_rng(42)
    sample = np.sort(rng.choice(adata.n_obs, min(12000, adata.n_obs), replace=False))
    sub = adata[sample]
    fig, ax = plt.subplots(1, 3, figsize=(16, 5))
    colors = sub.obs["condition"].map({"ctrl": "#4776E6", "stim": "#E45756"})
    ax[0].scatter(sub.obs.tsne1, sub.obs.tsne2, c=colors, s=2, alpha=.55, rasterized=True)
    ax[0].set(title="Author t-SNE: condition", xlabel="t-SNE 1", ylabel="t-SNE 2")
    for label, color in [("ctrl", "#4776E6"), ("stim", "#E45756")]:
        ax[0].scatter([], [], c=color, label=label, s=22)
    ax[0].legend(frameon=False)
    symbols = mono.var["gene_symbol"].astype(str)
    expected = [g for g in ["ISG15", "IFIT1", "MX1", "STAT1"] if g in set(symbols)]
    score_rows = []
    lib = counts.sum(axis=1)
    for gene in expected:
        cols = symbols.index[symbols.eq(gene)]
        value = np.log2(1 + counts.loc[:, cols].sum(axis=1).divide(lib) * 1e6)
        for sample_id, v in value.items():
            score_rows.append({"gene": gene, "sample": sample_id, "value": v,
                               "donor": design.loc[sample_id, "donor"],
                               "condition": design.loc[sample_id, "condition"]})
    scores = pd.DataFrame(score_rows)
    for i, gene in enumerate(expected):
        g = scores[scores.gene.eq(gene)]
        for donor in design.donor.unique():
            d = g[g.donor.eq(donor)].set_index("condition").value
            ax[1].plot([i-.14, i+.14], [d.ctrl, d.stim], color="#888", lw=.8, alpha=.7)
        for cond, x, color in [("ctrl", i-.14, "#4776E6"), ("stim", i+.14, "#E45756")]:
            ax[1].scatter(np.full(8, x), g[g.condition.eq(cond)].value, c=color, s=17)
    ax[1].set_xticks(range(len(expected)), expected)
    ax[1].set(title="CD14+ monocytes: paired donors", ylabel="log2(CPM + 1)")
    finite = de.dropna(subset=["padj", "log2FoldChange"]).copy()
    finite["mlog10"] = -np.log10(finite.padj.clip(lower=np.finfo(float).tiny))
    sig = finite.padj.lt(.05) & finite.log2FoldChange.abs().ge(1)
    ax[2].scatter(finite.log2FoldChange, finite.mlog10, c=np.where(sig, "#E45756", "#A9A9A9"), s=4, alpha=.55)
    top = finite.head(5)
    for _, r in top.iterrows():
        ax[2].annotate(r.gene_symbol, (r.log2FoldChange, r.mlog10), fontsize=7)
    ax[2].margins(x=.14)
    ax[2].axvline(0, color="black", lw=.7); ax[2].set(title="Paired pseudobulk DE", xlabel="log2 fold change (stim / ctrl)", ylabel="-log10 adjusted p")
    fig.suptitle("Kang 2018 GSE96583 — IFN-beta response with donor-aware evidence")
    fig.tight_layout(); fig.savefig(out / "showcase_figure.png", dpi=180); plt.close(fig)
    scores.to_csv(out / "prespecified_genes_by_donor.csv", index=False)


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default="review/workbench-ifnb-demo/results")
    args = ap.parse_args(); out = Path(args.out)
    if (out / "analysis_manifest.json").exists():
        raise FileExistsError("Use a new --out directory to retain the prior run")
    out.mkdir(parents=True, exist_ok=True)
    adata = reconstruct(); mono, counts, design = aggregate(adata, "CD14+ Monocytes")
    de = run_de(counts, design)
    de = de.merge(mono.var[["gene_symbol"]], left_on="ensembl_id", right_index=True, how="left")
    de.to_csv(out / "paired_pseudobulk_de.csv", index=False)
    design.to_csv(out / "pseudobulk_design.csv", index=False)
    counts.to_csv(out / "pseudobulk_counts.csv.gz", compression="gzip")
    adata.obs.to_csv(out / "cell_metadata_and_qc.csv.gz", compression="gzip")
    pd.crosstab(mono.obs.donor, mono.obs.condition).to_csv(out / "donor_cell_counts.csv")
    make_figure(adata, mono, counts, design.set_index("sample_id"), de, out)
    sys.path.insert(0, str(ROOT / "src"))
    from bionexus.annotation_evidence import assess_annotation_metadata
    identity_audit = assess_annotation_metadata({
        "candidate_label": "CD14+ Monocytes (source annotation)",
        "annotation_evidence": {"sources_declared": True},
        "calibration_context": {},
    }).to_dict()
    manifest = {
        "status": "COMPLETED_LOCAL_REHEARSAL_NOT_WORKBENCH_EVIDENCE",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "question": "Within source-annotated CD14+ monocytes, which genes differ after 6 h IFN-beta exposure?",
        "input": {"geo_accession": "GSE96583", "cells_all_singlets": adata.n_obs,
                  "monocyte_cells": mono.n_obs, "donors": int(design.donor.nunique()),
                  "conditions": ["ctrl", "stim"], "raw_tar_sha256": sha256(DATA / "GSE96583_RAW.tar"),
                  "metadata_sha256": sha256(DATA / "GSE96583_batch2.total.tsne.df.tsv.gz"),
                  "genes_sha256": sha256(Path(__file__).with_name("GSE96583_batch2.genes.tsv.gz"))},
        "method": {"unit": "donor x condition pseudobulk", "formula": "~ donor + condition",
                   "contrast": "stim vs ctrl", "gene_filter": "count >= 10 in >= 4 of 16 pseudobulk samples",
                   "multiple_testing": "Benjamini-Hochberg as returned by PyDESeq2"},
        "results": {"genes_tested": len(de), "padj_lt_0.05": int(de.padj.lt(.05).sum()),
                    "padj_lt_0.05_abs_lfc_ge_1": int((de.padj.lt(.05) & de.log2FoldChange.abs().ge(1)).sum()),
                    "top10": de.head(10)[["ensembl_id", "gene_symbol", "log2FoldChange", "padj"]].to_dict("records")},
        "bionexus_identity_audit": identity_audit,
        "limitations": [
            "Cell type is retained from the dataset authors; this run does not independently validate identity.",
            "Control and stimulation were sequenced as separate libraries, so condition and library are confounded.",
            "This is one SLE cohort with eight paired donors; findings are cohort-specific and require external replication.",
            "Association under this experimental dataset is reported; this analysis alone does not establish a general causal mechanism.",
            "No additional cell filtering beyond author singlet calls; inspect the saved per-cell QC before further use.",
            "Zero observed mitochondrial counts in this deposited matrix do not establish healthy mitochondrial QC.",
            "The left panel reuses author t-SNE coordinates for 12000 deterministically sampled cells; it is not a newly computed embedding.",
        ],
        "runtime": {"python": platform.python_version(), "pydeseq2": __import__("pydeseq2").__version__,
                    "anndata": ad.__version__, "platform": platform.platform()},
        "script_sha256": sha256(Path(__file__)),
        "qc": {"policy": "retain author singlets; report library size, genes, mitochondria; no additional post hoc filter",
               "monocyte_pct_mt_max": float(mono.obs.pct_mt.max()),
               "monocyte_n_genes_min": int(mono.obs.n_genes.min()),
               "monocyte_pct_mt_gt_20": int(mono.obs.pct_mt.gt(20).sum()),
               "mitochondrial_interpretation": "NOT_ASSESSED_ZERO_OBSERVED_MITO_COUNTS" if mono.obs.pct_mt.max() == 0 else "REQUIRES_REVIEW"},
        "output_sha256": {p.name: sha256(p) for p in out.iterdir() if p.is_file()},
    }
    (out / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(out.resolve()), **manifest["results"]}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
