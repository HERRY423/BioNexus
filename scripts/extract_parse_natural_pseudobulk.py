#!/usr/bin/env python3
"""Resume-safe full Parse-10M IFN-beta/PBS pseudobulk extraction.

Remote reads are recoverable at donor-condition metadata and bounded
cell-integer-ID expression checkpoints. Finalization requires exact coverage
of every eligible cell and every expected non-zero expression record. No
balancing, subsampling, or outcome-dependent filtering is performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypeVar

import anndata as ad
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from scipy import sparse

REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_LANCE_RUNTIME = REPO_ROOT / "runtime_lance"
if LOCAL_LANCE_RUNTIME.is_dir():
    sys.path.insert(0, str(LOCAL_LANCE_RUNTIME))

PINNED_REVISION = "93001c6a5b9db71ebe4237025c2a5c540e1d3674"
BASE_URI = "hf://datasets/slaf-project/Parse-10M"
ELIGIBLE_CYTOKINES = ("IFN-beta", "PBS")
EXPECTED_DONORS = tuple(f"Donor{index}" for index in range(1, 13))
EXPECTED_TOTAL_CELLS = 725_031
METADATA_COLUMNS = ("cell_integer_id", "cell_id", "donor", "cytokine", "gene_count")
T = TypeVar("T")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_hf_auth() -> None:
    """Pass an existing cached HF credential to Lance without logging it."""
    if os.environ.get("HF_TOKEN"):
        return
    from huggingface_hub import get_token

    token = get_token()
    if token:
        os.environ["HF_TOKEN"] = token


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _array_sha256(values: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(values, dtype="<i8").tobytes(order="C")).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.incomplete")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _retry(operation: Callable[[], T], *, attempts: int, label: str) -> T:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:  # remote backends expose several exception types
            last_error = exc
            if attempt == attempts:
                break
            delay = min(30, 2 ** (attempt - 1))
            print(
                f"RETRY {label} attempt={attempt}/{attempts} delay_seconds={delay} "
                f"error={type(exc).__name__}: {exc}",
                flush=True,
            )
            time.sleep(delay)
    assert last_error is not None
    raise RuntimeError(f"{label} failed after {attempts} attempts") from last_error


def _remote_revision() -> str:
    from huggingface_hub import HfApi

    return str(HfApi().dataset_info("slaf-project/Parse-10M").sha)


def _assert_pinned_revision(*, attempts: int, boundary: str) -> str:
    revision = _retry(_remote_revision, attempts=attempts, label=f"source revision {boundary}")
    if revision != PINNED_REVISION:
        raise RuntimeError(
            f"Parse-10M main revision drifted {boundary}: expected {PINNED_REVISION}, observed {revision}"
        )
    return revision


def _pair_slug(donor: str, cytokine: str) -> str:
    return f"{donor}__{cytokine.replace('-', '_')}"


def _pair_filter(donor: str, cytokine: str) -> str:
    if donor not in EXPECTED_DONORS or cytokine not in ELIGIBLE_CYTOKINES:
        raise ValueError("donor or cytokine is outside the locked Parse population")
    return f"donor = '{donor}' AND cytokine = '{cytokine}'"


def bounded_cell_id_chunks(cell_ids: np.ndarray, *, max_cells: int, max_span: int) -> list[np.ndarray]:
    """Split sorted unique IDs by both selected-cell count and numeric span."""
    if max_cells < 1 or max_span < 1:
        raise ValueError("max_cells and max_span must be positive")
    ordered = np.unique(np.asarray(cell_ids, dtype=np.int64))
    chunks: list[np.ndarray] = []
    cursor = 0
    while cursor < ordered.size:
        count_stop = min(cursor + max_cells, ordered.size)
        span_stop = int(np.searchsorted(ordered, ordered[cursor] + max_span, side="right"))
        stop = max(cursor + 1, min(count_stop, span_stop))
        chunks.append(ordered[cursor:stop])
        cursor = stop
    return chunks


def bounded_exact_range_batches(
    cell_ids: np.ndarray,
    *,
    max_cells: int,
    max_ranges: int,
    max_range_span: int,
) -> list[tuple[np.ndarray, list[tuple[int, int]]]]:
    """Pack exact contiguous ID ranges without scanning the gaps between them."""
    if max_cells < 1 or max_ranges < 1 or max_range_span < 1:
        raise ValueError("range-batch limits must be positive")
    ordered = np.unique(np.asarray(cell_ids, dtype=np.int64))
    if ordered.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(ordered) != 1) + 1
    runs = np.split(ordered, breaks)
    bounded_runs: list[np.ndarray] = []
    for run in runs:
        cursor = 0
        while cursor < len(run):
            stop = min(cursor + max_cells, cursor + max_range_span, len(run))
            bounded_runs.append(run[cursor:stop])
            cursor = stop
    batches: list[tuple[np.ndarray, list[tuple[int, int]]]] = []
    current: list[np.ndarray] = []
    current_cells = 0
    for run in bounded_runs:
        if current and (len(current) >= max_ranges or current_cells + len(run) > max_cells):
            ids = np.concatenate(current)
            batches.append((ids, [(int(part[0]), int(part[-1])) for part in current]))
            current = []
            current_cells = 0
        current.append(run)
        current_cells += len(run)
    if current:
        ids = np.concatenate(current)
        batches.append((ids, [(int(part[0]), int(part[-1])) for part in current]))
    return batches


def _metadata_paths(output_dir: Path, donor: str, cytokine: str) -> tuple[Path, Path]:
    root = output_dir / "checkpoints" / "metadata"
    slug = _pair_slug(donor, cytokine)
    return root / f"{slug}.parquet", root / f"{slug}.manifest.json"


def _valid_metadata_checkpoint(
    parquet_path: Path,
    manifest_path: Path,
    *,
    donor: str,
    cytokine: str,
    expected_rows: int,
) -> bool:
    if not parquet_path.is_file() or not manifest_path.is_file():
        return False
    try:
        manifest = _load_json(manifest_path)
        expected = {
            "schema_version": "bionexus.parse-metadata-checkpoint.v1",
            "source_revision": PINNED_REVISION,
            "donor": donor,
            "cytokine": cytokine,
            "n_cells": expected_rows,
            "parquet_sha256": _sha256(parquet_path),
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            return False
        metadata = pq.read_metadata(parquet_path)
        return metadata.num_rows == expected_rows and tuple(metadata.schema.names) == METADATA_COLUMNS
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False


def checkpoint_metadata(output_dir: Path, *, attempts: int) -> dict[str, Any]:
    import lance

    _assert_pinned_revision(attempts=attempts, boundary="before metadata checkpointing")
    pair_counts: dict[str, int] = {}
    resumed = 0
    written = 0
    for donor in EXPECTED_DONORS:
        for cytokine in ELIGIBLE_CYTOKINES:
            predicate = _pair_filter(donor, cytokine)

            def count_pair() -> int:
                return int(lance.dataset(f"{BASE_URI}/cells.lance").count_rows(predicate))

            expected_rows = _retry(count_pair, attempts=attempts, label=f"count {donor}/{cytokine}")
            if expected_rows < 10:
                raise RuntimeError(f"paired donor-condition gate failed for {donor}/{cytokine}: {expected_rows}")
            pair_counts[f"{donor}|{cytokine}"] = expected_rows
            parquet_path, manifest_path = _metadata_paths(output_dir, donor, cytokine)
            if _valid_metadata_checkpoint(
                parquet_path,
                manifest_path,
                donor=donor,
                cytokine=cytokine,
                expected_rows=expected_rows,
            ):
                resumed += 1
                print(f"RESUME metadata {donor}/{cytokine} cells={expected_rows}", flush=True)
                continue

            def read_pair() -> pa.Table:
                dataset = lance.dataset(f"{BASE_URI}/cells.lance")
                return dataset.scanner(columns=list(METADATA_COLUMNS), filter=predicate).to_table()

            table = _retry(read_pair, attempts=attempts, label=f"metadata {donor}/{cytokine}")
            if table.num_rows != expected_rows:
                raise RuntimeError(
                    f"metadata row mismatch for {donor}/{cytokine}: expected {expected_rows}, observed {table.num_rows}"
                )
            frame = table.to_pandas().sort_values("cell_integer_id", kind="stable")
            if set(frame["donor"].astype(str)) != {donor} or set(frame["cytokine"].astype(str)) != {cytokine}:
                raise RuntimeError(f"metadata label contamination for {donor}/{cytokine}")
            ids = frame["cell_integer_id"].to_numpy(dtype=np.int64)
            if len(np.unique(ids)) != expected_rows:
                raise RuntimeError(f"duplicate cell_integer_id in {donor}/{cytokine}")
            gene_counts = pd.to_numeric(frame["gene_count"], errors="coerce").to_numpy()
            if np.any(~np.isfinite(gene_counts)) or np.any(gene_counts < 0):
                raise RuntimeError(f"invalid gene_count in {donor}/{cytokine}")
            parquet_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = parquet_path.with_name(f"{parquet_path.name}.incomplete")
            pq.write_table(pa.Table.from_pandas(frame, preserve_index=False), temporary, compression="zstd")
            temporary.replace(parquet_path)
            _atomic_json(
                manifest_path,
                {
                    "schema_version": "bionexus.parse-metadata-checkpoint.v1",
                    "source_revision": PINNED_REVISION,
                    "donor": donor,
                    "cytokine": cytokine,
                    "n_cells": expected_rows,
                    "cell_integer_id_min": int(ids.min()),
                    "cell_integer_id_max": int(ids.max()),
                    "cell_integer_ids_sha256": _array_sha256(ids),
                    "expected_expression_records": int(gene_counts.astype(np.int64).sum()),
                    "parquet_sha256": _sha256(parquet_path),
                    "completed_at": _utc_now(),
                },
            )
            written += 1
            print(f"WRITE metadata {donor}/{cytokine} cells={expected_rows}", flush=True)

    total_cells = sum(pair_counts.values())
    if total_cells != EXPECTED_TOTAL_CELLS:
        raise RuntimeError(f"eligible population drift: expected {EXPECTED_TOTAL_CELLS}, observed {total_cells}")
    _assert_pinned_revision(attempts=attempts, boundary="after metadata checkpointing")
    manifest = {
        "schema_version": "bionexus.parse-metadata-stage.v1",
        "study_id": "BN-PB-IV-003",
        "cohort_id": "C02",
        "source_revision": PINNED_REVISION,
        "n_cells": total_cells,
        "n_donors": len(EXPECTED_DONORS),
        "n_conditions": len(ELIGIBLE_CYTOKINES),
        "donor_condition_cell_counts": pair_counts,
        "resumed_checkpoints": resumed,
        "written_checkpoints": written,
        "completed_at": _utc_now(),
    }
    _atomic_json(output_dir / "checkpoints" / "METADATA_STAGE.json", manifest)
    return manifest


def _load_genes(*, attempts: int) -> tuple[np.ndarray, np.ndarray]:
    import lance

    def read_genes() -> pd.DataFrame:
        dataset = lance.dataset(f"{BASE_URI}/genes.lance")
        return dataset.scanner(columns=["gene_integer_id", "gene_id"]).to_table().to_pandas()

    genes = _retry(read_genes, attempts=attempts, label="gene dictionary")
    genes = genes.sort_values("gene_integer_id", kind="stable")
    integer_ids = genes["gene_integer_id"].to_numpy(dtype=np.int64)
    if len(np.unique(integer_ids)) != len(integer_ids):
        raise RuntimeError("duplicate gene_integer_id in pinned source")
    if integer_ids.min() < 0 or integer_ids.max() > len(integer_ids) * 10:
        raise RuntimeError("gene_integer_id range is invalid or unexpectedly sparse")
    position_by_integer_id = np.full(int(integer_ids.max()) + 1, -1, dtype=np.int64)
    position_by_integer_id[integer_ids] = np.arange(len(integer_ids), dtype=np.int64)
    return genes["gene_id"].astype(str).to_numpy(), position_by_integer_id


def _expression_paths(output_dir: Path, donor: str, cytokine: str, index: int) -> tuple[Path, Path]:
    root = output_dir / "checkpoints" / "expression" / _pair_slug(donor, cytokine)
    stem = f"chunk_{index:05d}"
    return root / f"{stem}.npz", root / f"{stem}.manifest.json"


def _valid_expression_checkpoint(
    npz_path: Path,
    manifest_path: Path,
    *,
    donor: str,
    cytokine: str,
    selected_ids: np.ndarray,
    expected_records: int,
    n_genes: int,
) -> bool:
    if not npz_path.is_file() or not manifest_path.is_file():
        return False
    try:
        manifest = _load_json(manifest_path)
        expected = {
            "schema_version": "bionexus.parse-expression-checkpoint.v1",
            "source_revision": PINNED_REVISION,
            "donor": donor,
            "cytokine": cytokine,
            "n_selected_cells": int(len(selected_ids)),
            "selected_cell_ids_sha256": _array_sha256(selected_ids),
            "expected_expression_records": expected_records,
            "expression_records_aggregated": expected_records,
            "npz_sha256": _sha256(npz_path),
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            return False
        with np.load(npz_path, allow_pickle=False) as payload:
            counts = payload["counts"]
            stored_ids = payload["cell_integer_ids"]
        return (
            counts.shape == (n_genes,)
            and counts.dtype == np.uint64
            and np.array_equal(stored_ids.astype(np.int64), selected_ids.astype(np.int64))
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False


def checkpoint_expression(
    output_dir: Path,
    *,
    max_cells_per_range: int,
    max_cell_id_span: int,
    attempts: int,
) -> dict[str, Any]:
    import lance

    metadata_stage_path = output_dir / "checkpoints" / "METADATA_STAGE.json"
    if not metadata_stage_path.is_file() or int(_load_json(metadata_stage_path).get("n_cells", -1)) != EXPECTED_TOTAL_CELLS:
        raise RuntimeError("complete metadata stage is required before expression checkpointing")
    _assert_pinned_revision(attempts=attempts, boundary="before expression checkpointing")
    gene_ids, gene_lookup = _load_genes(attempts=attempts)
    resumed = 0
    written = 0
    total_records = 0
    total_chunks = 0
    pair_summary: dict[str, Any] = {}

    for donor in EXPECTED_DONORS:
        for cytokine in ELIGIBLE_CYTOKINES:
            metadata_path, metadata_manifest_path = _metadata_paths(output_dir, donor, cytokine)
            metadata_manifest = _load_json(metadata_manifest_path)
            expected_rows = int(metadata_manifest["n_cells"])
            if not _valid_metadata_checkpoint(
                metadata_path,
                metadata_manifest_path,
                donor=donor,
                cytokine=cytokine,
                expected_rows=expected_rows,
            ):
                raise RuntimeError(f"invalid metadata checkpoint for {donor}/{cytokine}")
            frame = pq.read_table(metadata_path, columns=["cell_integer_id", "gene_count"]).to_pandas()
            frame = frame.sort_values("cell_integer_id", kind="stable")
            all_ids = frame["cell_integer_id"].to_numpy(dtype=np.int64)
            gene_counts = frame["gene_count"].astype(np.int64).to_numpy()
            gene_count_by_id = dict(zip(all_ids.tolist(), gene_counts.tolist(), strict=True))
            chunks = bounded_cell_id_chunks(
                all_ids,
                max_cells=max_cells_per_range,
                max_span=max_cell_id_span,
            )
            pair_records = 0
            pair_hashes: list[str] = []
            for chunk_index, selected_ids in enumerate(chunks):
                total_chunks += 1
                expected_records = int(sum(gene_count_by_id[int(cell_id)] for cell_id in selected_ids))
                npz_path, manifest_path = _expression_paths(output_dir, donor, cytokine, chunk_index)
                if _valid_expression_checkpoint(
                    npz_path,
                    manifest_path,
                    donor=donor,
                    cytokine=cytokine,
                    selected_ids=selected_ids,
                    expected_records=expected_records,
                    n_genes=len(gene_ids),
                ):
                    manifest = _load_json(manifest_path)
                    resumed += 1
                    pair_records += expected_records
                    pair_hashes.append(str(manifest["npz_sha256"]))
                    print(
                        f"RESUME expression {donor}/{cytokine} chunk={chunk_index + 1}/{len(chunks)} "
                        f"cells={len(selected_ids)} records={expected_records}",
                        flush=True,
                    )
                    continue

                start = int(selected_ids[0])
                end = int(selected_ids[-1])
                def read_expression() -> tuple[np.ndarray, int]:
                    dataset = lance.dataset(f"{BASE_URI}/expression.lance")
                    scanner = dataset.scanner(
                        columns=["cell_integer_id", "gene_integer_id", "value"],
                        filter=f"cell_integer_id >= {start} AND cell_integer_id <= {end}",
                        batch_size=262_144,
                    )
                    vector = np.zeros(len(gene_ids), dtype=np.uint64)
                    records = 0
                    for batch in scanner.to_batches():
                        cell_values = batch.column("cell_integer_id").to_numpy(zero_copy_only=False).astype(np.int64)
                        keep = np.isin(cell_values, selected_ids, assume_unique=False)
                        if not np.any(keep):
                            continue
                        integer_genes = batch.column("gene_integer_id").to_numpy(zero_copy_only=False)[keep]
                        integer_genes = integer_genes.astype(np.int64)
                        if np.any(integer_genes < 0) or np.any(integer_genes >= len(gene_lookup)):
                            raise RuntimeError("unknown gene_integer_id outside the pinned dictionary")
                        positions = gene_lookup[integer_genes]
                        if np.any(positions < 0):
                            raise RuntimeError("unknown gene_integer_id in expression data")
                        values = batch.column("value").to_numpy(zero_copy_only=False)[keep].astype(np.uint64)
                        np.add.at(vector, positions, values)
                        records += int(np.count_nonzero(keep))
                    return vector, records

                counts, observed_records = _retry(
                    read_expression,
                    attempts=attempts,
                    label=f"expression {donor}/{cytokine} chunk {chunk_index + 1}/{len(chunks)} [{start},{end}]",
                )
                if observed_records != expected_records:
                    raise RuntimeError(
                        f"expression coverage mismatch {donor}/{cytokine} chunk {chunk_index}: "
                        f"expected {expected_records}, observed {observed_records}"
                    )
                npz_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = npz_path.with_name(f"{npz_path.name}.incomplete")
                with temporary.open("wb") as handle:
                    np.savez_compressed(handle, counts=counts, cell_integer_ids=selected_ids.astype(np.int64))
                temporary.replace(npz_path)
                npz_hash = _sha256(npz_path)
                _atomic_json(
                    manifest_path,
                    {
                        "schema_version": "bionexus.parse-expression-checkpoint.v1",
                        "source_revision": PINNED_REVISION,
                        "donor": donor,
                        "cytokine": cytokine,
                        "chunk_index": chunk_index,
                        "n_selected_cells": int(len(selected_ids)),
                        "cell_integer_id_start": start,
                        "cell_integer_id_end": end,
                        "cell_integer_id_span": end - start + 1,
                        "selected_cell_ids_sha256": _array_sha256(selected_ids),
                        "expected_expression_records": expected_records,
                        "expression_records_aggregated": observed_records,
                        "npz_sha256": npz_hash,
                        "completed_at": _utc_now(),
                    },
                )
                written += 1
                pair_records += observed_records
                pair_hashes.append(npz_hash)
                print(
                    f"WRITE expression {donor}/{cytokine} chunk={chunk_index + 1}/{len(chunks)} "
                    f"ids=[{start},{end}] cells={len(selected_ids)} records={observed_records}",
                    flush=True,
                )

            expected_pair_records = int(gene_counts.sum())
            if pair_records != expected_pair_records:
                raise RuntimeError(
                    f"pair expression coverage mismatch {donor}/{cytokine}: "
                    f"expected {expected_pair_records}, observed {pair_records}"
                )
            total_records += pair_records
            pair_summary[f"{donor}|{cytokine}"] = {
                "n_cells": int(len(all_ids)),
                "n_chunks": len(chunks),
                "expression_records": pair_records,
                "ordered_npz_hashes_sha256": hashlib.sha256("".join(pair_hashes).encode()).hexdigest(),
            }

    _assert_pinned_revision(attempts=attempts, boundary="after expression checkpointing")
    manifest = {
        "schema_version": "bionexus.parse-expression-stage.v1",
        "study_id": "BN-PB-IV-003",
        "cohort_id": "C02",
        "source_revision": PINNED_REVISION,
        "n_cells": EXPECTED_TOTAL_CELLS,
        "n_genes": len(gene_ids),
        "expression_records_aggregated": total_records,
        "max_selected_cells_per_range": max_cells_per_range,
        "max_cell_integer_id_span": max_cell_id_span,
        "n_chunks": total_chunks,
        "resumed_checkpoints": resumed,
        "written_checkpoints": written,
        "donor_condition_summary": pair_summary,
        "completed_at": _utc_now(),
    }
    _atomic_json(output_dir / "checkpoints" / "EXPRESSION_STAGE.json", manifest)
    return manifest


def _global_expression_paths(output_dir: Path, index: int) -> tuple[Path, Path]:
    root = output_dir / "checkpoints" / "expression_global"
    stem = f"range_{index:05d}"
    return root / f"{stem}.npz", root / f"{stem}.manifest.json"


def _valid_global_expression_checkpoint(
    npz_path: Path,
    manifest_path: Path,
    *,
    selected_ids: np.ndarray,
    selected_samples: np.ndarray,
    expected_records: int,
    n_samples: int,
    n_genes: int,
) -> bool:
    if not npz_path.is_file() or not manifest_path.is_file():
        return False
    try:
        manifest = _load_json(manifest_path)
        expected = {
            "schema_version": "bionexus.parse-global-expression-checkpoint.v1",
            "source_revision": PINNED_REVISION,
            "n_selected_cells": int(len(selected_ids)),
            "selected_cell_ids_sha256": _array_sha256(selected_ids),
            "selected_sample_indices_sha256": _array_sha256(selected_samples),
            "expected_expression_records": expected_records,
            "expression_records_aggregated": expected_records,
            "npz_sha256": _sha256(npz_path),
        }
        if any(manifest.get(key) != value for key, value in expected.items()):
            return False
        with np.load(npz_path, allow_pickle=False) as payload:
            counts = payload["counts"]
            stored_ids = payload["cell_integer_ids"]
            stored_samples = payload["sample_indices"]
        return (
            counts.shape == (n_samples, n_genes)
            and counts.dtype == np.uint64
            and np.array_equal(stored_ids.astype(np.int64), selected_ids.astype(np.int64))
            and np.array_equal(stored_samples.astype(np.int64), selected_samples.astype(np.int64))
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return False


def _global_population(output_dir: Path) -> tuple[list[tuple[str, str]], np.ndarray, np.ndarray, np.ndarray]:
    sample_keys = [(donor, cytokine) for donor in EXPECTED_DONORS for cytokine in ELIGIBLE_CYTOKINES]
    id_parts: list[np.ndarray] = []
    sample_parts: list[np.ndarray] = []
    gene_count_parts: list[np.ndarray] = []
    for sample_index, (donor, cytokine) in enumerate(sample_keys):
        metadata_path, manifest_path = _metadata_paths(output_dir, donor, cytokine)
        manifest = _load_json(manifest_path)
        if not _valid_metadata_checkpoint(
            metadata_path,
            manifest_path,
            donor=donor,
            cytokine=cytokine,
            expected_rows=int(manifest["n_cells"]),
        ):
            raise RuntimeError(f"invalid metadata checkpoint for {donor}/{cytokine}")
        frame = pq.read_table(metadata_path, columns=["cell_integer_id", "gene_count"]).to_pandas()
        ids = frame["cell_integer_id"].to_numpy(dtype=np.int64)
        id_parts.append(ids)
        sample_parts.append(np.full(len(ids), sample_index, dtype=np.int64))
        gene_count_parts.append(frame["gene_count"].astype(np.int64).to_numpy())
    ids = np.concatenate(id_parts)
    samples = np.concatenate(sample_parts)
    gene_counts = np.concatenate(gene_count_parts)
    order = np.argsort(ids, kind="stable")
    ids = ids[order]
    samples = samples[order]
    gene_counts = gene_counts[order]
    if len(ids) != EXPECTED_TOTAL_CELLS or len(np.unique(ids)) != EXPECTED_TOTAL_CELLS:
        raise RuntimeError("metadata checkpoints do not contain exactly 725,031 unique cell IDs")
    return sample_keys, ids, samples, gene_counts


def checkpoint_expression_global(
    output_dir: Path,
    *,
    max_cells_per_range: int,
    max_cell_id_span: int,
    max_ranges_per_checkpoint: int,
    attempts: int,
) -> dict[str, Any]:
    import lance

    metadata_stage_path = output_dir / "checkpoints" / "METADATA_STAGE.json"
    if not metadata_stage_path.is_file() or int(_load_json(metadata_stage_path).get("n_cells", -1)) != EXPECTED_TOTAL_CELLS:
        raise RuntimeError("complete metadata stage is required before expression checkpointing")
    _assert_pinned_revision(attempts=attempts, boundary="before expression checkpointing")
    gene_ids, gene_lookup = _load_genes(attempts=attempts)
    sample_keys, all_ids, all_samples, all_gene_counts = _global_population(output_dir)
    chunks = bounded_exact_range_batches(
        all_ids,
        max_cells=max_cells_per_range,
        max_ranges=max_ranges_per_checkpoint,
        max_range_span=max_cell_id_span,
    )
    id_start_to_position = {int(cell_id): index for index, cell_id in enumerate(all_ids)}
    resumed = 0
    written = 0
    total_records = 0
    chunk_hashes: list[str] = []
    for chunk_index, (selected_ids, exact_ranges) in enumerate(chunks):
        start_position = id_start_to_position[int(selected_ids[0])]
        stop_position = start_position + len(selected_ids)
        selected_samples = all_samples[start_position:stop_position]
        selected_gene_counts = all_gene_counts[start_position:stop_position]
        if not np.array_equal(all_ids[start_position:stop_position], selected_ids):
            raise RuntimeError("internal global range indexing error")
        expected_records = int(selected_gene_counts.sum())
        npz_path, manifest_path = _global_expression_paths(output_dir, chunk_index)
        if _valid_global_expression_checkpoint(
            npz_path,
            manifest_path,
            selected_ids=selected_ids,
            selected_samples=selected_samples,
            expected_records=expected_records,
            n_samples=len(sample_keys),
            n_genes=len(gene_ids),
        ):
            manifest = _load_json(manifest_path)
            resumed += 1
            total_records += expected_records
            chunk_hashes.append(str(manifest["npz_sha256"]))
            print(
                f"RESUME expression range={chunk_index + 1}/{len(chunks)} "
                f"cells={len(selected_ids)} records={expected_records}",
                flush=True,
            )
            continue
        predicate = " OR ".join(
            f"(cell_integer_id >= {start} AND cell_integer_id <= {end})" for start, end in exact_ranges
        )

        def read_expression() -> tuple[np.ndarray, int]:
            dataset = lance.dataset(f"{BASE_URI}/expression.lance")
            scanner = dataset.scanner(
                columns=["cell_integer_id", "gene_integer_id", "value"],
                filter=predicate,
                batch_size=262_144,
            )
            matrix = np.zeros((len(sample_keys), len(gene_ids)), dtype=np.uint64)
            records = 0
            for batch in scanner.to_batches():
                cell_values = batch.column("cell_integer_id").to_numpy(zero_copy_only=False).astype(np.int64)
                positions = np.searchsorted(selected_ids, cell_values)
                in_bounds = positions < len(selected_ids)
                keep = np.zeros(len(cell_values), dtype=bool)
                keep[in_bounds] = selected_ids[positions[in_bounds]] == cell_values[in_bounds]
                if not np.any(keep):
                    continue
                integer_genes = batch.column("gene_integer_id").to_numpy(zero_copy_only=False)[keep].astype(np.int64)
                if np.any(integer_genes < 0) or np.any(integer_genes >= len(gene_lookup)):
                    raise RuntimeError("unknown gene_integer_id outside the pinned dictionary")
                gene_positions = gene_lookup[integer_genes]
                if np.any(gene_positions < 0):
                    raise RuntimeError("unknown gene_integer_id in expression data")
                sample_rows = selected_samples[positions[keep]]
                values = batch.column("value").to_numpy(zero_copy_only=False)[keep].astype(np.uint64)
                flat_positions = sample_rows * len(gene_ids) + gene_positions
                batch_counts = np.bincount(
                    flat_positions,
                    weights=values,
                    minlength=len(sample_keys) * len(gene_ids),
                )
                matrix += batch_counts.reshape(matrix.shape).astype(np.uint64)
                records += int(np.count_nonzero(keep))
            return matrix, records

        counts, observed_records = _retry(
            read_expression,
            attempts=attempts,
            label=f"expression checkpoint {chunk_index + 1}/{len(chunks)} ({len(exact_ranges)} exact ranges)",
        )
        if observed_records != expected_records:
            raise RuntimeError(
                f"expression coverage mismatch range {chunk_index}: expected {expected_records}, "
                f"observed {observed_records}"
            )
        npz_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = npz_path.with_name(f"{npz_path.name}.incomplete")
        with temporary.open("wb") as handle:
            np.savez_compressed(
                handle,
                counts=counts,
                cell_integer_ids=selected_ids.astype(np.int64),
                sample_indices=selected_samples.astype(np.int64),
            )
        temporary.replace(npz_path)
        npz_hash = _sha256(npz_path)
        _atomic_json(
            manifest_path,
            {
                "schema_version": "bionexus.parse-global-expression-checkpoint.v1",
                "source_revision": PINNED_REVISION,
                "chunk_index": chunk_index,
                "n_selected_cells": int(len(selected_ids)),
                "cell_integer_id_ranges": [[start, end] for start, end in exact_ranges],
                "n_exact_ranges": len(exact_ranges),
                "selected_cell_ids_sha256": _array_sha256(selected_ids),
                "selected_sample_indices_sha256": _array_sha256(selected_samples),
                "expected_expression_records": expected_records,
                "expression_records_aggregated": observed_records,
                "npz_sha256": npz_hash,
                "completed_at": _utc_now(),
            },
        )
        written += 1
        total_records += observed_records
        chunk_hashes.append(npz_hash)
        print(
            f"WRITE expression checkpoint={chunk_index + 1}/{len(chunks)} exact_ranges={len(exact_ranges)} "
            f"cells={len(selected_ids)} records={observed_records}",
            flush=True,
        )
    if total_records != int(all_gene_counts.sum()):
        raise RuntimeError("global expression record total differs from metadata gene_count total")
    _assert_pinned_revision(attempts=attempts, boundary="after expression checkpointing")
    manifest = {
        "schema_version": "bionexus.parse-expression-stage.v2",
        "study_id": "BN-PB-IV-003",
        "cohort_id": "C02",
        "source_revision": PINNED_REVISION,
        "n_cells": EXPECTED_TOTAL_CELLS,
        "n_genes": len(gene_ids),
        "n_samples": len(sample_keys),
        "expression_records_aggregated": total_records,
        "max_selected_cells_per_range": max_cells_per_range,
        "max_cell_integer_id_span": max_cell_id_span,
        "max_exact_ranges_per_checkpoint": max_ranges_per_checkpoint,
        "n_chunks": len(chunks),
        "resumed_checkpoints": resumed,
        "written_checkpoints": written,
        "ordered_npz_hashes_sha256": hashlib.sha256("".join(chunk_hashes).encode()).hexdigest(),
        "completed_at": _utc_now(),
    }
    _atomic_json(output_dir / "checkpoints" / "EXPRESSION_STAGE.json", manifest)
    return manifest


def finalize_global(output_dir: Path, *, attempts: int) -> dict[str, Any]:
    metadata_stage_path = output_dir / "checkpoints" / "METADATA_STAGE.json"
    expression_stage_path = output_dir / "checkpoints" / "EXPRESSION_STAGE.json"
    if not metadata_stage_path.is_file() or not expression_stage_path.is_file():
        raise RuntimeError("metadata and expression stage manifests are required before finalization")
    metadata_stage = _load_json(metadata_stage_path)
    expression_stage = _load_json(expression_stage_path)
    if int(metadata_stage.get("n_cells", -1)) != EXPECTED_TOTAL_CELLS:
        raise RuntimeError("metadata stage does not cover the locked 725,031-cell population")
    if expression_stage.get("schema_version") != "bionexus.parse-expression-stage.v2":
        raise RuntimeError("global bounded-range expression stage v2 is required")
    _assert_pinned_revision(attempts=attempts, boundary="before finalization")
    gene_ids, _gene_lookup = _load_genes(attempts=attempts)
    sample_keys, all_ids, all_samples, all_gene_counts = _global_population(output_dir)
    chunks = bounded_exact_range_batches(
        all_ids,
        max_cells=int(expression_stage["max_selected_cells_per_range"]),
        max_ranges=int(expression_stage["max_exact_ranges_per_checkpoint"]),
        max_range_span=int(expression_stage["max_cell_integer_id_span"]),
    )
    counts = np.zeros((len(sample_keys), len(gene_ids)), dtype=np.uint64)
    observed_id_parts: list[np.ndarray] = []
    checkpoint_hashes: list[str] = []
    total_records = 0
    cursor = 0
    for chunk_index, (selected_ids, _exact_ranges) in enumerate(chunks):
        selected_samples = all_samples[cursor : cursor + len(selected_ids)]
        expected_records = int(all_gene_counts[cursor : cursor + len(selected_ids)].sum())
        cursor += len(selected_ids)
        npz_path, manifest_path = _global_expression_paths(output_dir, chunk_index)
        if not _valid_global_expression_checkpoint(
            npz_path,
            manifest_path,
            selected_ids=selected_ids,
            selected_samples=selected_samples,
            expected_records=expected_records,
            n_samples=len(sample_keys),
            n_genes=len(gene_ids),
        ):
            raise RuntimeError(f"invalid global expression checkpoint: {manifest_path}")
        manifest = _load_json(manifest_path)
        with np.load(npz_path, allow_pickle=False) as payload:
            counts += payload["counts"].astype(np.uint64)
            observed_id_parts.append(payload["cell_integer_ids"].astype(np.int64))
        total_records += expected_records
        checkpoint_hashes.append(str(manifest["npz_sha256"]))
    observed_ids = np.concatenate(observed_id_parts)
    if not np.array_equal(observed_ids, all_ids):
        raise RuntimeError("finalization cell-ID coverage is not exact, ordered, and unique")
    if total_records != int(expression_stage.get("expression_records_aggregated", -1)):
        raise RuntimeError("expression record total changed before finalization")
    if not np.any(counts):
        raise RuntimeError("final pseudobulk matrix is empty")
    if int(counts.max()) > np.iinfo(np.uint32).max:
        raise RuntimeError(f"pseudobulk count exceeds uint32: {int(counts.max())}")
    pair_counts = metadata_stage["donor_condition_cell_counts"]
    obs = pd.DataFrame(
        [
            {
                "sample_id": f"Parse10M__{donor}__{cytokine}",
                "donor": donor,
                "cytokine": cytokine,
                "n_cells": int(pair_counts[f"{donor}|{cytokine}"]),
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
        "checkpoint_contract": "donor-condition metadata plus global bounded cell-integer-ID expression ranges",
    }
    output_path = output_dir / "parse_ifnb_pbs_pseudobulk.h5ad"
    temporary_path = output_path.with_name(f"{output_path.name}.incomplete")
    adata.write_h5ad(temporary_path, compression="gzip")
    _assert_pinned_revision(attempts=attempts, boundary="after finalization")
    temporary_path.replace(output_path)
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
        "donor_condition_cell_counts": pair_counts,
        "expression_records_aggregated": total_records,
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


def finalize(output_dir: Path, *, attempts: int) -> dict[str, Any]:
    metadata_stage_path = output_dir / "checkpoints" / "METADATA_STAGE.json"
    expression_stage_path = output_dir / "checkpoints" / "EXPRESSION_STAGE.json"
    if not metadata_stage_path.is_file() or not expression_stage_path.is_file():
        raise RuntimeError("metadata and expression stage manifests are required before finalization")
    metadata_stage = _load_json(metadata_stage_path)
    expression_stage = _load_json(expression_stage_path)
    if int(metadata_stage.get("n_cells", -1)) != EXPECTED_TOTAL_CELLS:
        raise RuntimeError("metadata stage does not cover the locked 725,031-cell population")
    if int(expression_stage.get("n_cells", -1)) != EXPECTED_TOTAL_CELLS:
        raise RuntimeError("expression stage does not cover the locked 725,031-cell population")
    _assert_pinned_revision(attempts=attempts, boundary="before finalization")
    gene_ids, _gene_lookup = _load_genes(attempts=attempts)
    sample_keys = [(donor, cytokine) for donor in EXPECTED_DONORS for cytokine in ELIGIBLE_CYTOKINES]
    counts = np.zeros((len(sample_keys), len(gene_ids)), dtype=np.uint64)
    obs_records: list[dict[str, Any]] = []
    all_cell_ids: list[np.ndarray] = []
    all_checkpoint_hashes: list[str] = []
    total_records = 0

    for sample_index, (donor, cytokine) in enumerate(sample_keys):
        metadata_path, metadata_manifest_path = _metadata_paths(output_dir, donor, cytokine)
        metadata_manifest = _load_json(metadata_manifest_path)
        expected_rows = int(metadata_manifest["n_cells"])
        if not _valid_metadata_checkpoint(
            metadata_path,
            metadata_manifest_path,
            donor=donor,
            cytokine=cytokine,
            expected_rows=expected_rows,
        ):
            raise RuntimeError(f"invalid metadata checkpoint during finalization: {donor}/{cytokine}")
        frame = pq.read_table(metadata_path, columns=["cell_integer_id", "gene_count"]).to_pandas()
        frame = frame.sort_values("cell_integer_id", kind="stable")
        expected_ids = frame["cell_integer_id"].to_numpy(dtype=np.int64)
        chunk_manifests = sorted(
            (output_dir / "checkpoints" / "expression" / _pair_slug(donor, cytokine)).glob("chunk_*.manifest.json")
        )
        if not chunk_manifests:
            raise RuntimeError(f"no expression checkpoints for {donor}/{cytokine}")
        observed_ids: list[np.ndarray] = []
        pair_records = 0
        for manifest_path in chunk_manifests:
            manifest = _load_json(manifest_path)
            npz_path = manifest_path.with_name(manifest_path.name.replace(".manifest.json", ".npz"))
            with np.load(npz_path, allow_pickle=False) as payload:
                vector = payload["counts"]
                chunk_ids = payload["cell_integer_ids"].astype(np.int64)
            expected_records = int(manifest["expected_expression_records"])
            if not _valid_expression_checkpoint(
                npz_path,
                manifest_path,
                donor=donor,
                cytokine=cytokine,
                selected_ids=chunk_ids,
                expected_records=expected_records,
                n_genes=len(gene_ids),
            ):
                raise RuntimeError(f"invalid expression checkpoint: {manifest_path}")
            counts[sample_index] += vector.astype(np.uint64)
            observed_ids.append(chunk_ids)
            pair_records += expected_records
            all_checkpoint_hashes.append(str(manifest["npz_sha256"]))
        concatenated = np.concatenate(observed_ids)
        if not np.array_equal(concatenated, expected_ids):
            raise RuntimeError(f"cell-ID coverage is not exact and ordered for {donor}/{cytokine}")
        expected_pair_records = int(frame["gene_count"].astype(np.int64).sum())
        if pair_records != expected_pair_records:
            raise RuntimeError(f"expression record coverage mismatch for {donor}/{cytokine}")
        all_cell_ids.append(concatenated)
        total_records += pair_records
        obs_records.append(
            {
                "sample_id": f"Parse10M__{donor}__{cytokine}",
                "donor": donor,
                "cytokine": cytokine,
                "n_cells": int(len(expected_ids)),
            }
        )

    population_ids = np.concatenate(all_cell_ids)
    if len(population_ids) != EXPECTED_TOTAL_CELLS or len(np.unique(population_ids)) != EXPECTED_TOTAL_CELLS:
        raise RuntimeError("global cell-ID coverage is not exactly 725,031 unique cells")
    if total_records != int(expression_stage.get("expression_records_aggregated", -1)):
        raise RuntimeError("expression stage record total changed before finalization")
    if not np.any(counts):
        raise RuntimeError("final pseudobulk matrix is empty")
    if int(counts.max()) > np.iinfo(np.uint32).max:
        raise RuntimeError(f"pseudobulk count exceeds uint32: {int(counts.max())}")

    obs = pd.DataFrame(obs_records).set_index("sample_id")
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
        "checkpoint_contract": "donor-condition metadata plus bounded cell-integer-ID expression ranges",
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "parse_ifnb_pbs_pseudobulk.h5ad"
    temporary_path = output_path.with_name(f"{output_path.name}.incomplete")
    adata.write_h5ad(temporary_path, compression="gzip")
    _assert_pinned_revision(attempts=attempts, boundary="after finalization")
    temporary_path.replace(output_path)
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
        "donor_condition_cell_counts": metadata_stage["donor_condition_cell_counts"],
        "expression_records_aggregated": total_records,
        "cell_integer_ids_sha256": _array_sha256(np.sort(population_ids)),
        "ordered_expression_checkpoint_hashes_sha256": hashlib.sha256(
            "".join(all_checkpoint_hashes).encode()
        ).hexdigest(),
        "output_path": str(output_path.relative_to(REPO_ROOT).as_posix()),
        "output_sha256": _sha256(output_path),
        "completed_at": _utc_now(),
    }
    _atomic_json(output_dir / "EXTRACTION_MANIFEST.json", manifest)
    return manifest


def extract(
    output_dir: Path,
    *,
    stage: str,
    max_cells_per_range: int,
    max_cell_id_span: int,
    max_ranges_per_checkpoint: int,
    attempts: int,
) -> dict[str, Any]:
    _ensure_hf_auth()
    results: dict[str, Any] = {}
    if stage in {"metadata", "all"}:
        results["metadata"] = checkpoint_metadata(output_dir, attempts=attempts)
    if stage in {"expression", "all"}:
        results["expression"] = checkpoint_expression_global(
            output_dir,
            max_cells_per_range=max_cells_per_range,
            max_cell_id_span=max_cell_id_span,
            max_ranges_per_checkpoint=max_ranges_per_checkpoint,
            attempts=attempts,
        )
    if stage in {"finalize", "all"}:
        results["finalize"] = finalize_global(output_dir, attempts=attempts)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "data" / "independent" / "parse10m_pbmc_ifnb_natural_v1",
    )
    parser.add_argument("--stage", choices=("metadata", "expression", "finalize", "all"), default="all")
    parser.add_argument("--max-cells-per-range", type=int, default=5_000)
    parser.add_argument("--max-cell-id-span", type=int, default=50_000)
    parser.add_argument("--max-ranges-per-checkpoint", type=int, default=32)
    parser.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args()
    result = extract(
        args.output_dir,
        stage=args.stage,
        max_cells_per_range=args.max_cells_per_range,
        max_cell_id_span=args.max_cell_id_span,
        max_ranges_per_checkpoint=args.max_ranges_per_checkpoint,
        attempts=args.attempts,
    )
    print(json.dumps(result, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
