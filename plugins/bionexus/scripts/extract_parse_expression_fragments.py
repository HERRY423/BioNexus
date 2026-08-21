#!/usr/bin/env python3
"""Download/process pinned Parse expression fragments with resume-safe shards.

Each immutable Lance data file is downloaded sequentially to a bounded local
temporary path, filtered locally to the 725,031 preregistered cell IDs, and
reduced to a small pseudobulk checkpoint. The source fragment is deleted after
its SHA-256 and checkpoint have been recorded. Shards own disjoint fragment
IDs and can run concurrently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

import anndata as ad
import numpy as np
import pandas as pd
import requests
from scipy import sparse

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_LANCE_RUNTIME = REPO_ROOT / "runtime_lance"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if LOCAL_LANCE_RUNTIME.is_dir():
    sys.path.insert(0, str(LOCAL_LANCE_RUNTIME))

from scripts.extract_parse_natural_pseudobulk import (  # noqa: E402
    BASE_URI,
    ELIGIBLE_CYTOKINES,
    EXPECTED_DONORS,
    EXPECTED_TOTAL_CELLS,
    PINNED_REVISION,
    _array_sha256,
    _assert_pinned_revision,
    _atomic_json,
    _ensure_hf_auth,
    _global_population,
    _load_genes,
    _load_json,
    _sha256,
    _utc_now,
)

DEFAULT_OUTPUT = REPO_ROOT / "data" / "independent" / "parse10m_pbmc_ifnb_natural_v1"


def _fragment_paths(output_dir: Path, fragment_id: int) -> tuple[Path, Path]:
    root = output_dir / "checkpoints" / "expression_fragments"
    stem = f"fragment_{fragment_id:05d}"
    return root / f"{stem}.npz", root / f"{stem}.manifest.json"


def _valid_fragment_checkpoint(
    npz_path: Path,
    manifest_path: Path,
    *,
    fragment_id: int,
    source_file: str,
    source_file_size: int,
    physical_rows: int,
    n_samples: int,
    n_genes: int,
) -> bool:
    if not npz_path.is_file() or not manifest_path.is_file():
        return False
    try:
        manifest = _load_json(manifest_path)
        expected = {
            "schema_version": "bionexus.parse-expression-fragment-checkpoint.v1",
            "source_revision": PINNED_REVISION,
            "fragment_id": fragment_id,
            "source_file": source_file,
            "source_file_size_bytes": source_file_size,
            "physical_rows": physical_rows,
            "npz_sha256": _sha256(npz_path),
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            return False
        with np.load(npz_path, allow_pickle=False) as payload:
            counts = payload["counts"]
            cell_ids = payload["cell_integer_ids"]
            row_counts = payload["expression_row_counts"]
        return (
            counts.shape == (n_samples, n_genes)
            and counts.dtype == np.uint64
            and cell_ids.dtype == np.int64
            and row_counts.dtype == np.uint64
            and cell_ids.shape == row_counts.shape
            and int(row_counts.sum()) == int(manifest.get("expression_records_aggregated", -1))
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False


def _download_fragment(
    *,
    source_file: str,
    expected_size: int,
    temporary_path: Path,
    attempts: int,
) -> str:
    from huggingface_hub import get_token

    token = get_token()
    if not token:
        raise RuntimeError("authenticated Hugging Face credential is required for full fragment extraction")
    url = (
        "https://huggingface.co/datasets/slaf-project/Parse-10M/resolve/"
        f"{PINNED_REVISION}/expression.lance/data/{quote(source_file)}"
    )
    temporary_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with requests.get(
                url,
                headers={"Authorization": f"Bearer {token}", "User-Agent": "BioNexus-Parse-extraction/1"},
                stream=True,
                timeout=(30, 300),
            ) as response:
                response.raise_for_status()
                with temporary_path.open("wb") as handle:
                    for block in response.iter_content(chunk_size=4 * 1024 * 1024):
                        if block:
                            handle.write(block)
            observed_size = temporary_path.stat().st_size
            if observed_size != expected_size:
                raise RuntimeError(
                    f"fragment byte size mismatch: expected {expected_size}, observed {observed_size}"
                )
            return _sha256(temporary_path)
        except Exception as exc:
            last_error = exc
            temporary_path.unlink(missing_ok=True)
            if attempt == attempts:
                break
    assert last_error is not None
    raise RuntimeError(f"fragment download failed after {attempts} attempts: {source_file}") from last_error


def _process_local_fragment(
    path: Path,
    *,
    sample_by_cell_id: np.ndarray,
    gene_lookup: np.ndarray,
    n_samples: int,
    n_genes: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    from lance.file import LanceFileReader

    target_cell_parts: list[np.ndarray] = []
    observed_min: int | None = None
    observed_max: int | None = None
    matrix = np.zeros((n_samples, n_genes), dtype=np.uint64)
    reader = LanceFileReader(str(path), columns=["cell_integer_id", "gene_integer_id", "value"])
    for batch in reader.read_all(batch_size=1_000_000, batch_readahead=2).to_batches():
        cell_ids = batch.column("cell_integer_id").to_numpy(zero_copy_only=False).astype(np.int64)
        if len(cell_ids):
            observed_min = int(cell_ids[0]) if observed_min is None else min(observed_min, int(cell_ids.min()))
            observed_max = int(cell_ids[-1]) if observed_max is None else max(observed_max, int(cell_ids.max()))
        valid = (cell_ids >= 0) & (cell_ids < len(sample_by_cell_id))
        samples = np.full(len(cell_ids), -1, dtype=np.int64)
        samples[valid] = sample_by_cell_id[cell_ids[valid]]
        keep = samples >= 0
        if np.any(keep):
            target_cell_ids = cell_ids[keep]
            target_cell_parts.append(target_cell_ids)
            integer_genes = batch.column("gene_integer_id").to_numpy(zero_copy_only=False)[keep].astype(np.int64)
            if np.any(integer_genes < 0) or np.any(integer_genes >= len(gene_lookup)):
                raise RuntimeError("unknown gene_integer_id outside pinned gene dictionary")
            gene_positions = gene_lookup[integer_genes]
            if np.any(gene_positions < 0):
                raise RuntimeError("unknown gene_integer_id in pinned expression fragment")
            sample_rows = samples[keep]
            values = batch.column("value").to_numpy(zero_copy_only=False)[keep].astype(np.uint64)
            flat_positions = sample_rows * n_genes + gene_positions
            batch_counts = np.bincount(flat_positions, weights=values, minlength=n_samples * n_genes)
            matrix += batch_counts.reshape(matrix.shape).astype(np.uint64)
    if observed_min is None or observed_max is None:
        raise RuntimeError("empty Lance expression fragment")
    if not target_cell_parts:
        return matrix, np.array([], dtype=np.int64), np.array([], dtype=np.uint64), observed_min, observed_max
    target_cell_ids = np.concatenate(target_cell_parts)
    unique_ids, row_counts = np.unique(target_cell_ids, return_counts=True)
    return matrix, unique_ids.astype(np.int64), row_counts.astype(np.uint64), observed_min, observed_max


def _process_remote_fragment(
    uri: str,
    *,
    sample_by_cell_id: np.ndarray,
    gene_lookup: np.ndarray,
    n_samples: int,
    n_genes: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    """Read the compressed cell-ID column, then only matched gene/value rows."""
    from lance.file import LanceFileReader

    target_row_parts: list[np.ndarray] = []
    target_cell_parts: list[np.ndarray] = []
    offset = 0
    observed_min: int | None = None
    observed_max: int | None = None
    reader = LanceFileReader(uri, columns=["cell_integer_id"])
    for batch in reader.read_all(batch_size=1_000_000, batch_readahead=2).to_batches():
        cell_ids = batch.column("cell_integer_id").to_numpy(zero_copy_only=False).astype(np.int64)
        if len(cell_ids):
            observed_min = int(cell_ids[0]) if observed_min is None else min(observed_min, int(cell_ids.min()))
            observed_max = int(cell_ids[-1]) if observed_max is None else max(observed_max, int(cell_ids.max()))
        valid = (cell_ids >= 0) & (cell_ids < len(sample_by_cell_id))
        samples = np.full(len(cell_ids), -1, dtype=np.int64)
        samples[valid] = sample_by_cell_id[cell_ids[valid]]
        keep = samples >= 0
        if np.any(keep):
            target_row_parts.append(np.flatnonzero(keep).astype(np.int64) + offset)
            target_cell_parts.append(cell_ids[keep])
        offset += len(cell_ids)
    if observed_min is None or observed_max is None:
        raise RuntimeError("empty remote Lance expression fragment")
    matrix = np.zeros((n_samples, n_genes), dtype=np.uint64)
    if not target_row_parts:
        return matrix, np.array([], dtype=np.int64), np.array([], dtype=np.uint64), observed_min, observed_max
    row_indices = np.concatenate(target_row_parts)
    target_cell_ids = np.concatenate(target_cell_parts)
    reader = LanceFileReader(uri, columns=["gene_integer_id", "value"])
    cursor = 0
    for batch in reader.take_rows(row_indices, batch_size=262_144, batch_readahead=2).to_batches():
        length = batch.num_rows
        batch_cell_ids = target_cell_ids[cursor : cursor + length]
        cursor += length
        integer_genes = batch.column("gene_integer_id").to_numpy(zero_copy_only=False).astype(np.int64)
        if np.any(integer_genes < 0) or np.any(integer_genes >= len(gene_lookup)):
            raise RuntimeError("unknown gene_integer_id outside pinned gene dictionary")
        gene_positions = gene_lookup[integer_genes]
        if np.any(gene_positions < 0):
            raise RuntimeError("unknown gene_integer_id in pinned expression fragment")
        sample_rows = sample_by_cell_id[batch_cell_ids].astype(np.int64)
        values = batch.column("value").to_numpy(zero_copy_only=False).astype(np.uint64)
        flat_positions = sample_rows * n_genes + gene_positions
        batch_counts = np.bincount(flat_positions, weights=values, minlength=n_samples * n_genes)
        matrix += batch_counts.reshape(matrix.shape).astype(np.uint64)
    if cursor != len(row_indices):
        raise RuntimeError("remote Lance take_rows returned an incomplete target row set")
    unique_ids, row_counts = np.unique(target_cell_ids, return_counts=True)
    return matrix, unique_ids.astype(np.int64), row_counts.astype(np.uint64), observed_min, observed_max


def process_shard(
    output_dir: Path,
    *,
    shard_index: int,
    shard_count: int,
    attempts: int,
    max_fragments: int | None,
    transport: str,
) -> dict[str, Any]:
    import lance

    if shard_count < 1 or not 0 <= shard_index < shard_count:
        raise ValueError("shard_index must be in [0, shard_count)")
    _ensure_hf_auth()
    _assert_pinned_revision(attempts=attempts, boundary=f"before expression shard {shard_index}")
    gene_ids, gene_lookup = _load_genes(attempts=attempts)
    sample_keys, all_ids, all_samples, _all_gene_counts = _global_population(output_dir)
    sample_by_cell_id = np.full(int(all_ids.max()) + 1, -1, dtype=np.int16)
    sample_by_cell_id[all_ids] = all_samples.astype(np.int16)
    dataset = lance.dataset(f"{BASE_URI}/expression.lance")
    fragments = dataset.get_fragments()
    owned = [fragment for fragment in fragments if fragment.fragment_id % shard_count == shard_index]
    if max_fragments is not None:
        owned = owned[:max_fragments]
    resumed = 0
    written = 0
    records = 0
    temp_root = output_dir / "checkpoints" / "fragment_downloads" / f"shard_{shard_index}"
    for position, fragment in enumerate(owned, start=1):
        metadata = fragment.metadata
        if len(metadata.files) != 1:
            raise RuntimeError(f"fragment {fragment.fragment_id} has an unsupported multi-file layout")
        data_file = metadata.files[0]
        source_file = str(data_file.path)
        source_size = int(data_file.file_size_bytes)
        physical_rows = int(metadata.physical_rows)
        npz_path, manifest_path = _fragment_paths(output_dir, fragment.fragment_id)
        if _valid_fragment_checkpoint(
            npz_path,
            manifest_path,
            fragment_id=fragment.fragment_id,
            source_file=source_file,
            source_file_size=source_size,
            physical_rows=physical_rows,
            n_samples=len(sample_keys),
            n_genes=len(gene_ids),
        ):
            manifest = _load_json(manifest_path)
            resumed += 1
            records += int(manifest["expression_records_aggregated"])
            print(
                f"RESUME shard={shard_index}/{shard_count} fragment={fragment.fragment_id} "
                f"position={position}/{len(owned)} records={manifest['expression_records_aggregated']}",
                flush=True,
            )
            continue
        if transport == "download":
            temporary_fragment = temp_root / f"fragment_{fragment.fragment_id:05d}.lance.incomplete"
            source_sha256 = _download_fragment(
                source_file=source_file,
                expected_size=source_size,
                temporary_path=temporary_fragment,
                attempts=attempts,
            )
            try:
                counts, cell_ids, row_counts, cell_min, cell_max = _process_local_fragment(
                    temporary_fragment,
                    sample_by_cell_id=sample_by_cell_id,
                    gene_lookup=gene_lookup,
                    n_samples=len(sample_keys),
                    n_genes=len(gene_ids),
                )
            finally:
                temporary_fragment.unlink(missing_ok=True)
        elif transport == "remote-columns":
            source_sha256 = None
            uri = f"hf://datasets/slaf-project/Parse-10M/expression.lance/data/{source_file}"
            counts, cell_ids, row_counts, cell_min, cell_max = _process_remote_fragment(
                uri,
                sample_by_cell_id=sample_by_cell_id,
                gene_lookup=gene_lookup,
                n_samples=len(sample_keys),
                n_genes=len(gene_ids),
            )
        else:
            raise ValueError(f"unsupported transport: {transport}")
        if int(row_counts.sum()) > physical_rows:
            raise RuntimeError(f"fragment {fragment.fragment_id} target row count exceeds physical rows")
        npz_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_npz = npz_path.with_name(f"{npz_path.name}.incomplete")
        with temporary_npz.open("wb") as handle:
            np.savez_compressed(
                handle,
                counts=counts,
                cell_integer_ids=cell_ids,
                expression_row_counts=row_counts,
            )
        temporary_npz.replace(npz_path)
        fragment_records = int(row_counts.sum())
        _atomic_json(
            manifest_path,
            {
                "schema_version": "bionexus.parse-expression-fragment-checkpoint.v1",
                "source_revision": PINNED_REVISION,
                "fragment_id": int(fragment.fragment_id),
                "source_file": source_file,
                "source_file_size_bytes": source_size,
                "source_file_sha256": source_sha256,
                "retrieval_method": transport,
                "physical_rows": physical_rows,
                "fragment_cell_integer_id_min": cell_min,
                "fragment_cell_integer_id_max": cell_max,
                "n_target_cells_present": int(len(cell_ids)),
                "target_cell_ids_sha256": _array_sha256(cell_ids),
                "expression_records_aggregated": fragment_records,
                "npz_sha256": _sha256(npz_path),
                "completed_at": _utc_now(),
            },
        )
        written += 1
        records += fragment_records
        print(
            f"WRITE shard={shard_index}/{shard_count} fragment={fragment.fragment_id} "
            f"position={position}/{len(owned)} source_mb={source_size / 1_000_000:.1f} "
            f"target_cells={len(cell_ids)} records={fragment_records}",
            flush=True,
        )
    _assert_pinned_revision(attempts=attempts, boundary=f"after expression shard {shard_index}")
    manifest = {
        "schema_version": "bionexus.parse-expression-fragment-shard.v1",
        "study_id": "BN-PB-IV-003",
        "cohort_id": "C02",
        "source_revision": PINNED_REVISION,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "source_fragment_count": len(fragments),
        "owned_fragments": len(owned),
        "resumed_checkpoints": resumed,
        "written_checkpoints": written,
        "expression_records_aggregated": records,
        "complete_shard": max_fragments is None,
        "transport": transport,
        "completed_at": _utc_now(),
    }
    _atomic_json(output_dir / "checkpoints" / f"EXPRESSION_SHARD_{shard_index}_OF_{shard_count}.json", manifest)
    return manifest


def finalize(output_dir: Path, *, attempts: int) -> dict[str, Any]:
    import lance

    _ensure_hf_auth()
    _assert_pinned_revision(attempts=attempts, boundary="before fragment-checkpoint finalization")
    gene_ids, _gene_lookup = _load_genes(attempts=attempts)
    sample_keys, all_ids, all_samples, all_gene_counts = _global_population(output_dir)
    dataset = lance.dataset(f"{BASE_URI}/expression.lance")
    fragments = dataset.get_fragments()
    counts = np.zeros((len(sample_keys), len(gene_ids)), dtype=np.uint64)
    observed_row_counts = np.zeros(int(all_ids.max()) + 1, dtype=np.uint64)
    checkpoint_hashes: list[str] = []
    total_records = 0
    previous_cell_max = -1
    for fragment in fragments:
        metadata = fragment.metadata
        data_file = metadata.files[0]
        npz_path, manifest_path = _fragment_paths(output_dir, fragment.fragment_id)
        if not _valid_fragment_checkpoint(
            npz_path,
            manifest_path,
            fragment_id=fragment.fragment_id,
            source_file=str(data_file.path),
            source_file_size=int(data_file.file_size_bytes),
            physical_rows=int(metadata.physical_rows),
            n_samples=len(sample_keys),
            n_genes=len(gene_ids),
        ):
            raise RuntimeError(f"missing or invalid expression fragment checkpoint: {fragment.fragment_id}")
        manifest = _load_json(manifest_path)
        cell_min = int(manifest["fragment_cell_integer_id_min"])
        cell_max = int(manifest["fragment_cell_integer_id_max"])
        if cell_min < previous_cell_max:
            raise RuntimeError(f"expression fragment cell-ID ranges are not monotone at fragment {fragment.fragment_id}")
        previous_cell_max = cell_max
        with np.load(npz_path, allow_pickle=False) as payload:
            counts += payload["counts"].astype(np.uint64)
            cell_ids = payload["cell_integer_ids"].astype(np.int64)
            row_counts = payload["expression_row_counts"].astype(np.uint64)
        np.add.at(observed_row_counts, cell_ids, row_counts)
        total_records += int(row_counts.sum())
        checkpoint_hashes.append(str(manifest["npz_sha256"]))

    actual = observed_row_counts[all_ids]
    missing_cells = all_ids[(actual == 0) & (all_gene_counts > 0)]
    mismatch_mask = actual != all_gene_counts.astype(np.uint64)
    mismatches = all_ids[mismatch_mask]
    if len(missing_cells):
        raise RuntimeError(f"target expression cells are missing; first IDs: {missing_cells[:10].tolist()}")
    # Parse's released cells.gene_count is not a byte-for-byte row count for
    # every expression cell (the pinned source itself has small positive
    # discrepancies).  Do not impute or silently discard them: the source
    # expression rows are the aggregation input, while the mismatch is kept as
    # an explicit audit field.  Missing target cells remain a hard failure.
    mismatch_deltas = all_gene_counts.astype(np.int64) - actual.astype(np.int64)
    mismatch_delta_values = mismatch_deltas[mismatch_mask]
    mismatch_histogram: dict[str, int] = {}
    if len(mismatch_delta_values):
        delta_values, delta_counts = np.unique(mismatch_delta_values, return_counts=True)
        mismatch_histogram = {str(int(delta)): int(count) for delta, count in zip(delta_values, delta_counts, strict=True)}
    if not np.any(counts):
        raise RuntimeError("final pseudobulk matrix is empty")
    if int(counts.max()) > np.iinfo(np.uint32).max:
        raise RuntimeError(f"pseudobulk count exceeds uint32: {int(counts.max())}")

    pair_counts = {
        f"{donor}|{cytokine}": int(np.count_nonzero(all_samples == sample_index))
        for sample_index, (donor, cytokine) in enumerate(sample_keys)
    }
    obs = pd.DataFrame(
        [
            {
                "sample_id": f"Parse10M__{donor}__{cytokine}",
                "donor": donor,
                "cytokine": cytokine,
                "n_cells": pair_counts[f"{donor}|{cytokine}"],
            }
            for donor, cytokine in sample_keys
        ]
    ).set_index("sample_id")
    matrix = sparse.csr_matrix(counts.astype(np.uint32))
    adata = ad.AnnData(X=matrix, obs=obs, var=pd.DataFrame(index=pd.Index(gene_ids, name="gene")))
    adata.layers["counts"] = matrix.copy()
    adata.uns["bionexus_extraction"] = {
        "schema_version": "bionexus.parse-natural-extraction.v2",
        "aggregation_level": "donor_condition_pseudobulk",
        "source_revision": PINNED_REVISION,
        "eligible_cytokines": list(ELIGIBLE_CYTOKINES),
        "n_source_cells": EXPECTED_TOTAL_CELLS,
        "sampling": "all released eligible cells; no balancing or subsampling",
        "checkpoint_contract": "donor-condition metadata plus immutable expression-file fragments",
        "data_gate_status": "PASS_WITH_RETAINED_SOURCE_METADATA_COUNT_DISCREPANCIES",
        "metadata_gene_count_mismatch_policy": "retain_source_discrepancy; do_not_impute_or_balance",
    }
    output_path = output_dir / "parse_ifnb_pbs_pseudobulk.h5ad"
    temporary = output_path.with_name(f"{output_path.name}.incomplete")
    adata.write_h5ad(temporary, compression="gzip")
    _assert_pinned_revision(attempts=attempts, boundary="after fragment-checkpoint finalization")
    temporary.replace(output_path)
    manifest = {
        "schema_version": "bionexus.parse-natural-extraction.v2",
        "study_id": "BN-PB-IV-003",
        "cohort_id": "C02",
        "source_revision": PINNED_REVISION,
        "source_uri": BASE_URI,
        "sampling": "complete released IFN-beta/PBS eligible population",
        "balancing_or_stratified_sampling": False,
        "n_cells": EXPECTED_TOTAL_CELLS,
        "n_genes": len(gene_ids),
        "n_donors": len(EXPECTED_DONORS),
        "n_pseudobulk_samples": len(sample_keys),
        "source_expression_fragments": len(fragments),
        "data_gate_status": "PASS_WITH_RETAINED_SOURCE_METADATA_COUNT_DISCREPANCIES",
        "metadata_gene_count_mismatch_policy": "retain_source_discrepancy; do_not_impute_or_balance",
        "donor_condition_cell_counts": pair_counts,
        "expression_records_aggregated": total_records,
        "metadata_gene_count_sum": int(all_gene_counts.sum()),
        "per_cell_expression_record_mismatches": int(len(mismatches)),
        "per_cell_expression_record_mismatch_total_delta": int(mismatch_delta_values.sum()),
        "per_cell_expression_record_mismatch_histogram": mismatch_histogram,
        "per_cell_expression_record_mismatch_first_ids": mismatches[:20].astype(int).tolist(),
        "cell_integer_ids_sha256": _array_sha256(all_ids),
        "ordered_expression_checkpoint_hashes_sha256": hashlib.sha256(
            "".join(checkpoint_hashes).encode()
        ).hexdigest(),
        "output_path": str(output_path.relative_to(REPO_ROOT).as_posix()),
        "output_sha256": _sha256(output_path),
        "completed_at": _utc_now(),
    }
    _atomic_json(output_dir / "EXTRACTION_MANIFEST.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stage", choices=("expression", "finalize"), default="expression")
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--max-fragments", type=int)
    parser.add_argument("--transport", choices=("remote-columns", "download"), default="remote-columns")
    args = parser.parse_args()
    if args.stage == "expression":
        result = process_shard(
            args.output_dir,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            attempts=args.attempts,
            max_fragments=args.max_fragments,
            transport=args.transport,
        )
    else:
        result = finalize(args.output_dir, attempts=args.attempts)
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
