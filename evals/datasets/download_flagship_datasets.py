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
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "evals"))

from flagship_validation import (  # noqa: E402
    FLAGSHIP_DATASETS,
    flagship_dataset_dir,
    flagship_dataset_present,
)

from bionexus.egress_guard import DataClassification, guarded_urlopen  # noqa: E402

GEO_KANG2018_URL = "https://www.ncbi.nlm.nih.gov/geo/download/?acc=GSE96583&format=file"
CITESEQ_FILES = {
    "pbmc_10k_protein_v3.h5ad": {
        "url": "https://raw.githubusercontent.com/YosefLab/scVI-data/master/pbmc_10k_protein_v3.h5ad",
        "sha256": "5f08b8575febf9e04b209b94eb43f6335f1e33b0985cdcf44adf7320f6243c69",
    },
    "pbmc_5k_protein_v3.h5ad": {
        "url": "https://raw.githubusercontent.com/YosefLab/scVI-data/master/pbmc_5k_protein_v3.h5ad",
        "sha256": "a1bf51e070d24b39627ea4de9b3e489a4637ff795e1061e0733e26c3baec8847",
    },
}
XENIUM_ARCHIVE = {
    "name": "Xenium_V1_Protein_Human_Kidney_tiny_outs.zip",
    "url": (
        "https://cf.10xgenomics.com/samples/xenium/4.0.0/"
        "Xenium_V1_Protein_Human_Kidney_tiny/Xenium_V1_Protein_Human_Kidney_tiny_outs.zip"
    ),
    "sha256": "abd7e8f7fd047dcc6afdb1e9eece90d4533d3ead053c6f05c482be050bdf79d2",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _download_verified(url: str, destination: Path, expected_sha256: str | None) -> None:
    if destination.is_file() and (expected_sha256 is None or _sha256(destination) == expected_sha256):
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "BioNexus/1.0 flagship-validation",
            "Accept": "application/octet-stream,*/*;q=0.8",
        },
    )
    with guarded_urlopen(
        request,
        timeout=120,
        purpose=f"download pinned BioNexus public flagship dataset {destination.name}",
        data_classification=DataClassification.PUBLIC_BENCHMARK,
    ) as response, partial.open("wb") as handle:
        for block in iter(lambda: response.read(1024 * 1024), b""):
            handle.write(block)
    observed = _sha256(partial)
    if expected_sha256 is not None and observed != expected_sha256:
        partial.unlink(missing_ok=True)
        raise RuntimeError(
            f"download hash mismatch for {destination.name}: expected {expected_sha256}, observed {observed}"
        )
    partial.replace(destination)


def _extract_verified_zip(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"archive path escapes destination: {member.filename}")
        bundle.extractall(destination)


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
            _download_verified(GEO_KANG2018_URL, tar_path, expected_sha256=None)
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
    """B: public 10x PBMC CITE-seq files used by scvi-tools totalVI tutorials."""
    destination = flagship_dataset_dir("citeseq_pbmc_sorted")
    destination.mkdir(parents=True, exist_ok=True)
    for name, source in CITESEQ_FILES.items():
        _download_verified(source["url"], destination / name, source["sha256"])
    steps = """
    Two pinned processed public 10x PBMC CITE-seq AnnData files are present.
    BN-ANN-IV-001 uses PBMC10k only for fitting and PBMC5k only for holdout.
    Paired ADT is real orthogonal evidence, not independent expert ground truth.
    """
    _report("citeseq_pbmc_sorted", flagship_dataset_present("citeseq_pbmc_sorted"), steps)
    return flagship_dataset_present("citeseq_pbmc_sorted")


def fetch_xenium(root: Path) -> bool:
    """C: Xenium / CosMx / MERFISH-class in situ data with coordinates."""
    destination = flagship_dataset_dir("xenium_spatial_truth")
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / XENIUM_ARCHIVE["name"]
    _download_verified(XENIUM_ARCHIVE["url"], archive, XENIUM_ARCHIVE["sha256"])
    _extract_verified_zip(archive, destination / "official_tiny_outs")
    steps = """
    The pinned official XOA v4 tiny human-kidney archive is present and hash verified.
    It supports real-instrument technical acceptance only: 10x states that this
    tiny subset is not intended for biological conclusions.
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
