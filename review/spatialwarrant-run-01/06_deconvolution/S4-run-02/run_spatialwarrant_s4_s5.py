from __future__ import annotations

import datetime as dt
import gc
import hashlib
import json
import math
import os
import pathlib
import platform
import shutil
import sys
import time
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any

import anndata as ad
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psutil
import scanpy as sc
import scipy
from scipy import sparse
from scipy.optimize import nnls
from scipy.spatial import cKDTree
from scipy.stats import spearmanr
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler


ROOT = pathlib.Path(r"C:\Plugin\BioNexus\review\spatialwarrant-run-01")
PLAN = ROOT / "00_plan" / "analysis-plan.lock.md"
GUIDE = pathlib.Path(r"C:\Users\13264\Downloads\spatial-transcriptomics-task-design-revised\WORKBENCH_EXECUTION_GUIDE.zh-CN.md")
REF_PATH = ROOT / "03_scrna_reference" / "S2-run-01" / "ref_40k.h5ad"
ANNOTATION_EVIDENCE = ROOT / "03_scrna_reference" / "S2-run-01" / "annotation_evidence.csv"
S3 = ROOT / "04_visium_qc" / "S3-run-03"
TENX = ROOT / "01_inputs" / "10x_blockA_section1"
S4 = pathlib.Path(sys.argv[1])
S5 = pathlib.Path(sys.argv[2])
PLAN_SHA = "854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82"
SECTIONS = ["1142243F", "1160920F", "CID4290", "CID4465", "CID44971", "CID4535"]
SEEDS = [20260904, 20260905, 20260906]
TRAIN_GENE_COUNTS = [500, 1000, 2000]
EPOCHS = 500
PRIMARY_GENE_COUNT = 1000
PRIMARY_SEED = 20260904
START_FREE = 30 * 1024**3
STOP_FREE = 20 * 1024**3
STAGE_CAP = 10 * 1024**3
STARTED_PERF = time.perf_counter()
STARTED_UTC = dt.datetime.now(dt.timezone.utc).isoformat()
PROC = psutil.Process()


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def native(x: Any) -> Any:
    if isinstance(x, np.bool_): return bool(x)
    if isinstance(x, np.integer): return int(x)
    if isinstance(x, np.floating):
        v = float(x)
        return v if math.isfinite(v) else None
    if isinstance(x, np.ndarray): return [native(v) for v in x.tolist()]
    if isinstance(x, pathlib.Path): return str(x)
    if isinstance(x, dict): return {str(k): native(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)): return [native(v) for v in x]
    if isinstance(x, float) and not math.isfinite(x): return None
    return x


def sha(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(4 * 1024**2), b""): h.update(b)
    return h.hexdigest()


def dir_size(path: pathlib.Path) -> int:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) if path.exists() else 0


def guarded(stage: pathlib.Path, extra: int = 0) -> int:
    free = shutil.disk_usage("C:\\").free
    if free < STOP_FREE:
        raise RuntimeError(f"C_DRIVE_WRITE_FLOOR free={free} floor={STOP_FREE}")
    if dir_size(stage) + extra > STAGE_CAP:
        raise RuntimeError(f"STAGE_OUTPUT_CAP path={stage} cap={STAGE_CAP}")
    return free


def atomic_json(path: pathlib.Path, obj: Any) -> None:
    data = (json.dumps(native(obj), ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    stage = S4 if S4 == path or S4 in path.parents else S5
    guarded(stage, len(data))
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    with tmp.open("xb") as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def write_text(path: pathlib.Path, text: str) -> None:
    stage = S4 if S4 in path.parents else S5
    data = text.encode("utf-8"); guarded(stage, len(data))
    with path.open("x", encoding="utf-8", newline="") as f:
        f.write(text); f.flush(); os.fsync(f.fileno())


def progress(stage: pathlib.Path, status: str, step: str, percent: float, **extra: Any) -> None:
    children = PROC.children(recursive=True)
    rss = PROC.memory_info().rss + sum(c.memory_info().rss for c in children if c.is_running())
    atomic_json(stage / "progress.json", {
        "status": status, "stage": step, "percent": round(float(percent), 3), "pid": os.getpid(),
        "elapsed_seconds": time.perf_counter() - STARTED_PERF, "current_process_tree_memory_bytes": rss,
        "free_C_bytes": shutil.disk_usage("C:\\").free, "updated_at_utc": now(), **extra,
    })


def normalize_log1p(x: sparse.spmatrix) -> sparse.csr_matrix:
    x = x.tocsr().astype(np.float32)
    total = np.asarray(x.sum(axis=1)).ravel()
    scale = np.divide(10000.0, total, out=np.zeros_like(total, dtype=np.float32), where=total > 0)
    y = sparse.diags(scale).dot(x).tocsr()
    y.data = np.log1p(y.data)
    return y


def read_hashes(path: pathlib.Path) -> dict[str, str]:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if len(line) >= 66:
            out[line[66:].strip().replace("\\", "/")] = line[:64]
    return out


def preflight() -> dict[str, Any]:
    if sha(PLAN) != PLAN_SHA: raise RuntimeError("LOCKED_PLAN_HASH_MISMATCH")
    if json.loads((ROOT / "03_scrna_reference/S2-run-01/S2-result.json").read_text())["status"] != "COMPLETED":
        raise RuntimeError("S2_NOT_COMPLETE")
    if json.loads((S3 / "S3-result.json").read_text())["status"] != "COMPLETED": raise RuntimeError("S3_NOT_COMPLETE")
    if (ROOT / "S4-S5-checkpoint.md").exists(): raise RuntimeError("ROOT_CHECKPOINT_COLLISION")
    s2h = read_hashes(ROOT / "03_scrna_reference/S2-run-01/SHA256SUMS.txt")
    s3h = read_hashes(S3 / "SHA256SUMS.txt")
    if s2h.get("ref_40k.h5ad") != sha(REF_PATH): raise RuntimeError("S2_REFERENCE_HASH_MISMATCH")
    if s2h.get("annotation_evidence.csv") != sha(ANNOTATION_EVIDENCE): raise RuntimeError("S2_ANNOTATION_HASH_MISMATCH")
    verified = []
    for sid in SECTIONS:
        p = S3 / sid / f"{sid}.h5ad"
        if s3h.get(f"{sid}/{sid}.h5ad") != sha(p): raise RuntimeError(f"S3_HASH_MISMATCH {sid}")
        verified.append({"section": sid, "path": str(p), "sha256": sha(p), "bytes": p.stat().st_size})
    free = shutil.disk_usage("C:\\").free
    if free < START_FREE: raise RuntimeError(f"C_DRIVE_START_FLOOR free={free} floor={START_FREE}")
    probe = S4 / f".write-check-{uuid.uuid4().hex}.tmp"; payload = uuid.uuid4().bytes
    with probe.open("xb") as f: f.write(payload); f.flush(); os.fsync(f.fileno())
    if probe.read_bytes() != payload: raise RuntimeError("WRITE_READBACK_FAILED")
    probe.unlink()
    return {"status": "PASS", "plan_sha256": sha(PLAN), "S2_reference_sha256": sha(REF_PATH),
            "S2_annotation_evidence_sha256": sha(ANNOTATION_EVIDENCE), "S3_files": verified,
            "free_C_bytes": free, "start_floor_bytes": START_FREE, "runtime_stop_floor_bytes": STOP_FREE,
            "write_flush_readback_delete": "PASS", "route": "local Python/scverse execution",
            "registered_NGS_workflow_run": "NONE"}


def marker_genes(ref: ad.AnnData) -> tuple[list[str], pd.DataFrame]:
    labels = ref.obs["producer_celltype_minor"].astype(str).to_numpy()
    x = normalize_log1p(ref.X)
    rows = []
    for label in sorted(set(labels)):
        inside = labels == label
        mean_in = np.asarray(x[inside].mean(axis=0)).ravel()
        mean_out = np.asarray(x[~inside].mean(axis=0)).ravel()
        det_in = np.asarray((x[inside] > 0).mean(axis=0)).ravel()
        det_out = np.asarray((x[~inside] > 0).mean(axis=0)).ravel()
        score = mean_in - mean_out
        order = np.lexsort((ref.var_names.to_numpy(str), -score))[:50]
        for rank, j in enumerate(order, 1):
            rows.append({"producer_celltype_minor": label, "rank": rank, "gene_symbol": str(ref.var_names[j]),
                         "mean_log1p_in": mean_in[j], "mean_log1p_out": mean_out[j], "difference": score[j],
                         "detected_fraction_in": det_in[j], "detected_fraction_out": det_out[j]})
    table = pd.DataFrame(rows)
    merged = (table.groupby("gene_symbol", sort=True)
              .agg(label_frequency=("producer_celltype_minor", "nunique"), best_rank=("rank", "min"), mean_difference=("difference", "mean"))
              .reset_index().sort_values(["label_frequency", "best_rank", "mean_difference", "gene_symbol"],
                                         ascending=[False, True, False, True], kind="stable"))
    genes = merged["gene_symbol"].tolist()
    table.to_csv(S4 / "reference-marker-top50-by-producer-label.csv", index=False)
    merged.to_csv(S4 / "deterministic-marker-gene-union.csv", index=False)
    del x; gc.collect()
    return genes, table


def tangram_worker(args: tuple[str, list[str]]) -> dict[str, Any]:
    sid, marker_union = args
    import tangram as tg
    import tangram.mapping_utils as mu
    # tangram-sc 1.0.4 passes a pandas Series to torch 2.14. Convert that same vector only.
    original_mapper = mu.mo.Mapper
    def compatible_mapper(*a, **kw):
        kw["d"] = np.asarray(kw["d"], dtype=np.float32)
        return original_mapper(*a, **kw)
    mu.mo.Mapper = compatible_mapper
    worker_proc = psutil.Process()
    ref = sc.read_h5ad(REF_PATH)
    sp = sc.read_h5ad(S3 / sid / f"{sid}.h5ad")
    available = set(sp.var_names.astype(str))
    section_candidates = [g for g in marker_union if g in available]
    section_out = S4 / "tangram-grid" / sid; section_out.mkdir(parents=True, exist_ok=False)
    runs = []
    for requested in TRAIN_GENE_COUNTS:
        genes = section_candidates[:requested]
        if not genes: raise RuntimeError(f"NO_TANGRAM_TRAINING_GENES {sid}")
        for seed in SEEDS:
            run_out = section_out / f"genes-{requested}_seed-{seed}"; run_out.mkdir()
            t0 = time.perf_counter(); started = now()
            record = {"section": sid, "requested_training_genes": requested, "candidate_training_genes": len(genes),
                      "seed": seed, "epochs": EPOCHS, "mode": "clusters", "cluster_label": "producer_celltype_minor",
                      "device": "cpu", "density_prior": "rna_count_based", "status": "RUNNING", "started_at_utc": started,
                      "compatibility_adjustment": "density prior pandas Series converted to NumPy float32 before unchanged Tangram optimizer"}
            write_text(run_out / "candidate-training-genes.txt", "".join(f"{g}\n" for g in genes))
            try:
                r = ref[:, genes].copy(); q = sp[:, genes].copy()
                tg.pp_adatas(r, q, genes=genes, gene_to_lowercase=False)
                actual_genes = list(r.uns["training_genes"])
                write_text(run_out / "training-genes.txt", "".join(f"{g}\n" for g in actual_genes))
                m = tg.map_cells_to_space(r, q, mode="clusters", cluster_label="producer_celltype_minor",
                                          device="cpu", num_epochs=EPOCHS, random_state=seed, verbose=False)
                tg.project_cell_annotations(m, q, annotation="producer_celltype_minor")
                comp = q.obsm["tangram_ct_pred"].copy()
                comp = comp.reindex(columns=sorted(ref.obs["producer_celltype_minor"].astype(str).unique()), fill_value=0.0)
                sums = comp.sum(axis=1).to_numpy(float)
                comp.loc[sums > 0, :] = comp.loc[sums > 0, :].div(sums[sums > 0], axis=0)
                comp.insert(0, "barcode", comp.index.astype(str)); comp.insert(0, "section", sid)
                comp.to_csv(run_out / "spot-by-celltype-composition.csv.gz", index=False,
                            compression={"method": "gzip", "mtime": 0})
                history = native(m.uns.get("training_history", {}))
                record.update({"status": "COMPLETED", "actual_training_genes": len(actual_genes),
                               "actual_training_gene_order_sha256": hashlib.sha256("\n".join(actual_genes).encode()).hexdigest(),
                               "actual_training_gene_membership_sorted_sha256": hashlib.sha256("\n".join(sorted(actual_genes)).encode()).hexdigest(),
                               "ended_at_utc": now(), "elapsed_seconds": time.perf_counter()-t0,
                               "common_feature_symbols": int(len(set(ref.var_names) & set(sp.var_names))),
                               "zero_sum_spots": int((sums <= 0).sum()), "training_history": history,
                               "peak_memory_bytes": getattr(worker_proc.memory_info(), "peak_wset", worker_proc.memory_info().rss)})
                atomic_json(run_out / "run.json", record)
                runs.append({k: record[k] for k in ["section", "requested_training_genes", "actual_training_genes", "seed", "epochs", "status", "elapsed_seconds", "peak_memory_bytes"]})
                del r, q, m, comp
            except Exception as exc:
                record.update({"status": "FAILED", "ended_at_utc": now(), "elapsed_seconds": time.perf_counter()-t0,
                               "error_type": type(exc).__name__, "error": str(exc), "traceback": traceback.format_exc()})
                atomic_json(run_out / "run.json", record); runs.append(record)
            gc.collect()
    return {"section": sid, "runs": runs, "peak_memory_bytes": getattr(worker_proc.memory_info(), "peak_wset", worker_proc.memory_info().rss)}


def collect_tangram() -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    primary = []; sensitivity = []; failures = []
    for sid in SECTIONS:
        pdir = S4 / "tangram-grid" / sid
        for requested in TRAIN_GENE_COUNTS:
            for seed in SEEDS:
                rdir = pdir / f"genes-{requested}_seed-{seed}"
                rec = json.loads((rdir / "run.json").read_text())
                if rec["status"] != "COMPLETED": failures.append(rec); continue
                df = pd.read_csv(rdir / "spot-by-celltype-composition.csv.gz")
                if requested == PRIMARY_GENE_COUNT and seed == PRIMARY_SEED: primary.append(df)
                base = pd.read_csv(pdir / f"genes-{PRIMARY_GENE_COUNT}_seed-{PRIMARY_SEED}" / "spot-by-celltype-composition.csv.gz")
                celltypes = [c for c in df.columns if c not in {"section", "barcode"}]
                corrs = []
                for c in celltypes:
                    rr = spearmanr(base[c], df[c]).statistic
                    corrs.append(rr if np.isfinite(rr) else np.nan)
                sensitivity.append({"section": sid, "requested_training_genes": requested,
                                    "actual_training_genes": rec["actual_training_genes"], "seed": seed,
                                    "mean_celltype_spearman_vs_primary": np.nanmean(corrs),
                                    "mean_absolute_difference_vs_primary": np.mean(np.abs(base[celltypes].to_numpy()-df[celltypes].to_numpy())),
                                    "dominant_component_agreement_vs_primary": np.mean(base[celltypes].idxmax(axis=1).to_numpy()==df[celltypes].idxmax(axis=1).to_numpy()),
                                    "elapsed_seconds": rec["elapsed_seconds"], "status": "COMPLETED"})
    if len(primary) != len(SECTIONS): raise RuntimeError(f"PRIMARY_TANGRAM_INCOMPLETE sections={len(primary)}")
    full = pd.concat(primary, ignore_index=True)
    sens = pd.DataFrame(sensitivity)
    full.to_csv(S4 / "proportions_tangram.csv.gz", index=False, compression={"method":"gzip","mtime":0})
    sens.to_csv(S4 / "tangram-parameter-sensitivity.csv", index=False)
    return full, sens, failures


def run_nnls(ref: ad.AnnData, marker_union: list[str]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    labels = sorted(ref.obs["producer_celltype_minor"].astype(str).unique())
    label_arr = ref.obs["producer_celltype_minor"].astype(str).to_numpy()
    rows, residuals, unknown = [], [], []
    norm_info = {"reference": "per-cell total-count normalize to 10000 then sparse log1p; mean within producer label",
                 "visium": "per-spot total-count normalize to 10000 then sparse log1p", "solver": "scipy.optimize.nnls",
                 "weights": "normalized to sum 1 when positive; zero-sum is unknown", "calibrated_cell_proportions": False,
                 "sections": {}}
    for si, sid in enumerate(SECTIONS):
        progress(S4, "RUNNING", "S4_MARKER_NNLS", 62 + si*2)
        sp = sc.read_h5ad(S3 / sid / f"{sid}.h5ad")
        genes = [g for g in marker_union if g in set(sp.var_names)]
        ridx = ref.var_names.get_indexer(genes); sidx = sp.var_names.get_indexer(genes)
        rx = normalize_log1p(ref.X[:, ridx]); qx = normalize_log1p(sp.X[:, sidx])
        template = np.vstack([np.asarray(rx[label_arr == lab].mean(axis=0)).ravel() for lab in labels]).T
        norm_info["sections"][sid] = {"common_marker_genes": len(genes), "feature_sha256": hashlib.sha256("\n".join(genes).encode()).hexdigest()}
        values = np.zeros((sp.n_obs, len(labels)), dtype=np.float32)
        for i in range(sp.n_obs):
            coef, resid = nnls(template, qx.getrow(i).toarray().ravel())
            total = coef.sum(); residuals.append({"section":sid,"barcode":str(sp.obs_names[i]),"residual_l2":resid,"weight_sum":total})
            if total > 0: values[i] = coef / total
            else: unknown.append({"section":sid,"barcode":str(sp.obs_names[i]),"reason":"NNLS_WEIGHT_SUM_ZERO"})
        df = pd.DataFrame(values, columns=labels); df.insert(0,"barcode",sp.obs_names.astype(str)); df.insert(0,"section",sid); rows.append(df)
        del sp, rx, qx, template; gc.collect()
    comp = pd.concat(rows, ignore_index=True); resid = pd.DataFrame(residuals); unk = pd.DataFrame(unknown, columns=["section","barcode","reason"])
    comp.to_csv(S4 / "proportions_marker_nnls.csv.gz", index=False, compression={"method":"gzip","mtime":0})
    resid.to_csv(S4 / "residuals.csv", index=False); unk.to_csv(S4 / "unknown_spots.csv", index=False)
    atomic_json(S4 / "normalization-and-feature-map.json", norm_info)
    return comp, resid, unk


def run_ingest(ref: ad.AnnData) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []; agreements = []
    from scanpy.tools._ingest import Ingest
    original_ingest_pca = Ingest._pca
    def sparse_ingest_pca(self, n_pcs=None):
        x = self._adata_new.X
        if sparse.issparse(x):
            if self._pca_use_hvg: x = x[:, self._adata_ref.var["highly_variable"]]
            basis = self._pca_basis[:, :n_pcs]
            projected = x.dot(basis)
            if sparse.issparse(projected): projected = projected.toarray()
            projected = np.asarray(projected, dtype=np.float32)
            if self._pca_centered:
                projected -= np.asarray(x.mean(axis=0)).ravel() @ basis
            return projected
        return original_ingest_pca(self, n_pcs)
    Ingest._pca = sparse_ingest_pca
    hvg = pd.read_csv(ROOT / "03_scrna_reference/S2-run-01/batch-aware-HVG.csv")
    hvg_genes = hvg.loc[hvg["selected"].astype(bool), "gene_symbol"].astype(str).tolist()
    labels = ref.obs["producer_celltype_minor"].astype(str)
    for i, sid in enumerate(SECTIONS):
        progress(S4,"RUNNING","S4_SCANPY_INGEST",75+i*1.5)
        sp = sc.read_h5ad(S3/sid/f"{sid}.h5ad")
        genes = [g for g in hvg_genes if g in set(sp.var_names)]
        r = ad.AnnData(X=normalize_log1p(ref[:,genes].X), obs=pd.DataFrame({"producer_celltype_minor":labels.to_numpy()}, index=ref.obs_names.copy()), var=pd.DataFrame(index=genes))
        q = ad.AnnData(X=normalize_log1p(sp[:,genes].X), obs=pd.DataFrame(index=sp.obs_names.copy()), var=pd.DataFrame(index=genes))
        sc.pp.pca(r, n_comps=min(30,len(genes)-1), zero_center=False, random_state=PRIMARY_SEED)
        sc.pp.neighbors(r, n_neighbors=15, n_pcs=min(30,len(genes)-1), random_state=PRIMARY_SEED)
        sc.tl.ingest(q, r, obs="producer_celltype_minor", embedding_method="pca")
        knn = NearestNeighbors(n_neighbors=5).fit(r.obsm["X_pca"]); dist, ind = knn.kneighbors(q.obsm["X_pca"])
        ref_lab = labels.to_numpy(); neigh = ref_lab[ind]
        agreement = np.asarray([np.mean(v == v[0]) for v in neigh])
        ambiguity = np.divide(dist[:,0],dist[:,1],out=np.ones(len(dist)),where=dist[:,1]>0)
        transferred = q.obs["producer_celltype_minor"].astype(str).to_numpy()
        for j,b in enumerate(sp.obs_names.astype(str)):
            rows.append({"section":sid,"barcode":b,"transferred_label":transferred[j],"nearest_neighbor_label_agreement":agreement[j],
                         "nearest_distance_ratio":ambiguity[j],"numeric_leiden_0_5":str(sp.obs["numeric_leiden_0_5"].iloc[j]),
                         "interpretation":"mixed-spot transferred similarity label; no proportion"})
        tab = pd.crosstab(pd.Series(sp.obs["numeric_leiden_0_5"].astype(str).to_numpy(),name="numeric_leiden_0_5"), pd.Series(transferred,name="transferred_label"))
        for cluster,row in tab.iterrows():
            for lab,val in row.items(): agreements.append({"section":sid,"numeric_leiden_0_5":cluster,"transferred_label":lab,"spots":int(val)})
        del sp,r,q; gc.collect()
    out=pd.DataFrame(rows); agree=pd.DataFrame(agreements)
    out.to_csv(S4/"ingest_labels.csv.gz",index=False,compression={"method":"gzip","mtime":0}); agree.to_csv(S4/"ingest_confusion_by_section.csv",index=False)
    return out,agree


def section_coords(sid: str) -> pd.DataFrame:
    out = pd.read_csv(S3/sid/"spot-QC-and-metadata.csv.gz", index_col=0)
    out.index = out.index.astype(str); out.index.name = "barcode"
    return out


def plot_s4(tgcomp: pd.DataFrame, nncomp: pd.DataFrame, ingest: pd.DataFrame, sens: pd.DataFrame) -> None:
    focus = ["CAFs MSC iCAF-like","CAFs myCAF-like","T cells CD8+","Macrophage",
             "Endothelial ACKR1","Endothelial CXCL12","Endothelial Lymphatic LYVE1","Endothelial RGS5"]
    for sid in SECTIONS:
        d=tgcomp[tgcomp.section==sid].set_index("barcode"); c=section_coords(sid).loc[d.index]
        fig,axs=plt.subplots(2,4,figsize=(16,8))
        for ax,lab in zip(axs.ravel(),focus):
            im=ax.scatter(c.px_col,c.px_row,c=d[lab],s=6,cmap="viridis",rasterized=True);ax.invert_yaxis();ax.set_title(lab,fontsize=8);ax.axis("off");fig.colorbar(im,ax=ax,shrink=.6)
        fig.suptitle(f"{sid}: primary Tangram normalized composition weights")
        fig.tight_layout();fig.savefig(S4/f"{sid}-composition.png",dpi=180);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(13,5))
    axs[0].scatter(sens.actual_training_genes,sens.mean_celltype_spearman_vs_primary,c=sens.seed,s=30);axs[0].set(xlabel="actual training genes",ylabel="mean cell-type Spearman vs primary",title="Tangram parameter sensitivity")
    merged=tgcomp.merge(nncomp,on=["section","barcode"],suffixes=("_tg","_nn")); labs=[c for c in tgcomp.columns if c not in {"section","barcode"}]
    axs[1].scatter(np.concatenate([merged[f"{c}_tg"] for c in labs]),np.concatenate([merged[f"{c}_nn"] for c in labs]),s=1,alpha=.15);axs[1].set(xlabel="Tangram normalized weight",ylabel="NNLS normalized weight",title="Shared-reference method sensitivity")
    fig.tight_layout();fig.savefig(S4/"method-comparison.png",dpi=180);plt.close(fig)
    fig,axs=plt.subplots(2,3,figsize=(15,9))
    for ax,sid in zip(axs.ravel(),SECTIONS):
        q=ingest[ingest.section==sid].set_index("barcode"); c=section_coords(sid).loc[q.index]; cats=sorted(q.transferred_label.unique()); codes=pd.Categorical(q.transferred_label,categories=cats).codes
        ax.scatter(c.px_col,c.px_row,c=codes,s=6,cmap="tab20",rasterized=True);ax.invert_yaxis();ax.axis("off");ax.set_title(sid)
    fig.suptitle("Scanpy ingest transferred similarity labels (categorical)");fig.tight_layout();fig.savefig(S4/"ingest_maps.png",dpi=180);plt.close(fig)


def concordance(tgcomp: pd.DataFrame, nncomp: pd.DataFrame, resid: pd.DataFrame, unknown: pd.DataFrame, ingest: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    labs=[c for c in tgcomp.columns if c not in {"section","barcode"}]
    merged=tgcomp.merge(nncomp,on=["section","barcode"],suffixes=("_tangram","_nnls")); rows=[]
    for sid,g in merged.groupby("section"):
        for lab in labs:
            r=spearmanr(g[f"{lab}_tangram"],g[f"{lab}_nnls"]).statistic
            rows.append({"section":sid,"producer_celltype_minor":lab,"spearman":r if np.isfinite(r) else np.nan,
                         "mean_absolute_difference":np.mean(np.abs(g[f"{lab}_tangram"]-g[f"{lab}_nnls"])),
                         "spots":len(g),"nnls_mean_residual":resid[resid.section==sid].residual_l2.mean(),
                         "nnls_unknown_spots":int((unknown.section==sid).sum()) if len(unknown) else 0})
        rows.append({"section":sid,"producer_celltype_minor":"__DOMINANT_COMPONENT_AGREEMENT__","spearman":np.nan,
                     "mean_absolute_difference":np.nan,"spots":len(g),"dominant_component_agreement":np.mean(g[[f"{x}_tangram" for x in labs]].idxmax(axis=1).str.removesuffix("_tangram").to_numpy()==g[[f"{x}_nnls" for x in labs]].idxmax(axis=1).str.removesuffix("_nnls").to_numpy()),
                     "nnls_mean_residual":resid[resid.section==sid].residual_l2.mean(),"nnls_unknown_spots":int((unknown.section==sid).sum()) if len(unknown) else 0})
    out=pd.DataFrame(rows);out.to_csv(S4/"tangram-nnls-concordance.csv",index=False)
    prim=tgcomp.copy(); prim["tangram_dominant"]=prim[labs].idxmax(axis=1); ia=ingest.merge(prim[["section","barcode","tangram_dominant"]],on=["section","barcode"]); ia["agreement"]=ia.transferred_label==ia.tangram_dominant
    ag=ia.groupby(["section","transferred_label","tangram_dominant"],dropna=False).size().rename("spots").reset_index(); ag.to_csv(S4/"ingest-label-agreement.csv",index=False)
    return out,ag


def adjacency(coords: pd.DataFrame) -> sparse.csr_matrix:
    xy=coords[["px_col","px_row"]].to_numpy(float);tree=cKDTree(xy);nearest=tree.query(xy,k=2)[0][:,1];d=float(np.median(nearest[(nearest>0)&np.isfinite(nearest)]));pairs=np.asarray(list(tree.query_pairs(1.2*d)),dtype=int)
    if not len(pairs): return sparse.csr_matrix((len(xy),len(xy)))
    dd=np.linalg.norm(xy[pairs[:,0]]-xy[pairs[:,1]],axis=1);pairs=pairs[(dd>=.8*d)&(dd<=1.2*d)];rr=np.r_[pairs[:,0],pairs[:,1]];cc=np.r_[pairs[:,1],pairs[:,0]]
    return sparse.csr_matrix((np.ones(len(rr)),(rr,cc)),shape=(len(xy),len(xy)))


def moran(x: np.ndarray,w:sparse.csr_matrix,seed:int=PRIMARY_SEED,permutations:int=999)->dict[str,Any]:
    z=np.asarray(x,float);z-=z.mean();den=float(z@z);s0=float(w.sum())
    if den==0 or s0==0:return {"I":None,"p_two_sided":None,"reason":"constant_or_no_edges"}
    obs=float(len(z)/s0*(z@(w@z))/den);rng=np.random.default_rng(seed);extreme=0
    for _ in range(permutations):
        zp=rng.permutation(z);ip=float(len(z)/s0*(zp@(w@zp))/den);extreme+=abs(ip)>=abs(obs)
    return {"I":obs,"p_two_sided":(extreme+1)/(permutations+1),"permutations":permutations,"descriptive":True}


def run_s5(tgcomp: pd.DataFrame, marker_union: list[str], labels: list[str]) -> dict[str, Any]:
    s5start=time.perf_counter();progress(S5,"RUNNING","S5_KMEANS_GRID",4)
    x=tgcomp[labels].to_numpy(float); sections=tgcomp.section.to_numpy(); scaler=StandardScaler().fit(x,sample_weight=np.asarray([1/np.sum(sections==s) for s in sections])); z=scaler.transform(x)
    atomic_json(S5/"scaler.json",{"feature_order":labels,"mean":scaler.mean_,"scale":scaler.scale_,"fit_sections":SECTIONS,"section_total_weight_equal":True,"held_out_10x_used_for_fit":False})
    summaries=[];silrows=[];alllabs=[];models={}
    weights=np.asarray([1/np.sum(sections==s) for s in sections])
    for k in range(6,11):
        for seed in SEEDS:
            km=KMeans(n_clusters=k,random_state=seed,n_init=20).fit(z,sample_weight=weights);pred=km.labels_;models[(k,seed)]=km
            summaries.append({"k":k,"seed":seed,"inertia":km.inertia_,"iterations":km.n_iter_,"spots":len(pred),"section_total_weight_equal":True})
            for sid in SECTIONS:
                take=sections==sid; score=silhouette_score(z[take],pred[take]) if len(set(pred[take]))>1 else np.nan
                silrows.append({"k":k,"seed":seed,"section":sid,"silhouette":score,"spots":int(take.sum())})
            alllabs.extend({"section":s,"barcode":b,"k":k,"seed":seed,"niche":f"N{v}"} for s,b,v in zip(tgcomp.section,tgcomp.barcode,pred))
    pd.DataFrame(summaries).to_csv(S5/"kmeans-grid.csv",index=False);pd.DataFrame(silrows).to_csv(S5/"silhouette-by-section.csv",index=False);pd.DataFrame(alllabs).to_csv(S5/"kmeans-grid-labels.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    means=pd.DataFrame(silrows).groupby("k").silhouette.mean();best=float(means.max()); selected_k=int(min(means.index[np.isclose(means,best,rtol=1e-12,atol=1e-12)]));selected_seed=PRIMARY_SEED;km=models[(selected_k,selected_seed)];pred=km.labels_
    atomic_json(S5/"selected-k.json",{"selected_k":selected_k,"display_seed":selected_seed,"criterion":"maximum unweighted mean of six section silhouettes, averaged across three preregistered seeds; ties choose smaller k","selected_before_boundary_enrichment":True,"mean_silhouette_by_k":means.to_dict()})
    pd.DataFrame(km.cluster_centers_,columns=labels,index=[f"N{i}" for i in range(selected_k)]).rename_axis("niche").to_csv(S5/"kmeans-centers.csv")
    niche=tgcomp[["section","barcode"]].copy();niche["niche"]=[f"N{i}" for i in pred];niche.to_csv(S5/"niche_labels.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    cent=tgcomp.assign(niche=niche.niche).groupby("niche")[labels].mean();cent.to_csv(S5/"niche-composition-centroids.csv")
    mapping={"CAF":["CAFs MSC iCAF-like","CAFs myCAF-like"],"CD8_T":["T cells CD8+"],"macrophage":["Macrophage"],"endothelial":["Endothelial ACKR1","Endothelial CXCL12","Endothelial Lymphatic LYVE1","Endothelial RGS5"]}
    atomic_json(S5/"prespecified-four-component-map.json",{"mapping":mapping,"excluded_similar_labels":["Cycling T-cells","Monocyte"],"forced_target_niche":False})
    four=pd.DataFrame(index=cent.index)
    for name,members in mapping.items(): four[name]=cent[members].sum(axis=1)
    four.to_csv(S5/"prespecified-four-components-by-niche.csv")
    enrich=[];cooccur=[];morans=[];dist=[]
    for sid in SECTIONS:
        sub=niche[niche.section==sid].set_index("barcode"); coords=section_coords(sid).loc[sub.index];w=adjacency(coords); lab=sub.niche.to_numpy();cats=sorted(set(lab)); counts=pd.Series(lab).value_counts()
        for c in cats:dist.append({"section":sid,"niche":c,"spots":int(counts[c]),"proportion":float(counts[c]/len(lab))})
        ri,ci=w.nonzero(); keep=ri<ci; ri=ri[keep];ci=ci[keep]; total_edges=len(ri)
        for a in cats:
            for b in cats:
                obs=int(np.sum(((lab[ri]==a)&(lab[ci]==b))|((lab[ri]==b)&(lab[ci]==a)))) if a!=b else int(np.sum((lab[ri]==a)&(lab[ci]==a)))
                pa=np.mean(lab==a);pb=np.mean(lab==b);expected=total_edges*(2*pa*pb if a!=b else pa*pa)
                ratio=obs/expected if expected>0 else np.nan
                enrich.append({"section":sid,"niche_a":a,"niche_b":b,"observed_edges":obs,"expected_edges_independence":expected,"enrichment_ratio":ratio,"descriptive":True})
                cooccur.append({"section":sid,"niche_a":a,"niche_b":b,"co_occurrence_ratio":ratio,"graph_steps":"first-ring","descriptive":True})
            m=moran((lab==a).astype(float),w);morans.append({"section":sid,"niche":a,**m})
        c=coords.copy();c["niche"]=lab;codes=pd.Categorical(c.niche,categories=cats).codes;fig,ax=plt.subplots(figsize=(6,6));ax.scatter(c.px_col,c.px_row,c=codes,s=8,cmap="tab10",rasterized=True);ax.invert_yaxis();ax.axis("off");ax.set_title(f"{sid} niches, k={selected_k}");fig.tight_layout();fig.savefig(S5/f"{sid}-niche-map.png",dpi=180);plt.close(fig)
    pd.DataFrame(enrich).to_csv(S5/"neighborhood-enrichment.csv",index=False);pd.DataFrame(cooccur).to_csv(S5/"co-occurrence.csv",index=False);pd.DataFrame(morans).to_csv(S5/"niche-Moran.csv",index=False);pd.DataFrame(dist).to_csv(S5/"niche-distribution-by-section.csv",index=False)
    boundary=[]
    for sid in SECTIONS:
        if sid!="CID4535":
            boundary.append({"section":sid,"niche":"ALL","status":"NOT_COMPUTED_WITH_REASON","reason":"S3 frozen pathology meaning/geometry does not support a boundary/core mask for this section"});continue
        masks=pd.read_csv(S3/sid/"geometry-boundary-core-masks.csv").set_index("barcode"); sub=niche[niche.section==sid].set_index("barcode");masks=masks.loc[sub.index]
        B=masks.boundary_invasive_d2.astype(bool).to_numpy();C=masks.core_invasive_d_gt_3.astype(bool).to_numpy();lab=sub.niche.to_numpy()
        for c in sorted(set(lab)):
            bn=int(np.sum(B&(lab==c)));cn=int(np.sum(C&(lab==c)));bp=bn/B.sum();cp=cn/C.sum()
            boundary.append({"section":sid,"niche":c,"status":"COMPUTED_DESCRIPTIVE","boundary_B2_spots":bn,"core_D_gt_3_spots":cn,"boundary_proportion":bp,"core_proportion":cp,"proportion_difference":bp-cp,"enrichment_fold":bp/cp if cp>0 else np.nan,"single_section_no_patient_inference":True})
    ben=pd.DataFrame(boundary);ben.to_csv(S5/"boundary-niche-enrichment.csv",index=False)
    fig,axs=plt.subplots(1,2,figsize=(12,5));im=axs[0].imshow(four.to_numpy(),aspect="auto",cmap="viridis");axs[0].set_xticks(range(4),four.columns,rotation=45,ha="right");axs[0].set_yticks(range(len(four)),four.index);axs[0].set_title("Prespecified four components");fig.colorbar(im,ax=axs[0]);pivot=pd.DataFrame(dist).pivot(index="niche",columns="section",values="proportion").fillna(0);im2=axs[1].imshow(pivot.to_numpy(),aspect="auto",cmap="magma");axs[1].set_xticks(range(len(pivot.columns)),pivot.columns,rotation=45,ha="right");axs[1].set_yticks(range(len(pivot)),pivot.index);axs[1].set_title("Niche proportions by section");fig.colorbar(im2,ax=axs[1]);fig.tight_layout();fig.savefig(S5/"enrichment-heatmap.png",dpi=180);plt.close(fig)
    progress(S5,"RUNNING","S5_10X_TECHNICAL_TRANSFER",82)
    transfer=run_10x_transfer(marker_union,labels,scaler,km,selected_k)
    return {"selected_k":selected_k,"selected_seed":selected_seed,"niches":selected_k,"grid_combinations":15,"boundary_sections_computed":1,"boundary_sections_not_computed":5,"technical_transfer":transfer,"elapsed_seconds":time.perf_counter()-s5start}


def run_10x_transfer(marker_union:list[str],labels:list[str],scaler:StandardScaler,km:KMeans,selected_k:int)->dict[str,Any]:
    import tangram as tg
    import tangram.mapping_utils as mu
    original_mapper=mu.mo.Mapper
    def compatible_mapper(*a,**kw):kw["d"]=np.asarray(kw["d"],dtype=np.float32);return original_mapper(*a,**kw)
    mu.mo.Mapper=compatible_mapper
    h5=TENX/"V1_Breast_Cancer_Block_A_Section_1_filtered_feature_bc_matrix.h5"; sp=sc.read_10x_h5(h5,gex_only=True);sp.var_names_make_unique()
    pos=pd.read_csv(TENX/"V1_Breast_Cancer_Block_A_Section_1_spatial-extracted/spatial/tissue_positions_list.csv",header=None,names=["barcode","in_tissue","array_row","array_col","px_row","px_col"]).set_index("barcode")
    common=sp.obs_names.intersection(pos.index);sp=sp[common].copy();pos=pos.loc[common];keep=pos.in_tissue.astype(int).to_numpy()==1;sp=sp[keep].copy();pos=pos.iloc[np.flatnonzero(keep)]
    ref=sc.read_h5ad(REF_PATH); genes=[g for g in marker_union if g in set(sp.var_names)][:PRIMARY_GENE_COUNT]
    t0=time.perf_counter();r=ref[:,genes].copy();q=sp[:,genes].copy();tg.pp_adatas(r,q,genes=genes,gene_to_lowercase=False);m=tg.map_cells_to_space(r,q,mode="clusters",cluster_label="producer_celltype_minor",device="cpu",num_epochs=EPOCHS,random_state=PRIMARY_SEED,verbose=False);tg.project_cell_annotations(m,q,annotation="producer_celltype_minor")
    comp=q.obsm["tangram_ct_pred"].reindex(columns=labels,fill_value=0.0);sums=comp.sum(axis=1).to_numpy();comp.loc[sums>0,:]=comp.loc[sums>0,:].div(sums[sums>0],axis=0);missing=[c for c in labels if c not in q.obsm["tangram_ct_pred"].columns]
    comp_out=comp.copy();comp_out.insert(0,"barcode",sp.obs_names.astype(str));comp_out.to_csv(S5/"10x-transfer-composition.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    pred=km.predict(scaler.transform(comp.to_numpy()));out=pd.DataFrame({"barcode":sp.obs_names.astype(str),"assigned_niche":[f"N{i}" for i in pred]});out.to_csv(S5/"10x-transfer-labels.csv.gz",index=False,compression={"method":"gzip","mtime":0})
    atomic_json(S5/"10x-transfer-feature-overlap.json",{"status":"COMPLETED_TECHNICAL_TRANSFER","input":str(h5),"input_sha256":sha(h5),"in_tissue_spots":sp.n_obs,"reference_labels":labels,"missing_components":missing,"requested_training_genes":PRIMARY_GENE_COUNT,"actual_training_genes":len(genes),"training_genes":genes,"seed":PRIMARY_SEED,"epochs":EPOCHS,"elapsed_seconds":time.perf_counter()-t0,"training_history":m.uns.get("training_history",{}),"scaler_refit_on_10x":False,"kmeans_refit_on_10x":False,"interpretation":"technical transfer/compatibility only; no pathology truth, biological replication, or independent validation"})
    fig,ax=plt.subplots(figsize=(7,7));cats=sorted(out.assigned_niche.unique());codes=pd.Categorical(out.assigned_niche,categories=cats).codes;ax.scatter(pos.px_col,pos.px_row,c=codes,s=7,cmap="tab10",rasterized=True);ax.invert_yaxis();ax.axis("off");ax.set_title(f"10x technical transfer niches, frozen k={selected_k}");fig.tight_layout();fig.savefig(S5/"10x-transfer-map.png",dpi=180);plt.close(fig)
    return {"status":"COMPLETED_TECHNICAL_TRANSFER","spots":sp.n_obs,"genes":sp.n_vars,"actual_training_genes":len(genes),"missing_components":missing,"scaler_refit":False,"kmeans_refit":False}


def provenance(out:pathlib.Path,stage:str,inputs:list[pathlib.Path],params:dict[str,Any])->None:
    sys.path.insert(0,r"C:\Plugin\BioNexus\src")
    try:
        import bionexus
        from bionexus.provenance import sidecar
        outputs=[p for p in out.rglob("*") if p.is_file() and p.name not in {"stdout.log","stderr.log","progress.json","SHA256SUMS.txt","output-manifest.json","provenance.sidecar.json"}]
        rec=sidecar(activity_name=f"SpatialWarrant {stage} technical execution",input_files=inputs,output_files=outputs,parameters=params,method="locked-plan local sparse spatial analysis",backend="local Python/scverse execution")
        rec.update({"bionexus_runtime_version":getattr(bionexus,"__version__","UNKNOWN"),"scope_boundary":"technical provenance only; no scientific Warrant or biological conclusion","machine_verdict":"PENDING","biological_conclusion":"PENDING"})
    except Exception as e:
        rec={"status":"PROVENANCE_LIBRARY_CALL_FAILED","error_type":type(e).__name__,"error":str(e),"technical_inputs_and_hashes_retained":True,"machine_verdict":"PENDING","biological_conclusion":"PENDING"}
    atomic_json(out/"provenance.sidecar.json",rec)


def finalize(out:pathlib.Path,stage:str,result:dict[str,Any])->None:
    excluded={"stdout.log","stderr.log","SHA256SUMS.txt","output-manifest.json"}
    files=sorted(p for p in out.rglob("*") if p.is_file() and p.name not in excluded)
    atomic_json(out/"output-manifest.json",{"stage":stage,"status":result.get("status"),"created_at_utc":now(),"files_before_manifest":[{"file":str(p.relative_to(out)),"bytes":p.stat().st_size,"sha256":sha(p)} for p in files],"runtime_logs_excluded_from_stage_checksum":["stdout.log","stderr.log"],"machine_verdict":"PENDING","biological_conclusion":"PENDING"})
    files=sorted(p for p in out.rglob("*") if p.is_file() and p.name not in {"stdout.log","stderr.log","SHA256SUMS.txt"})
    write_text(out/"SHA256SUMS.txt","".join(f"{sha(p)}  {p.relative_to(out)}\n" for p in files))


def checkpoint(s4res:dict[str,Any],s5res:dict[str,Any])->None:
    p=ROOT/"S4-S5-checkpoint.md"
    if p.exists(): raise RuntimeError("ROOT_CHECKPOINT_COLLISION")
    boundary=pd.read_csv(S5/"boundary-niche-enrichment.csv");cid=boundary[boundary.section=="CID4535"]
    dist=pd.read_csv(S5/"niche-distribution-by-section.csv")
    text=f"""# SpatialWarrant S4-S5 checkpoint\n\n- Status: COMPLETED\n- Route: local Python/scverse execution; registered NGS workflow run: NONE\n- Locked plan SHA-256: `{PLAN_SHA}`\n- S4 output: `{S4}`\n- S5 output: `{S5}`\n- Tangram: cluster mode CPU, {EPOCHS} epochs, requested genes {TRAIN_GENE_COUNTS}, seeds {SEEDS}; completed {s4res['tangram_completed_combinations']}/54 combinations; failed {s4res['tangram_failed_combinations']}.\n- Main Tangram: requested {PRIMARY_GENE_COUNT} genes, seed {PRIMARY_SEED}; normalized composition weights are method estimates, not calibrated cell fractions.\n- Marker/NNLS and Scanpy ingest: completed. Ingest is categorical similarity-label transfer only.\n- Method comparison: descriptive sensitivity using the shared Wu reference; it is not independent validation.\n- S5 KMeans: all 15 k/seed combinations completed; selected k={s5res['selected_k']} using the unweighted six-section mean silhouette before boundary analysis, display seed {PRIMARY_SEED}.\n- Niche distributions: `{S5/'niche-distribution-by-section.csv'}` ({len(dist)} section-niche rows).\n- Frozen boundary: CID4535 B2 versus core was evaluated descriptively ({len(cid)} niche rows). The other five sections are NOT_COMPUTED_WITH_REASON. No boundary was redefined.\n- 10x Block A Section 1: {s5res['technical_transfer']['status']}; frozen scaler and KMeans were applied without refitting. This is technical transfer/compatibility only.\n- S4 elapsed seconds: {s4res['elapsed_seconds']:.3f}; S5 elapsed seconds: {s5res['elapsed_seconds']:.3f}.\n- Peak process-tree memory bytes (observed): {s4res['peak_process_tree_memory_bytes']}.\n- Start/end C free bytes: {s4res['start_free_C_bytes']} / {s5res['end_free_C_bytes']}.\n- S4/S5 output bytes: {dir_size(S4)} / {dir_size(S5)}.\n- Patient-level inference: BLOCKED / NOT_ESTABLISHED.\n- Machine verdict: PENDING.\n- Biological conclusion: PENDING.\n- Next stage: S6 was not started.\n"""
    with p.open("x",encoding="utf-8") as f:f.write(text);f.flush();os.fsync(f.fileno())


def main()->None:
    peak_tree=0
    try:
        pf=preflight();atomic_json(S4/"preflight.json",pf);atomic_json(S5/"preflight.json",pf)
        common_inputs=[PLAN,GUIDE,REF_PATH,ANNOTATION_EVIDENCE,ROOT/"03_scrna_reference/S2-run-01/SHA256SUMS.txt",S3/"SHA256SUMS.txt"]+[S3/s/f"{s}.h5ad" for s in SECTIONS]+[S3/s/"spot-QC-and-metadata.csv.gz" for s in SECTIONS]+[S3/s/"geometry-boundary-core-masks.csv" for s in SECTIONS]
        tenx_inputs=[p for p in TENX.rglob("*") if p.is_file()]
        atomic_json(S4/"input-manifest.json",{"files":[{"path":str(p),"bytes":p.stat().st_size,"sha256":sha(p)} for p in common_inputs],"route":"local Python/scverse execution","registered_NGS_workflow_run":"NONE"})
        atomic_json(S5/"input-manifest.json",{"files":[{"path":str(p),"bytes":p.stat().st_size,"sha256":sha(p)} for p in common_inputs+tenx_inputs],"route":"local Python/scverse execution","registered_NGS_workflow_run":"NONE"})
        env={"python":sys.version,"executable":sys.executable,"platform":platform.platform(),"route":"local Python/scverse execution","registered_NGS_workflow_run":"NONE","dependencies":{n:__import__(n).__version__ for n in ["numpy","scipy","pandas","anndata","scanpy","sklearn","matplotlib","psutil"]}}
        import torch,tangram
        env["dependencies"].update({"torch":torch.__version__,"tangram":tangram.__version__});env["device"]="CPU";env["tangram_install_command"]="project-local venv: python -m pip install --no-cache-dir tangram-sc==1.0.4 scanpy==1.12.2 psutil==7.0.0"
        atomic_json(S4/"execution-environment.json",env);atomic_json(S5/"execution-environment.json",env)
        ref=sc.read_h5ad(REF_PATH)
        if ref.n_obs!=40000 or "producer_celltype_minor" not in ref.obs:raise RuntimeError("REFERENCE_CONTRACT")
        labels=sorted(ref.obs.producer_celltype_minor.astype(str).unique())
        progress(S4,"RUNNING","S4_REFERENCE_MARKERS",3)
        marker_union,_=marker_genes(ref)
        atomic_json(S4/"S4-config.json",{"Tangram":{"mode":"clusters","device":"cpu","cluster_label":"producer_celltype_minor","epochs":EPOCHS,"requested_training_genes":TRAIN_GENE_COUNTS,"seeds":SEEDS,"primary":{"requested_training_genes":PRIMARY_GENE_COUNT,"seed":PRIMARY_SEED},"maximum_parallel_sections":2},"marker_selection":"top 50 mean-log1p-difference markers per producer label; deterministic frequency/rank/score/symbol union; section feature intersection; no padding","NNLS":{"solver":"scipy.optimize.nnls","calibrated_proportion":False},"ingest":{"output":"transferred similarity label and ambiguity only","proportions":False},"patient_level_inference":"NOT_ESTABLISHED"})
        progress(S4,"RUNNING","S4_TANGRAM_GRID",6,total_combinations=54)
        worker_results=[]
        with ProcessPoolExecutor(max_workers=2) as pool:
            futures={pool.submit(tangram_worker,(sid,marker_union)):sid for sid in SECTIONS}
            for n,fut in enumerate(as_completed(futures),1):
                result=fut.result();worker_results.append(result);peak_tree=max(peak_tree,result["peak_memory_bytes"]);progress(S4,"RUNNING","S4_TANGRAM_GRID",6+54*n/len(SECTIONS),completed_sections=n,total_sections=6)
        tgcomp,sens,failures=collect_tangram()
        completed=int(sum(r["status"]=="COMPLETED" for w in worker_results for r in w["runs"]))
        nncomp,resid,unknown=run_nnls(ref,marker_union)
        ingest,conf=run_ingest(ref)
        conc,ingagree=concordance(tgcomp,nncomp,resid,unknown,ingest);plot_s4(tgcomp,nncomp,ingest,sens)
        s4res={"status":"COMPLETED","started_at_utc":STARTED_UTC,"ended_at_utc":now(),"sections":6,"producer_labels":len(labels),"tangram_grid_combinations":54,"tangram_completed_combinations":completed,"tangram_failed_combinations":len(failures),"failed_combinations":failures,"primary_requested_training_genes":PRIMARY_GENE_COUNT,"primary_seed":PRIMARY_SEED,"NNLS_unknown_spots":len(unknown),"ingest_output":"categorical transferred similarity labels only","method_interpretation":"shared-reference method sensitivity; no independent validation or calibrated cell fractions","elapsed_seconds":time.perf_counter()-STARTED_PERF,"peak_process_tree_memory_bytes":max(peak_tree,PROC.memory_info().rss),"start_free_C_bytes":pf["free_C_bytes"],"patient_level_inference":"NOT_ESTABLISHED","machine_verdict":"PENDING","biological_conclusion":"PENDING"}
        atomic_json(S4/"S4-result.json",s4res);provenance(S4,"S4",[PLAN,GUIDE,REF_PATH,ANNOTATION_EVIDENCE]+[S3/s/f"{s}.h5ad" for s in SECTIONS],{"Tangram_grid":54,"epochs":EPOCHS,"seeds":SEEDS,"route":"local Python/scverse execution","registered_NGS_workflow_run":"NONE"});progress(S4,"COMPLETED","S4_COMPLETE",100);finalize(S4,"S4",s4res)
        progress(S5,"RUNNING","S5_START",1)
        s5res=run_s5(tgcomp,marker_union,labels);s5res.update({"status":"COMPLETED","started_at_utc":now(),"ended_at_utc":now(),"end_free_C_bytes":shutil.disk_usage("C:\\").free,"output_bytes_before_manifest":dir_size(S5),"patient_level_inference":"NOT_ESTABLISHED","machine_verdict":"PENDING","biological_conclusion":"PENDING","S6_started":False})
        atomic_json(S5/"S5-result.json",s5res);provenance(S5,"S5",[PLAN,S4/"proportions_tangram.csv.gz",S3/"CID4535/geometry-boundary-core-masks.csv",TENX/"V1_Breast_Cancer_Block_A_Section_1_filtered_feature_bc_matrix.h5"],{"k_values":[6,7,8,9,10],"seeds":SEEDS,"technical_transfer_only":True,"boundary_redefined":False});progress(S5,"COMPLETED","S5_COMPLETE",100);finalize(S5,"S5",s5res)
        checkpoint(s4res,s5res)
    except Exception as e:
        failure={"status":"FAILED","at_utc":now(),"error_type":type(e).__name__,"error":str(e),"traceback":traceback.format_exc(),"S6_started":False,"machine_verdict":"PENDING","biological_conclusion":"PENDING"}
        target=S5 if (S5/"progress.json").exists() else S4
        try:atomic_json(target/"failure.json",failure);progress(target,"FAILED","FAILED",100,error_type=type(e).__name__,error=str(e))
        finally:raise


if __name__=="__main__":main()
