from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import anndata as ad
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import psutil
import scanpy as sc
from scipy import sparse


PLAN_SHA256 = "854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82"
DISPLAY_GENES = ["CXCL9", "CXCL10", "CXCL11", "IDO1", "STAT1", "IRF1"]
LOW_DISK_STOP = 20 * 1024**3


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def native(v):
    if isinstance(v, dict):
        return {str(k): native(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [native(x) for x in v]
    if isinstance(v, np.ndarray):
        return [native(x) for x in v.tolist()]
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return float(v) if math.isfinite(float(v)) else None
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if pd.isna(v):
        return None
    return v


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(native(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def disk_guard(stage: str) -> int:
    free = shutil.disk_usage("C:\\").free
    if free < LOW_DISK_STOP:
        raise RuntimeError(f"DISK_STOP at {stage}: free_C_bytes={free} < {LOW_DISK_STOP}")
    return free


def peak_memory() -> int:
    mi = psutil.Process().memory_info()
    return int(getattr(mi, "peak_wset", mi.rss))


def parse_sha_manifest(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and len(parts[0]) == 64:
            rows.append((parts[0].lower(), parts[1].lstrip("* ").replace("/", os.sep)))
    return rows


def verify_manifest(root: Path, manifest_name: str = "SHA256SUMS.txt") -> dict:
    m = root / manifest_name
    if not m.exists():
        return {"status": "MISSING_MANIFEST", "manifest": str(m), "checked": 0, "mismatches": []}
    bad = []
    checked = 0
    for expected, rel in parse_sha_manifest(m):
        f = root / rel
        if f.resolve() == m.resolve():
            continue
        if not f.exists():
            bad.append({"path": str(f), "reason": "missing"})
            continue
        observed = sha256_file(f)
        checked += 1
        if observed != expected:
            bad.append({"path": str(f), "expected": expected, "observed": observed})
    return {"status": "PASS" if not bad else "FAIL", "manifest": str(m), "checked": checked, "mismatches": bad}


def gmt_sets(path: Path) -> dict[str, list[str]]:
    sets = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        x = line.rstrip("\n").split("\t")
        if len(x) >= 3:
            sets[x[0]] = x[2:]
    return sets


def sum_region(X, mask: np.ndarray) -> np.ndarray:
    z = X[mask, :]
    if not sparse.issparse(z):
        raise RuntimeError("Visium count matrix is not sparse")
    data = z.data
    if not np.all(np.isfinite(data)) or np.any(data < 0) or np.any(data != np.floor(data)):
        raise RuntimeError("Visium raw count integrity failure")
    return np.asarray(z.sum(axis=0)).ravel().astype(np.int64)


def write_sha_manifest(root: Path, target: Path) -> None:
    rows = []
    for f in sorted(root.rglob("*"), key=lambda p: str(p).lower()):
        if f.is_file() and f.resolve() != target.resolve() and not f.name.endswith(".tmp"):
            rows.append(f"{sha256_file(f)}  {f.relative_to(root).as_posix()}")
    target.write_text("\n".join(rows) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    args = ap.parse_args()
    root = Path(args.project)
    out_pb = root / "08_pseudobulk" / "S6-run-01"
    out_lr = root / "09_liana_literature" / "S6-run-01"
    started = time.perf_counter()
    started_utc = utcnow()
    start_free = disk_guard("start")
    progress = out_lr / "progress.json"

    def update(stage, percent, status="RUNNING", **extra):
        write_json(progress, {"status": status, "stage": stage, "percent": percent, "elapsed_seconds": time.perf_counter()-started,
                             "current_memory_bytes": psutil.Process().memory_info().rss, "peak_memory_bytes": peak_memory(),
                             "free_C_bytes": shutil.disk_usage("C:\\").free, "updated_at_utc": utcnow(), **extra})

    try:
        update("preflight", 2)
        plan = root / "00_plan" / "analysis-plan.lock.md"
        if sha256_file(plan) != PLAN_SHA256:
            raise RuntimeError("Locked plan SHA-256 mismatch")
        s2_claimed = root / "02_reference" / "S2-run-01"
        s2 = root / "03_scrna_reference" / "S2-run-01"
        s3 = root / "04_visium_qc" / "S3-run-03"
        s4 = root / "06_deconvolution" / "S4-run-02"
        s5 = root / "07_niches" / "S5-run-02"
        checkpoint = root / "S4-S5-checkpoint.md"
        for p in [s2, s3, s4, s5, checkpoint]:
            if not p.exists():
                raise RuntimeError(f"Required input missing: {p}")
        input_verification = {
            "status": "PASS",
            "locked_plan_sha256": sha256_file(plan),
            "locked_plan_expected_sha256": PLAN_SHA256,
            "user_stated_s2_path": str(s2_claimed),
            "user_stated_s2_path_exists": s2_claimed.exists(),
            "resolved_formal_s2_path": str(s2),
            "resolution_basis": "Formal S2 path used by S4/S5 and prior checkpoint; no alternative S2 was created.",
            "S2": verify_manifest(s2), "S3": verify_manifest(s3), "S4": verify_manifest(s4), "S5": verify_manifest(s5),
            "S4_S5_checkpoint_sha256": sha256_file(checkpoint), "start_free_C_bytes": start_free,
            "disk_stop_threshold_bytes": LOW_DISK_STOP, "checked_at_utc": utcnow()
        }
        if any(input_verification[k]["status"] == "FAIL" for k in ["S2", "S3", "S4", "S5"]):
            raise RuntimeError("Input SHA manifest verification failed")
        write_json(out_pb / "input-verification.json", input_verification)
        write_json(out_lr / "input-verification.json", input_verification)

        update("primary_program_and_pseudobulk", 8)
        adata = ad.read_h5ad(s3 / "CID4535" / "CID4535.h5ad")
        if not sparse.issparse(adata.X):
            raise RuntimeError("CID4535 raw count matrix is not sparse")
        mask_df = pd.read_csv(s3 / "CID4535" / "geometry-boundary-core-masks.csv")
        if mask_df["barcode"].duplicated().any() or adata.obs_names.duplicated().any():
            raise RuntimeError("Duplicate barcode in CID4535 or masks")
        mask_df = mask_df.set_index("barcode").reindex(adata.obs_names)
        if mask_df.index.isna().any() or mask_df[["boundary_invasive_d1","boundary_invasive_d2","boundary_invasive_d3","core_invasive_d_gt_3"]].isna().any().any():
            raise RuntimeError("CID4535 mask-to-count barcode join failed")
        regions = {
            "B1_boundary_D_le_1": mask_df["boundary_invasive_d1"].astype(bool).to_numpy(),
            "B2_boundary_D_le_2": mask_df["boundary_invasive_d2"].astype(bool).to_numpy(),
            "B3_boundary_D_le_3": mask_df["boundary_invasive_d3"].astype(bool).to_numpy(),
            "core_D_gt_3": mask_df["core_invasive_d_gt_3"].astype(bool).to_numpy(),
        }
        counts = {name: sum_region(adata.X, mask) for name, mask in regions.items()}
        totals = {name: int(x.sum()) for name, x in counts.items()}
        spots = {name: int(mask.sum()) for name, mask in regions.items()}
        for name in regions:
            if spots[name] < 20 or totals[name] < 100000:
                raise RuntimeError(f"Eligibility failure for {name}: spots={spots[name]}, UMI={totals[name]}")
        genes = pd.Index(adata.var_names.astype(str))
        if genes.duplicated().any():
            raise RuntimeError("Duplicate CID4535 feature symbols")
        gmt = root / "01_inputs" / "resources" / "h.all.v2024.1.Hs.symbols.gmt"
        sets = gmt_sets(gmt)
        primary_name = "HALLMARK_INTERFERON_GAMMA_RESPONSE"
        full_primary = sets[primary_name]
        matched = [g for g in full_primary if g in genes]
        missing = [g for g in full_primary if g not in genes]
        if len(full_primary) != 200 or len(matched) / len(full_primary) < 0.90:
            raise RuntimeError("Primary program membership or >=90% coverage gate failed")
        gidx = genes.get_indexer(matched)
        cpm = {name: x.astype(float) / totals[name] * 1e6 for name, x in counts.items()}
        logcpm = {name: np.log2(v + 1.0) for name, v in cpm.items()}
        score = {name: float(logcpm[name][gidx].mean()) for name in regions}
        deltas = {
            "B1_boundary_minus_core": score["B1_boundary_D_le_1"] - score["core_D_gt_3"],
            "B2_boundary_minus_core_primary": score["B2_boundary_D_le_2"] - score["core_D_gt_3"],
            "B3_boundary_minus_core": score["B3_boundary_D_le_3"] - score["core_D_gt_3"],
        }
        coverage = {"program": primary_name, "systematic_id": "M5913", "release": "2024.1.Hs", "gmt_sha256": sha256_file(gmt),
                    "full_gene_count": len(full_primary), "matched_gene_count": len(matched), "coverage_fraction": len(matched)/len(full_primary),
                    "matched_genes": matched, "missing_genes": missing, "alias_substitution": "NONE",
                    "score_denominator": "matched identifiable genes only", "score_formula": "mean_gene(log2(1 + 1e6 * region raw gene count / region total raw UMI))"}
        write_json(out_pb / "primary-program-gene-coverage.json", coverage)
        pd.DataFrame({"gene": matched}).to_csv(out_pb / "primary-program-matched-genes.csv", index=False)
        pd.DataFrame({"gene": missing}).to_csv(out_pb / "primary-program-missing-genes.csv", index=False)
        region_rows = []
        for name in regions:
            region_rows.append({"section":"CID4535","region":name,"spots":spots[name],"total_UMI":totals[name],"matched_program_genes":len(matched),
                                "mean_log2_CPM_plus_1_score":score[name],"single_section_descriptive":True})
        pd.DataFrame(region_rows).to_csv(out_pb / "primary-program-region-scores.csv", index=False)
        pd.DataFrame([{"section":"CID4535", **deltas, "eligible_sections":1, "population_CI":np.nan, "population_p_value":np.nan,
                       "sign_test":"NOT_RUN_SINGLE_ELIGIBLE_SECTION", "patient_level_inference":"BLOCKED"}]).to_csv(out_pb / "primary-program-B1-B2-B3-sensitivity.csv", index=False)

        display_rows = []
        for gene in DISPLAY_GENES:
            if gene in genes:
                j = int(genes.get_loc(gene))
                row = {"gene": gene, "matched": True}
                for name in regions:
                    row[f"{name}_raw_count"] = int(counts[name][j])
                    row[f"{name}_CPM"] = float(cpm[name][j])
                    row[f"{name}_log2_CPM_plus_1"] = float(logcpm[name][j])
                row["B2_boundary_minus_core"] = float(logcpm["B2_boundary_D_le_2"][j] - logcpm["core_D_gt_3"][j])
            else:
                row = {"gene":gene,"matched":False,"B2_boundary_minus_core":np.nan}
            display_rows.append(row)
        pd.DataFrame(display_rows).to_csv(out_pb / "prespecified-six-genes.csv", index=False)

        pb_counts = pd.DataFrame({"gene_id": genes.astype(str), **{f"{k}_raw_count": v for k,v in counts.items()}})
        pb_counts.to_csv(out_pb / "region-pseudobulk-raw-counts.full.csv.gz", index=False, compression="gzip")
        whole = pd.DataFrame({"gene_id": genes.astype(str),
                              "B2_boundary_raw_count": counts["B2_boundary_D_le_2"], "core_raw_count": counts["core_D_gt_3"],
                              "B2_boundary_CPM": cpm["B2_boundary_D_le_2"], "core_CPM": cpm["core_D_gt_3"],
                              "B2_boundary_log2_CPM_plus_1": logcpm["B2_boundary_D_le_2"], "core_log2_CPM_plus_1": logcpm["core_D_gt_3"]})
        whole["B2_boundary_minus_core_log2_CPM_plus_1"] = whole["B2_boundary_log2_CPM_plus_1"] - whole["core_log2_CPM_plus_1"]
        whole["absolute_descriptive_difference"] = whole["B2_boundary_minus_core_log2_CPM_plus_1"].abs()
        whole = whole.sort_values(["absolute_descriptive_difference","gene_id"], ascending=[False,True], kind="mergesort").reset_index(drop=True)
        whole.insert(0, "deterministic_rank", np.arange(1, len(whole)+1))
        whole["inferential_DE_status"] = "NOT_RUN_INSUFFICIENT_REPLICATION"
        whole["p_value"] = np.nan
        whole["padj"] = np.nan
        whole.to_csv(out_pb / "descriptive-whole-gene-table.full.csv.gz", index=False, compression="gzip")
        pd.DataFrame([{"section":"CID4535","B2_boundary_spots":spots["B2_boundary_D_le_2"],"core_spots":spots["core_D_gt_3"],
                       "B2_boundary_total_UMI":totals["B2_boundary_D_le_2"],"core_total_UMI":totals["core_D_gt_3"],
                       "inferential_DE_status":"NOT_RUN_INSUFFICIENT_REPLICATION","reason":"one boundary/core pseudobulk pair; no biological replication and no full-rank inferential design",
                       "p_value":np.nan,"padj":np.nan}]).to_csv(out_pb / "pseudobulk-design-status.csv", index=False)

        update("pathway_analysis", 24, primary_delta=deltas["B2_boundary_minus_core_primary"])
        path_rows = []
        for name, members in sets.items():
            use = [g for g in members if g in genes]
            idx = genes.get_indexer(use)
            b = float(logcpm["B2_boundary_D_le_2"][idx].mean()) if use else np.nan
            c = float(logcpm["core_D_gt_3"][idx].mean()) if use else np.nan
            path_rows.append({"resource":"MSigDB Hallmark","release":"2024.1.Hs","pathway":name,"full_genes":len(members),"matched_genes":len(use),
                              "coverage_fraction":len(use)/len(members) if members else np.nan,"boundary_activity_mean_log2_CPM_plus_1":b,
                              "core_activity_mean_log2_CPM_plus_1":c,"boundary_minus_core":b-c,"method":"unweighted matched-gene mean; descriptive"})
        pd.DataFrame(path_rows).sort_values("pathway").to_csv(out_pb / "pathway-hallmark-results.full.csv", index=False)
        prog_file = root / "01_inputs" / "resources" / "PROGENy-omnipath-snapshot.tsv"
        prog_raw = pd.read_csv(prog_file, sep="\t", dtype=str)
        prog_w = prog_raw[prog_raw["label"].isin(["pathway","weight"])].pivot_table(index=["record_id","genesymbol"], columns="label", values="value", aggfunc="first").reset_index()
        prog_w = prog_w.dropna(subset=["pathway","weight"])
        prog_w["weight"] = pd.to_numeric(prog_w["weight"], errors="coerce")
        prog_w = prog_w.dropna(subset=["weight"])
        prog_net = prog_w.rename(columns={"pathway":"source","genesymbol":"target"})[["source","target","weight"]]
        prog_net = prog_net[prog_net["target"].isin(genes)].groupby(["source","target"],as_index=False)["weight"].mean()
        expr = pd.DataFrame([logcpm["B2_boundary_D_le_2"], logcpm["core_D_gt_3"]], index=["B2_boundary_D_le_2","core_D_gt_3"], columns=genes)
        decoupler_status = {"status":"NOT_RUN", "resource_sha256":sha256_file(prog_file), "network_edges":len(prog_net)}
        try:
            import decoupler as dc
            ulm = dc.mt.ulm(expr, prog_net, tmin=5, raw=False, empty=False, bsize=250000, verbose=False)
            if isinstance(ulm, pd.DataFrame):
                score_df = ulm
            elif isinstance(ulm, tuple):
                score_df = pd.DataFrame(ulm[0], index=expr.index)
            else:
                score_df = pd.DataFrame(ulm)
            if set(expr.index).issubset(score_df.index):
                pass
            elif score_df.shape[0] == 2:
                score_df.index = expr.index
            rows = []
            for pathway in score_df.columns:
                rows.append({"resource":"PROGENy OmniPath frozen snapshot","pathway":str(pathway),"boundary_activity":float(score_df.loc["B2_boundary_D_le_2",pathway]),
                             "core_activity":float(score_df.loc["core_D_gt_3",pathway]),"boundary_minus_core":float(score_df.loc["B2_boundary_D_le_2",pathway]-score_df.loc["core_D_gt_3",pathway]),
                             "matched_targets":int(prog_net.loc[prog_net.source==pathway,"target"].nunique()),"method":"decoupler ULM; descriptive"})
            pd.DataFrame(rows).sort_values("pathway").to_csv(out_pb / "pathway-progeny-results.full.csv", index=False)
            decoupler_status.update({"status":"COMPLETED", "decoupler_version":importlib.metadata.version("decoupler"),"pathways":len(rows)})
        except Exception as e:
            decoupler_status.update({"status":"FAILED_EXTENSION_RETAINED", "error":repr(e), "traceback":traceback.format_exc()})
            pd.DataFrame(columns=["resource","pathway","boundary_activity","core_activity","boundary_minus_core","matched_targets","method"]).to_csv(out_pb / "pathway-progeny-results.full.csv", index=False)
        write_json(out_pb / "pathway-resource-and-coverage.json", {"hallmark":{"source":str(gmt),"sha256":sha256_file(gmt),"sets":len(sets)},
                                                                   "progeny":{"source":str(prog_file),"sha256":sha256_file(prog_file),"network_edges_after_feature_intersection":len(prog_net),"status":decoupler_status},
                                                                   "primary_set_unchanged":True})
        del prog_raw, prog_w, prog_net, expr
        disk_guard("after pathways")

        update("liana_rank_aggregate", 38)
        liana_status = {"status":"NOT_RUN"}
        lr_file = root / "01_inputs" / "resources" / "liana-consensus-frozen.csv"
        lr_resource = pd.read_csv(lr_file)
        try:
            import liana as li
            ref = ad.read_h5ad(s2 / "ref_40k.h5ad")
            if not sparse.issparse(ref.X):
                raise RuntimeError("S2 reference count matrix is not sparse")
            if "producer_celltype_minor" not in ref.obs:
                raise RuntimeError("producer_celltype_minor absent")
            if ref.obs["producer_celltype_minor"].isna().any():
                raise RuntimeError("producer labels contain missing values")
            ref.obs["producer_celltype_minor"] = ref.obs["producer_celltype_minor"].astype("category")
            sc.pp.normalize_total(ref, target_sum=1e4)
            sc.pp.log1p(ref)
            li.mt.rank_aggregate(ref, groupby="producer_celltype_minor", resource=lr_resource, expr_prop=0.1, min_cells=5,
                                 return_all_lrs=True, use_raw=False, n_perms=1000, seed=20260904, n_jobs=1, inplace=True, verbose=True)
            lrres = ref.uns["liana_res"].copy()
            lrres.to_csv(out_lr / "liana-rank-aggregate.full.csv.gz", index=False, compression="gzip")
            liana_status = {"status":"COMPLETED", "liana_version":importlib.metadata.version("liana"), "rows":len(lrres),
                            "resource":str(lr_file),"resource_sha256":sha256_file(lr_file),"resource_pairs":len(lr_resource),
                            "groupby":"producer_celltype_minor","expr_prop":0.1,"min_cells":5,"n_perms":1000,"seed":20260904,"n_jobs":1,
                            "normalization":"normalize_total target_sum=10000 then log1p","return_all_lrs":True,
                            "ranking_basis":"LIANA rank_aggregate magnitude_rank ascending, then source/target/ligand/receptor identifier"}
            del ref
        except Exception as e:
            lrres = pd.DataFrame()
            liana_status = {"status":"FAILED_EXTENSION_RETAINED", "error":repr(e), "traceback":traceback.format_exc(),
                            "liana_version":importlib.metadata.version("liana"),"resource":str(lr_file),"resource_sha256":sha256_file(lr_file)}
            pd.DataFrame().to_csv(out_lr / "liana-rank-aggregate.full.csv.gz", index=False, compression="gzip")
        write_json(out_lr / "liana-method-and-resource.json", liana_status)

        # Required interaction extraction, preserving absent rows explicitly.
        required_specs = [
            ("CXCL9-CXCR3", lambda l,r: l=="CXCL9" and "CXCR3" in r),
            ("CXCL10-CXCR3", lambda l,r: l=="CXCL10" and "CXCR3" in r),
            ("CD274-PDCD1", lambda l,r: l=="CD274" and "PDCD1" in r),
            ("TGFB1-TGFBR-family", lambda l,r: l=="TGFB1" and "TGFBR" in r),
            ("SPP1-CD44", lambda l,r: l=="SPP1" and "CD44" in r),
        ]
        req_frames = []
        if not lrres.empty:
            lcol = "ligand_complex" if "ligand_complex" in lrres.columns else "ligand"
            rcol = "receptor_complex" if "receptor_complex" in lrres.columns else "receptor"
            for name, fn in required_specs:
                sel = lrres[[fn(str(l),str(r)) for l,r in zip(lrres[lcol],lrres[rcol])]].copy()
                if sel.empty:
                    req_frames.append(pd.DataFrame([{"prespecified_interaction":name,"status":"NOT_FOUND_IN_FILTERED_LIANA_RESULT"}]))
                else:
                    sel.insert(0,"status","FOUND")
                    sel.insert(0,"prespecified_interaction",name)
                    req_frames.append(sel)
        else:
            req_frames = [pd.DataFrame([{"prespecified_interaction":n,"status":"LIANA_EXTENSION_FAILED"}]) for n,_ in required_specs]
        required_lr = pd.concat(req_frames, ignore_index=True, sort=False)
        required_lr.to_csv(out_lr / "liana-prespecified-interactions.csv", index=False)

        # Deterministic top 10 for external-evidence lookup.
        if not lrres.empty:
            rank_col = "magnitude_rank" if "magnitude_rank" in lrres.columns else next((c for c in lrres.columns if c.endswith("rank")), None)
            sort_cols = ([rank_col] if rank_col else []) + [c for c in ["source","target","ligand_complex","receptor_complex"] if c in lrres.columns]
            top_lr = lrres.sort_values(sort_cols, kind="mergesort").head(10).copy()
        else:
            top_lr = pd.DataFrame()
        top_lr.to_csv(out_lr / "liana-top10-for-external-evidence.csv", index=False)

        update("spatial_niche_context", 70, liana_rows=len(lrres))
        context_rows = []
        if not lrres.empty:
            tang = pd.read_csv(s4 / "proportions_tangram.csv.gz")
            cid = tang[tang["section"].astype(str)=="CID4535"].set_index("barcode")
            mm = mask_df.reindex(cid.index)
            cent = pd.read_csv(s5 / "niche-composition-centroids.csv")
            niche_col = "niche" if "niche" in cent.columns else cent.columns[0]
            co = pd.read_csv(s5 / "co-occurrence.csv")
            co = co[co["section"].astype(str)=="CID4535"]
            for _, row in top_lr.iterrows():
                src, tgt = str(row.get("source","")), str(row.get("target",""))
                src_niche = str(cent.loc[cent[src].idxmax(),niche_col]) if src in cent.columns else None
                tgt_niche = str(cent.loc[cent[tgt].idxmax(),niche_col]) if tgt in cent.columns else None
                cq = co[(co.niche_a.astype(str)==str(src_niche)) & (co.niche_b.astype(str)==str(tgt_niche))]
                context_rows.append({"source":src,"target":tgt,"ligand_complex":row.get("ligand_complex",row.get("ligand")),
                                     "receptor_complex":row.get("receptor_complex",row.get("receptor")),
                                     "source_mean_composition_B2":float(cid.loc[mm["boundary_invasive_d2"].astype(bool),src].mean()) if src in cid else np.nan,
                                     "source_mean_composition_core":float(cid.loc[mm["core_invasive_d_gt_3"].astype(bool),src].mean()) if src in cid else np.nan,
                                     "target_mean_composition_B2":float(cid.loc[mm["boundary_invasive_d2"].astype(bool),tgt].mean()) if tgt in cid else np.nan,
                                     "target_mean_composition_core":float(cid.loc[mm["core_invasive_d_gt_3"].astype(bool),tgt].mean()) if tgt in cid else np.nan,
                                     "source_max_centroid_niche":src_niche,"target_max_centroid_niche":tgt_niche,
                                     "CID4535_niche_cooccurrence_ratio":float(cq.iloc[0]["co_occurrence_ratio"]) if not cq.empty else np.nan,
                                     "interpretation_limit":"shared scRNA communication plausibility plus composition/co-location context; not independent validation or spot-resolved sender/receiver expression"})
        pd.DataFrame(context_rows).to_csv(out_lr / "liana-spatial-niche-context.csv", index=False)
        write_json(out_lr / "boundary-celltype-specific-liana-status.json", {"status":"NOT_IDENTIFIABLE",
                   "reason":"CID4535 Visium spots are mixtures and no cell-type-resolved boundary expression measurement is available; ingest/composition labels cannot create such expression.",
                   "overall_scRNA_rank_aggregate_status":liana_status["status"]})

        top20 = whole.head(20)[["deterministic_rank","gene_id","B2_boundary_minus_core_log2_CPM_plus_1","absolute_descriptive_difference"]]
        top20.to_csv(out_lr / "top20-descriptive-genes-for-external-evidence.csv", index=False)
        lr_targets = []
        if not top_lr.empty:
            for i, row in top_lr.reset_index(drop=True).iterrows():
                lr_targets.append({"rank":i+1,"source":str(row.get("source","")),"target":str(row.get("target","")),
                                   "ligand":str(row.get("ligand_complex",row.get("ligand",""))),"receptor":str(row.get("receptor_complex",row.get("receptor",""))),
                                   "query":f'{row.get("ligand_complex",row.get("ligand",""))} {row.get("receptor_complex",row.get("receptor",""))} cancer interaction' })
        query_targets = {"selection_rule":"genes: absolute descriptive B2-core difference descending then gene_id; interactions: LIANA magnitude_rank ascending then identifiers",
                         "top20_genes":top20.to_dict("records"),"top10_liana_interactions":lr_targets,
                         "prespecified_items":["CXCL9 CXCR3","CXCL10 CXCR3","CD274 PDCD1","TGFB1 TGFBR1 TGFBR2","SPP1 CD44","HALLMARK_INTERFERON_GAMMA_RESPONSE"]}
        write_json(out_lr / "external-evidence-query-targets.json", query_targets)

        update("integrated_figure", 80)
        fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
        reg_order = ["B1_boundary_D_le_1","B2_boundary_D_le_2","B3_boundary_D_le_3","core_D_gt_3"]
        axes[0,0].bar(["B1","B2","B3","Core"],[score[x] for x in reg_order],color=["#7B6FD0","#4C78A8","#72B7B2","#B9B9B9"])
        axes[0,0].set_ylabel("Mean log2(CPM+1)")
        axes[0,0].set_title("Frozen IFN-γ program (196/200 matched)")
        ddf = pd.DataFrame(display_rows)
        axes[0,1].barh(ddf["gene"],ddf["B2_boundary_minus_core"],color=["#E45756" if x>=0 else "#4C78A8" for x in ddf["B2_boundary_minus_core"]])
        axes[0,1].axvline(0,color="black",lw=.8); axes[0,1].set_xlabel("B2 boundary − core"); axes[0,1].set_title("Prespecified display genes")
        t10 = whole.head(10).iloc[::-1]
        axes[1,0].barh(t10["gene_id"],t10["B2_boundary_minus_core_log2_CPM_plus_1"],color=["#F58518" if x>=0 else "#54A24B" for x in t10["B2_boundary_minus_core_log2_CPM_plus_1"]])
        axes[1,0].axvline(0,color="black",lw=.8); axes[1,0].set_xlabel("B2 boundary − core"); axes[1,0].set_title("Largest descriptive gene effects")
        if not top_lr.empty and "magnitude_rank" in top_lr.columns:
            labs = [f"{r.get('ligand_complex',r.get('ligand',''))}→{r.get('receptor_complex',r.get('receptor',''))}\n{r.get('source','')}→{r.get('target','')}" for _,r in top_lr.head(6).iterrows()][::-1]
            vals = (-np.log10(np.maximum(top_lr.head(6)["magnitude_rank"].astype(float).to_numpy(),1e-300)))[::-1]
            axes[1,1].barh(range(len(labs)),vals,color="#B279A2"); axes[1,1].set_yticks(range(len(labs)),labels=labs,fontsize=7)
            axes[1,1].set_xlabel("−log10 LIANA magnitude rank"); axes[1,1].set_title("Top inferred interactions")
        else:
            axes[1,1].text(.5,.5,"LIANA extension unavailable",ha="center",va="center"); axes[1,1].set_axis_off()
        fig.suptitle("SpatialWarrant S6 | CID4535 descriptive boundary analysis",fontsize=15,fontweight="bold")
        fig.savefig(out_pb / "S6-integrated-figure.png",dpi=220,bbox_inches="tight")
        plt.close(fig)

        method_limits = {
            "execution_route":"local Python/scverse execution; not a registered NGS workflow run",
            "primary_boundary":"S3 frozen publisher Invasive cancer/Stroma geometry only; B2 primary, B1/B3 sensitivity, core D>3",
            "boundary_redefined_in_S6":False,
            "independent_units":1,
            "inference":"single-section descriptive effects only; no population CI, p value, sign test, or patient-level inference",
            "pydeseq2":"NOT_RUN_INSUFFICIENT_REPLICATION",
            "communication":"LIANA on producer-labeled scRNA is interaction plausibility; mixed spots do not identify cell-type-specific boundary expression",
            "shared_reference":"S4 composition, S5 niches, and LIANA share the Wu scRNA reference and are not independent validation",
            "machine_verdict":"PENDING","biological_conclusion":"PENDING","S7":"NOT_STARTED"
        }
        write_json(out_pb / "methods-and-limitations.json", method_limits)
        write_json(out_lr / "methods-and-limitations.json", method_limits)
        env = {"created_at_utc":utcnow(),"python":sys.version,"executable":sys.executable,"platform":platform.platform(),
               "packages":{p:importlib.metadata.version(p) for p in ["anndata","scanpy","numpy","pandas","scipy","matplotlib","psutil","liana","decoupler","mudata","plotnine","marsilea"]},
               "dependency_install_log":str(out_lr / "dependency-install.log"),"execution_route":method_limits["execution_route"]}
        write_json(out_pb / "execution-environment.json", env)
        write_json(out_lr / "execution-environment.json", env)

        local_result = {"status":"LOCAL_COMPUTATION_COMPLETED","started_at_utc":started_utc,"ended_at_utc":utcnow(),"elapsed_seconds":time.perf_counter()-started,
                        "peak_process_memory_bytes":peak_memory(),"start_free_C_bytes":start_free,"current_free_C_bytes":shutil.disk_usage("C:\\").free,
                        "primary_program":coverage,"region_spots":spots,"region_total_UMI":totals,"program_scores":score,"program_differences":deltas,
                        "inferential_DE":"NOT_RUN_INSUFFICIENT_REPLICATION","liana":liana_status,"decoupler":decoupler_status,
                        "patient_level_inference":"BLOCKED","machine_verdict":"PENDING","biological_conclusion":"PENDING","external_evidence":"PENDING","bionexus_audit":"PENDING","S7":"NOT_STARTED"}
        write_json(out_pb / "S6-local-result.json", local_result)
        write_json(out_lr / "S6-local-result.json", local_result)
        write_sha_manifest(out_pb, out_pb / "SHA256SUMS.local.txt")
        write_sha_manifest(out_lr, out_lr / "SHA256SUMS.local.txt")
        update("local_computation_complete", 85, status="LOCAL_COMPUTATION_COMPLETED", primary_delta=deltas["B2_boundary_minus_core_primary"], liana_status=liana_status["status"])
        print(json.dumps(native(local_result), ensure_ascii=False, allow_nan=False))
        return 0
    except Exception as e:
        failure = {"status":"FAILED","stage":json.loads(progress.read_text(encoding="utf-8"))["stage"] if progress.exists() else "unknown",
                   "error":repr(e),"traceback":traceback.format_exc(),"at_utc":utcnow(),"elapsed_seconds":time.perf_counter()-started,
                   "free_C_bytes":shutil.disk_usage("C:\\").free,"peak_process_memory_bytes":peak_memory()}
        write_json(out_lr / "failure.json", failure)
        write_json(out_pb / "failure.json", failure)
        update("failed", 0, status="FAILED", error=repr(e))
        print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
