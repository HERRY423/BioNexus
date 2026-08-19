"""
Download / prepare the real public datasets for the BioNexus flagship
external-validation track (BNS-015, v1.0 real-data).

Honesty contract: this script NEVER fabricates or synthesizes the required
files. For every dataset it either (a) performs a real download from a stable
public source, or (b) prints the exact manual-acquisition steps when the
source requires a EULA / registration / non-stable URL. Exit code 0 only when
all required files for all three flagship datasets are present.

Usage:
    python evals/datasets/download_flagship_datasets.py [--only DATASET_ID]
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "evals"))

from flagship_validation import (  # noqa: E402
    FLAGSHIP_DATASETS,
    flagship_dataset_dir,
    flagship_dataset_present,
)

GEO_KANG2018_URL = "https://www.ncbi.nlm.nih.gov/geo/download/?acc=GSE96583&format=file"


def _report(dataset_id: str, ok: bool, note: str = "") -> None:
    status = "PRESENT" if ok else "MISSING"
    print(f"[{status}] {dataset_id}")
    for line in note.strip().splitlines():
        print(f"         {line}")


def fetch_kang2018(root: Path) -> bool:
    """A: Kang et al. 2018 PBMC IFN-beta (GEO GSE96583).

    Automated step: download the GEO supplementary tarball. Manual step:
    build pbmc_ifnb_counts.h5ad (obs: donor, condition in {ctrl, stim}) and
    published_de_truth.csv from the paper's published DE tables.
    """
    d = flagship_dataset_dir("kang2018_pbmc_ifnb")
    d.mkdir(parents=True, exist_ok=True)
    tar_path = d / "GSE96583_raw.tar"
    if not tar_path.is_file():
        print(f"    downloading GEO supplementary tarball -> {tar_path} ...")
        try:
            urllib.request.urlretrieve(GEO_KANG2018_URL, tar_path)  # noqa: S310
        except Exception as e:
            print(f"    automatic download failed ({e}); fetch manually:")
            print(f"      {GEO_KANG2018_URL}")
    steps = """
    Manual preparation required (not auto-generated, never synthesized):
      1. Extract the tarball; it contains per-donor UMI count matrices
         (matrix_*_ctrl.txt / matrix_*_stim.txt.gz style files).
      2. Build data/flagship/kang2018_pbmc_ifnb/pbmc_ifnb_counts.h5ad:
         raw integer counts, obs columns 'donor' (8 donors) and
         'condition' ('ctrl' | 'stim').
      3. Build data/flagship/kang2018_pbmc_ifnb/published_de_truth.csv:
         columns 'gene' plus the paper's published significance score
         (e.g. padj), taken from Kang et al. 2018 doi:10.1038/s41467-018-04001-5
         supplementary DE tables — the independent truth set.
    """
    _report("kang2018_pbmc_ifnb", flagship_dataset_present("kang2018_pbmc_ifnb"), steps)
    return flagship_dataset_present("kang2018_pbmc_ifnb")


def fetch_citeseq(root: Path) -> bool:
    """B: CITE-seq / sorted PBMC (Hao et al. 2021 multimodal PBMC, 10x public)."""
    flagship_dataset_dir("citeseq_pbmc_sorted").mkdir(parents=True, exist_ok=True)
    steps = """
    Manual acquisition (10x data files are versioned per release; follow the
    current links rather than pinned URLs):
      1. 10x Genomics public CITE-seq PBMC feature-barcode datasets, or
         Hao et al. 2021 (Cell 184:3573, doi:10.1016/j.cell.2021.04.048)
         multimodal PBMC 'bmcite' (available via the SeuratData R package).
      2. Convert to data/flagship/citeseq_pbmc_sorted/citeseq_pbmc.h5ad with
         the ADT protein modality exposed (obsm['prot'] or a var-masked ADT
         block) and sorted-population labels in obs when available.
    The benchmark measures whether BioNexus distrusts annotations lacking this
    orthogonal protein evidence — the evidence itself must be real.
    """
    _report("citeseq_pbmc_sorted", flagship_dataset_present("citeseq_pbmc_sorted"), steps)
    return flagship_dataset_present("citeseq_pbmc_sorted")


def fetch_xenium(root: Path) -> bool:
    """C: Xenium / CosMx / MERFISH-class in situ data with coordinates."""
    flagship_dataset_dir("xenium_spatial_truth").mkdir(parents=True, exist_ok=True)
    steps = """
    Manual acquisition (10x/Vizgen public in situ datasets are distributed via
    registered downloads; follow the current links):
      1. 10x Genomics Xenium public datasets (e.g. Human Breast FFPE) or
         Vizgen MERSCOPE public MERFISH releases.
      2. Build data/flagship/xenium_spatial_truth/spatial_truth.h5ad:
         raw counts + physical coordinates in obsm['spatial'];
         optional obs columns 'cell_area' and 'fov'.
    The artifact injectors then manufacture leakage / size / density /
    permutation / FOV artifacts on this REAL coordinate field.
    """
    _report("xenium_spatial_truth", flagship_dataset_present("xenium_spatial_truth"), steps)
    return flagship_dataset_present("xenium_spatial_truth")


_FETCHERS = {
    "kang2018_pbmc_ifnb": fetch_kang2018,
    "citeseq_pbmc_sorted": fetch_citeseq,
    "xenium_spatial_truth": fetch_xenium,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", choices=sorted(FLAGSHIP_DATASETS), help="prepare a single dataset")
    args = ap.parse_args()

    targets = [args.only] if args.only else sorted(FLAGSHIP_DATASETS)
    print("BioNexus flagship real-data acquisition (BNS-015)")
    print("Rule: files are downloaded from real public sources or fetched manually.")
    print("      Nothing here is ever synthesized or imitated.\n")

    ok = True
    for dataset_id in targets:
        ok = _FETCHERS[dataset_id](REPO_ROOT) and ok

    present = sum(1 for t in targets if flagship_dataset_present(t))
    print(f"\n{present}/{len(targets)} flagship datasets present.")
    if present < len(targets):
        print("Absent datasets: the corresponding flagship eval cases will honestly")
        print("SKIP (SKIPPED_NO_BACKEND / NOT_EVALUATED_NO_BACKEND, BNS-EM-009).")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
