"""
External Benchmark Datasets Fetcher & Reference Manifest for BioNexus Eval L3.

Provides standardized access to real-world benchmark datasets:
1. 10x Genomics PBMC 3k (scRNA-seq baseline)
2. 10x Visium Spatial Transcriptomics Sagittal Mouse Brain
3. ClinVar Pathogenic / Benign variant control set

Only an explicitly pinned download is materialized. Unconfigured sources fail
closed; synthetic fixtures belong under tests/fixtures and never use these names.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict

BENCHMARK_CATALOG: Dict[str, Dict[str, Any]] = {
    "pbmc3k_scrna": {
        "description": "10x Genomics PBMC 3k single-cell RNA-seq baseline counts dataset",
        "modality": "scRNA-seq",
        "organism": "Homo sapiens",
        "canonical_markers": ["CD3D", "CD19", "MS4A1", "CD14", "FCGR3A", "GNLY"],
        "target_file": "pbmc3k_raw.h5ad",
        "direct_url": "https://raw.githubusercontent.com/scverse/scanpy-tutorials/master/pbmc3k_raw.h5ad",
    },
    "visium_mouse_brain": {
        "description": "10x Genomics Visium Spatial Transcriptomics Mouse Brain Section",
        "modality": "Spatial Transcriptomics",
        "organism": "Mus musculus",
        "canonical_svgs": ["Mbp", "Plp1", "Snap25", "Nrgn"],
        "target_file": "visium_sagittal.h5ad",
        "direct_url": None,  # Generated or fetched via scanpy.datasets.visium_sge
    },
    "clinvar_controls": {
        "description": "ClinVar curated Pathogenic/Benign variant ground-truth control subset",
        "modality": "Genomics / ACMG",
        "organism": "Homo sapiens",
        "sample_size": 250,
        "target_file": "clinvar_controls.json",
    },
}


def download_benchmark(dataset_name: str, dest_dir: Path, *, expected_sha256: str | None = None) -> Path:
    """Fetch bytes matching a caller-retained digest; never substitute synthetic data.

    A matching hash establishes byte identity only, not scientific ground truth.
    Old unpinned caches are deliberately not trusted: earlier versions could
    write synthetic fixtures under the public dataset filenames.
    """
    meta = BENCHMARK_CATALOG.get(dataset_name)
    if not meta:
        raise ValueError(f"Unknown benchmark dataset: {dataset_name}. Choose from: {list(BENCHMARK_CATALOG.keys())}")

    if not meta.get("direct_url"):
        raise ValueError(f"No public download source configured for {dataset_name}; outcome NOT VERIFIED")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("An independently retained expected_sha256 is required before downloading or using a cache")
    expected_sha256 = expected_sha256.lower()

    def verify(path: Path) -> None:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        if not path.stat().st_size or digest.hexdigest() != expected_sha256:
            raise ValueError(f"Dataset SHA-256 mismatch or empty file: {path}; outcome NOT VERIFIED")

    out_path = dest_dir / meta["target_file"]
    if out_path.exists():
        verify(out_path)
        return out_path
    dest_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".reference-download-", dir=dest_dir) as staging:
        temporary = Path(staging) / "download.part"
        urllib.request.urlretrieve(meta["direct_url"], temporary)
        verify(temporary)
        # Exclusive creation preserves any file created concurrently.
        with temporary.open("rb") as source, out_path.open("xb") as target:
            shutil.copyfileobj(source, target)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="BioNexus External Benchmark Dataset Fetcher")
    parser.add_argument("--dataset", choices=list(BENCHMARK_CATALOG.keys()), required=True)
    parser.add_argument("--sha256", required=True, help="Expected raw-byte SHA-256 retained independently of this download")
    parser.add_argument("--dest", default="evals/datasets/benchmarks")
    args = parser.parse_args()

    dest_p = Path(args.dest)
    download_benchmark(args.dataset, dest_p, expected_sha256=args.sha256)


if __name__ == "__main__":
    main()
