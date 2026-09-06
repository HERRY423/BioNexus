from __future__ import annotations

import csv
import datetime as dt
import difflib
import gzip
import hashlib
import importlib.metadata
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
from typing import Any

import numpy as np
import psutil


ROOT = pathlib.Path(r"C:\Plugin\BioNexus\review\spatialwarrant-run-01")
OUT_PARENT = ROOT / "03_reference"
FAILED_OUT = OUT_PARENT / "S2A_metrics.v1"
OUT = OUT_PARENT / "S2A_metrics.v1.retry1"
PLAN_SHA256 = "854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82"
SUPPLEMENT_SHA256 = "e6084a97821bc10eecc1060afde4bd049092446a1c1ad02427bd78c6e35086af"
FAILED_SCRIPT_SHA256 = "3539e9de7865a7e5f01f8135ccee8dfb516dd0eae9815e0f7ed9b02591999e20"
FAILED_RECORD_SHA256 = "8613e81eaf5a8ecf97953f0eb2b5477dd5823717cbf06112a9c4f488ec576767"
START_MIN_BYTES = 30 * 1024**3
WRITE_STOP_BELOW_BYTES = 20 * 1024**3
OUTPUT_BUDGET_BYTES = 1024**3
CHUNK_BYTES = 64 * 1024**2

CONTROL_FILES = [
    "00_plan/analysis-plan.lock.md",
    "00_plan/S1-to-S2-entry-review.v1.md",
    "00_plan/S2A-technical-QC-supplement.v1.md",
    "02_identity/scRNA-identity-resolution.v1.json",
    "S1-checkpoint.md",
    "manifest/S1-input-file-index.json",
]
INPUT_BASENAMES = {
    "count_matrix_sparse.mtx",
    "count_matrix_genes.tsv",
    "count_matrix_barcodes.tsv",
    "metadata.csv",
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def exact_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024**2), b""):
            digest.update(block)
    return digest.hexdigest()


def directory_size(path: pathlib.Path) -> int:
    if not path.exists():
        return 0
    return sum(p.stat().st_size for p in path.iterdir() if p.is_file())


def storage_guard(additional_bytes: int = 0) -> int:
    free = shutil.disk_usage("C:\\").free
    if free < WRITE_STOP_BELOW_BYTES:
        raise RuntimeError(
            f"STORAGE_WRITE_FLOOR: free={free}, floor={WRITE_STOP_BELOW_BYTES}"
        )
    if OUT.exists() and directory_size(OUT) + additional_bytes > OUTPUT_BUDGET_BYTES:
        raise RuntimeError(
            f"S2A_OUTPUT_BUDGET: current={directory_size(OUT)}, "
            f"additional={additional_bytes}, cap={OUTPUT_BUDGET_BYTES}"
        )
    return free


def write_bytes_exclusive(name: str, data: bytes) -> pathlib.Path:
    storage_guard(len(data))
    path = OUT / name
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return path


def json_native(value: Any) -> Any:
    """Recursively convert NumPy values to strict JSON-native values."""
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        converted = float(value)
        return converted if math.isfinite(converted) else None
    if isinstance(value, np.ndarray):
        return [json_native(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): json_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_native(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def serialization_selftest() -> dict[str, Any]:
    fixture = {
        "nested": {
            "integer": np.int64(7),
            "floating": np.float64(2.5),
            "boolean": np.bool_(True),
            "array": np.asarray([[np.int64(1), np.int64(2)], [np.int64(3), np.int64(4)]]),
            "missing": np.float64(np.nan),
            "missing_flag": np.bool_(True),
            "positive_infinity": np.float64(np.inf),
            "positive_infinity_missing": np.bool_(True),
            "negative_infinity": np.float64(-np.inf),
            "negative_infinity_missing": np.bool_(True),
        },
        "list": [np.int64(9), np.float64(1.25), np.bool_(False), np.asarray([5, 6])],
        "python_types": {"integer": 11, "floating": 3.75, "boolean": False, "none": None, "text": "ok"},
    }
    expected = {
        "nested": {
            "integer": 7,
            "floating": 2.5,
            "boolean": True,
            "array": [[1, 2], [3, 4]],
            "missing": None,
            "missing_flag": True,
            "positive_infinity": None,
            "positive_infinity_missing": True,
            "negative_infinity": None,
            "negative_infinity_missing": True,
        },
        "list": [9, 1.25, False, [5, 6]],
        "python_types": {"integer": 11, "floating": 3.75, "boolean": False, "none": None, "text": "ok"},
    }
    converted = json_native(fixture)
    encoded = json.dumps(converted, ensure_ascii=False, allow_nan=False, sort_keys=True)
    decoded = json.loads(encoded)
    forbidden_literals_absent = not any(token in encoded for token in ["NaN", "Infinity", "-Infinity"])
    passed = decoded == expected and forbidden_literals_absent
    result = {
        "status": "PASS" if passed else "FAIL",
        "scope": "Engineering serialization only; not scientific validation",
        "covered": [
            "nested dict/list",
            "numpy.int64 -> int",
            "numpy.float64 finite -> float",
            "numpy.float64 nonfinite -> null with separate missing flags",
            "numpy.bool_ -> bool",
            "numpy.ndarray -> recursively converted list",
            "ordinary Python JSON types unchanged",
        ],
        "strict_allow_nan": False,
        "forbidden_nonfinite_literals_absent": forbidden_literals_absent,
        "converted_value": converted,
        "expected_value_match": decoded == expected,
    }
    if not passed:
        raise RuntimeError("JSON_SERIALIZATION_SELFTEST_FAILED")
    return result


def write_json_exclusive(name: str, value: Any) -> pathlib.Path:
    data = (
        json.dumps(json_native(value), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    return write_bytes_exclusive(name, data)


def read_control_and_hashes() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    parsed: dict[str, Any] = {}
    for rel in CONTROL_FILES:
        path = ROOT / rel
        data = path.read_bytes()
        text = data.decode("utf-8-sig")
        if path.suffix == ".json":
            parsed[rel] = json.loads(text)
        else:
            parsed[rel] = text
        records.append(
            {
                "file": rel,
                "bytes": len(data),
                "sha256_exact_bytes": hashlib.sha256(data).hexdigest(),
                "read_in_full": True,
            }
        )
    if records[0]["sha256_exact_bytes"] != PLAN_SHA256:
        raise RuntimeError("PARENT_PLAN_HASH_MISMATCH")
    supplement_record = next(
        x for x in records if x["file"].endswith("S2A-technical-QC-supplement.v1.md")
    )
    if supplement_record["sha256_exact_bytes"] != SUPPLEMENT_SHA256:
        raise RuntimeError("S2A_SUPPLEMENT_HASH_MISMATCH")
    review = parsed["00_plan/S1-to-S2-entry-review.v1.md"]
    if SUPPLEMENT_SHA256 not in review or PLAN_SHA256 not in review:
        raise RuntimeError("ENTRY_REVIEW_BINDING_MISMATCH")
    resolution = parsed["02_identity/scRNA-identity-resolution.v1.json"]
    if resolution["canonical_technical_key"]["name"] != "source_sample_id":
        raise RuntimeError("IDENTITY_KEY_NOT_SOURCE_SAMPLE_ID")
    if resolution["alias_review"]["action"] != "KEEP_SEPARATE_NO_ALIAS":
        raise RuntimeError("CID4290_ALIAS_POLICY_MISMATCH")
    return records, parsed


def resolve_and_hash_inputs(index: dict[str, Any]) -> tuple[dict[str, pathlib.Path], list[dict[str, Any]]]:
    selected: dict[str, dict[str, Any]] = {}
    for item in index["files"]:
        base = pathlib.Path(item["relative_path"]).name
        if base in INPUT_BASENAMES:
            if base in selected:
                raise RuntimeError(f"AMBIGUOUS_S2A_INPUT: {base}")
            selected[base] = item
    if set(selected) != INPUT_BASENAMES:
        raise RuntimeError(
            f"MISSING_S2A_INPUT: expected={sorted(INPUT_BASENAMES)}, got={sorted(selected)}"
        )
    paths: dict[str, pathlib.Path] = {}
    records: list[dict[str, Any]] = []
    for base in sorted(selected):
        item = selected[base]
        path = pathlib.Path(item["absolute_path"])
        actual_size = path.stat().st_size
        actual_sha = exact_sha256(path)
        size_match = actual_size == item["bytes"]
        hash_match = actual_sha == item["sha256_raw_bytes"]
        records.append(
            {
                "role": base,
                "path": str(path),
                "bytes": actual_size,
                "expected_bytes": item["bytes"],
                "sha256_exact_bytes": actual_sha,
                "expected_sha256_exact_bytes": item["sha256_raw_bytes"],
                "size_match": size_match,
                "sha256_match": hash_match,
            }
        )
        if not size_match or not hash_match:
            raise RuntimeError(f"S2A_INPUT_HASH_OR_SIZE_MISMATCH: {base}")
        paths[base] = path
    return paths, records


def nondestructive_write_check() -> dict[str, Any]:
    payload = ("SpatialWarrant-S2A-preflight:" + str(uuid.uuid4())).encode("ascii")
    path = ROOT / "00_plan" / f".S2A-write-check-{uuid.uuid4().hex}.tmp"
    if path.exists():
        raise RuntimeError("WRITE_CHECK_TARGET_CONFLICT")
    started = utc_now()
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    returned = path.read_bytes()
    if returned != payload:
        raise RuntimeError("WRITE_CHECK_READBACK_MISMATCH")
    path.unlink()
    if path.exists():
        raise RuntimeError("WRITE_CHECK_DELETE_FAILED")
    return {
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "bytes": len(payload),
        "flush_and_fsync": True,
        "readback_match": True,
        "temporary_file_deleted": True,
        "temporary_parent": "00_plan",
    }


def read_genes(path: pathlib.Path) -> tuple[list[str], np.ndarray, bytes]:
    genes = path.read_text(encoding="utf-8-sig").splitlines()
    if not genes or any(not gene for gene in genes):
        raise RuntimeError("EMPTY_OR_MISSING_GENE_SYMBOL")
    if len(genes) != len(set(genes)):
        raise RuntimeError("DUPLICATE_GENE_SYMBOL")
    mask = np.fromiter((gene.startswith("MT-") for gene in genes), dtype=np.bool_)
    membership = "".join(
        f"{index}\t{gene}\n"
        for index, (gene, is_mt) in enumerate(zip(genes, mask, strict=True), start=1)
        if is_mt
    ).encode("utf-8")
    if not mask.any():
        raise RuntimeError("EMPTY_EXACT_MT_PREFIX_FEATURE_SET")
    return genes, mask, membership


def read_barcodes(path: pathlib.Path) -> list[str]:
    barcodes = path.read_text(encoding="utf-8-sig").splitlines()
    if not barcodes or any(not barcode for barcode in barcodes):
        raise RuntimeError("EMPTY_OR_MISSING_BARCODE")
    if len(barcodes) != len(set(barcodes)):
        raise RuntimeError("DUPLICATE_BARCODE")
    return barcodes


def read_metadata(path: pathlib.Path, barcodes: list[str]) -> tuple[list[str], list[str], list[str], list[str]]:
    metadata_barcodes: list[str] = []
    source_sample_ids: list[str] = []
    producer_minor: list[str] = []
    fieldnames: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        required = {"", "orig.ident", "celltype_minor"}
        if not required.issubset(fieldnames):
            raise RuntimeError(f"METADATA_REQUIRED_FIELDS_MISSING: {sorted(required-set(fieldnames))}")
        if "patient_id" in fieldnames:
            raise RuntimeError("UNEXPECTED_PATIENT_ID_FIELD")
        for row in reader:
            metadata_barcodes.append(row[""])
            source_sample_ids.append(row["orig.ident"])
            producer_minor.append(row["celltype_minor"])
    if metadata_barcodes != barcodes:
        raise RuntimeError("BARCODE_METADATA_ORDER_OR_VALUE_MISMATCH")
    if len(metadata_barcodes) != len(set(metadata_barcodes)):
        raise RuntimeError("DUPLICATE_METADATA_BARCODE")
    if any(not value for value in source_sample_ids):
        raise RuntimeError("MISSING_SOURCE_SAMPLE_ID")
    if any(not value for value in producer_minor):
        raise RuntimeError("MISSING_PRODUCER_CELLTYPE_MINOR")
    return metadata_barcodes, source_sample_ids, producer_minor, fieldnames


def parse_matrix_streaming(
    path: pathlib.Path, n_genes_expected: int, n_cells_expected: int, mt_mask: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    total_umi = np.zeros(n_cells_expected, dtype=np.int64)
    detected_genes = np.zeros(n_cells_expected, dtype=np.int64)
    mitochondrial_umi = np.zeros(n_cells_expected, dtype=np.int64)
    explicit_zero_entries = 0
    observed_entries = 0
    duplicate_coordinates = 0
    ordering_violations = 0
    previous_key = -1
    chunks = 0
    max_count_value = 0
    min_count_value: int | None = None
    process = psutil.Process()
    peak_working_set = process.memory_info().peak_wset
    last_progress = -1
    file_bytes = path.stat().st_size
    with path.open("rb", buffering=1024 * 1024) as handle:
        header = handle.readline().rstrip(b"\r\n")
        if header != b"%%MatrixMarket matrix coordinate integer general":
            raise RuntimeError(f"MATRIX_MARKET_HEADER_MISMATCH: {header!r}")
        dimension_line = handle.readline()
        while dimension_line.startswith(b"%"):
            dimension_line = handle.readline()
        dims = dimension_line.split()
        if len(dims) != 3:
            raise RuntimeError("MATRIX_DIMENSION_LINE_INVALID")
        try:
            n_genes, n_cells, declared_nnz = map(int, dims)
        except ValueError as exc:
            raise RuntimeError("MATRIX_DIMENSION_NONINTEGER") from exc
        if (n_genes, n_cells) != (n_genes_expected, n_cells_expected):
            raise RuntimeError(
                f"MATRIX_DIMENSION_MISMATCH: matrix={(n_genes,n_cells)}, "
                f"features_barcodes={(n_genes_expected,n_cells_expected)}"
            )
        tail = b""
        while True:
            storage_guard()
            block = handle.read(CHUNK_BYTES)
            if not block:
                data = tail
                tail = b""
            else:
                data = tail + block
                cut = data.rfind(b"\n")
                if cut < 0:
                    if len(data) > CHUNK_BYTES * 2:
                        raise RuntimeError("MATRIX_LINE_EXCEEDS_STREAMING_LIMIT")
                    tail = data
                    continue
                tail = data[cut + 1 :]
                data = data[: cut + 1]
            if data:
                line_count = data.count(b"\n")
                if not block and not data.endswith(b"\n"):
                    line_count += 1
                if b"\t" in data or data.count(b" ") != 2 * line_count:
                    raise RuntimeError("MATRIX_COORDINATE_TOKEN_LAYOUT_INVALID")
                values = np.fromstring(data, dtype=np.float64, sep=" ")
                if values.size != 3 * line_count:
                    raise RuntimeError(
                        f"MATRIX_TOKEN_PARSE_COUNT_MISMATCH: values={values.size}, lines={line_count}"
                    )
                triples = values.reshape((-1, 3))
                if not np.isfinite(triples).all():
                    raise RuntimeError("MATRIX_NONFINITE_VALUE")
                if not np.equal(triples, np.floor(triples)).all():
                    raise RuntimeError("MATRIX_NONINTEGER_VALUE")
                if np.abs(triples).max(initial=0) > 2**53:
                    raise RuntimeError("MATRIX_INTEGER_EXCEEDS_EXACT_FLOAT64_PARSE_RANGE")
                row = triples[:, 0].astype(np.int64)
                col = triples[:, 1].astype(np.int64)
                count = triples[:, 2].astype(np.int64)
                if row.min(initial=1) < 1 or row.max(initial=0) > n_genes:
                    raise RuntimeError("MATRIX_GENE_INDEX_OUT_OF_RANGE")
                if col.min(initial=1) < 1 or col.max(initial=0) > n_cells:
                    raise RuntimeError("MATRIX_CELL_INDEX_OUT_OF_RANGE")
                if count.min(initial=0) < 0:
                    raise RuntimeError("MATRIX_NEGATIVE_COUNT")
                if len(count):
                    max_count_value = max(max_count_value, int(count.max()))
                    cmin = int(count.min())
                    min_count_value = cmin if min_count_value is None else min(min_count_value, cmin)
                keys = (col - 1) * n_genes + (row - 1)
                if len(keys):
                    if int(keys[0]) < previous_key:
                        ordering_violations += 1
                        raise RuntimeError("MATRIX_COORDINATES_NOT_COLUMN_MAJOR_SORTED")
                    if int(keys[0]) == previous_key:
                        duplicate_coordinates += 1
                        raise RuntimeError("MATRIX_DUPLICATE_COORDINATE")
                    differences = np.diff(keys)
                    if (differences < 0).any():
                        ordering_violations += int((differences < 0).sum())
                        raise RuntimeError("MATRIX_COORDINATES_NOT_COLUMN_MAJOR_SORTED")
                    if (differences == 0).any():
                        duplicate_coordinates += int((differences == 0).sum())
                        raise RuntimeError("MATRIX_DUPLICATE_COORDINATE")
                    previous_key = int(keys[-1])
                positive = count > 0
                explicit_zero_entries += int((~positive).sum())
                cell_index = col - 1
                add_total = np.bincount(cell_index, weights=count, minlength=n_cells)
                if (add_total > 2**53).any():
                    raise RuntimeError("CHUNK_CELL_UMI_EXCEEDS_EXACT_FLOAT64_SUM_RANGE")
                total_umi += add_total.astype(np.int64)
                if positive.any():
                    detected_genes += np.bincount(
                        cell_index[positive], minlength=n_cells
                    ).astype(np.int64)
                    is_mt = mt_mask[row - 1] & positive
                    if is_mt.any():
                        add_mt = np.bincount(
                            cell_index[is_mt], weights=count[is_mt], minlength=n_cells
                        )
                        mitochondrial_umi += add_mt.astype(np.int64)
                observed_entries += len(count)
                chunks += 1
                peak_working_set = max(peak_working_set, process.memory_info().peak_wset)
            progress = int(100 * handle.tell() / file_bytes)
            if progress // 10 > last_progress // 10:
                last_progress = progress
                print(
                    json.dumps(
                        {
                            "event": "matrix_scan_progress",
                            "percent": min(progress, 100),
                            "entries": observed_entries,
                            "free_C_bytes": shutil.disk_usage("C:\\").free,
                        }
                    ),
                    flush=True,
                )
            if not block:
                break
    if observed_entries != declared_nnz:
        raise RuntimeError(
            f"MATRIX_NNZ_MISMATCH: observed={observed_entries}, declared={declared_nnz}"
        )
    if (mitochondrial_umi > total_umi).any():
        raise RuntimeError("MITOCHONDRIAL_UMI_EXCEEDS_TOTAL_UMI")
    validation = {
        "matrix_market_header": header.decode("ascii"),
        "matrix_dimensions_genes_cells_nnz": [n_genes, n_cells, declared_nnz],
        "observed_coordinate_entries": observed_entries,
        "all_declared_entries_scanned": True,
        "all_numeric_tokens_finite": True,
        "all_indices_and_counts_integer": True,
        "all_gene_indices_in_range": True,
        "all_cell_indices_in_range": True,
        "all_counts_nonnegative": True,
        "minimum_count_value": min_count_value,
        "maximum_count_value": max_count_value,
        "explicit_zero_coordinate_entries": explicit_zero_entries,
        "coordinate_order": "strictly increasing (cell column, gene row)",
        "coordinate_ordering_violations": ordering_violations,
        "duplicate_coordinates": duplicate_coordinates,
        "duplicate_coordinate_check": "PASS; strict global order makes any duplicate adjacent",
        "streaming": True,
        "matrix_densified": False,
        "full_matrix_copied": False,
        "chunk_bytes": CHUNK_BYTES,
        "chunks": chunks,
        "peak_working_set_during_scan_bytes": peak_working_set,
    }
    return total_umi, detected_genes, mitochondrial_umi, validation


def metric_stats(values: np.ndarray, valid: np.ndarray, zero_umi_count: int) -> dict[str, Any]:
    subset = values[valid]
    if len(subset) == 0:
        summary = {key: None for key in ["minimum", "maximum", "median", "q01", "q05", "q25", "q75", "q95", "q99"]}
        zero_values = 0
    else:
        q = np.quantile(subset, [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99], method="linear")
        summary = {
            "minimum": float(np.min(subset)),
            "maximum": float(np.max(subset)),
            "median": float(q[3]),
            "q01": float(q[0]),
            "q05": float(q[1]),
            "q25": float(q[2]),
            "q75": float(q[4]),
            "q95": float(q[5]),
            "q99": float(q[6]),
        }
        zero_values = int((subset == 0).sum())
    return {
        "cell_count": int(len(values)),
        "valid_count": int(valid.sum()),
        "missing_count": int((~valid).sum()),
        "zero_value_count_among_valid": zero_values,
        "zero_UMI_count": zero_umi_count,
        **summary,
    }


def format_float(value: Any) -> str:
    if value is None:
        return ""
    return format(float(value), ".17g")


def main() -> None:
    process = psutil.Process()
    script_started_wall = time.perf_counter()
    started_at = utc_now()
    if OUT.exists():
        raise RuntimeError(f"TARGET_DIRECTORY_CONFLICT: {OUT}")
    failed_script = FAILED_OUT / "run-s2a-metrics.v1.py"
    failed_record = FAILED_OUT / "failure.v1.json"
    if not FAILED_OUT.is_dir():
        raise RuntimeError(f"FAILED_LINEAGE_DIRECTORY_MISSING: {FAILED_OUT}")
    if exact_sha256(failed_script) != FAILED_SCRIPT_SHA256:
        raise RuntimeError("FAILED_SCRIPT_LINEAGE_HASH_MISMATCH")
    if exact_sha256(failed_record) != FAILED_RECORD_SHA256:
        raise RuntimeError("FAILED_RECORD_LINEAGE_HASH_MISMATCH")
    free_before_preflight = shutil.disk_usage("C:\\").free
    if free_before_preflight < START_MIN_BYTES:
        raise RuntimeError(
            f"START_STORAGE_GATE: free={free_before_preflight}, minimum={START_MIN_BYTES}"
        )
    control_records, parsed = read_control_and_hashes()
    input_paths, input_records = resolve_and_hash_inputs(
        parsed["manifest/S1-input-file-index.json"]
    )
    write_check = nondestructive_write_check()
    free_after_write_check = shutil.disk_usage("C:\\").free
    if free_after_write_check < START_MIN_BYTES:
        raise RuntimeError(
            f"START_STORAGE_GATE_AFTER_WRITE_CHECK: free={free_after_write_check}, "
            f"minimum={START_MIN_BYTES}"
        )

    dependencies = {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "numpy": importlib.metadata.version("numpy"),
        "psutil": importlib.metadata.version("psutil"),
        "bionexus_distribution_metadata": importlib.metadata.version("bionexus"),
    }
    import bionexus
    from bionexus.provenance import sidecar

    dependencies["bionexus_runtime_version"] = getattr(bionexus, "__version__", "UNKNOWN")
    dependencies["bionexus_import_origin"] = str(pathlib.Path(bionexus.__file__).resolve())

    OUT_PARENT.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=False)
    retry_script_name = "run-s2a-metrics.v1.retry1.py"
    retry_script_path = write_bytes_exclusive(retry_script_name, pathlib.Path(__file__).read_bytes())
    retry_script_sha256 = exact_sha256(retry_script_path)
    failed_text = failed_script.read_text(encoding="utf-8")
    retry_text = pathlib.Path(__file__).read_text(encoding="utf-8")
    engineering_diff = "".join(
        difflib.unified_diff(
            failed_text.splitlines(keepends=True),
            retry_text.splitlines(keepends=True),
            fromfile="S2A_metrics.v1/run-s2a-metrics.v1.py",
            tofile="S2A_metrics.v1.retry1/run-s2a-metrics.v1.retry1.py",
        )
    )
    write_bytes_exclusive("engineering-fix.v1.diff", engineering_diff.encode("utf-8"))
    write_bytes_exclusive(
        "engineering-fix.v1.md",
        f"""# S2A retry1 minimal engineering fix

- Failed script SHA-256: {FAILED_SCRIPT_SHA256}
- Retry1 script SHA-256: {retry_script_sha256}
- Failed record SHA-256: {FAILED_RECORD_SHA256}
- Failed directory retained unchanged: {FAILED_OUT}
- Retry output directory: {OUT}

Authorized changes only:
1. Changed the fixed output directory from `S2A_metrics.v1` to `S2A_metrics.v1.retry1`.
2. Added recursive conversion of NumPy integer, floating, boolean and ndarray values to strict JSON-native values; non-finite floating values become null and fields that can be missing retain separate missing flags.
3. Added a strict JSON serialization self-test before the complete matrix scan.
4. Added lineage references to the failed script and `failure.v1.json`, including their exact approved hashes.

Matrix parsing, formulas, identity handling, MT- prefix rule, index base, summaries, scientific scope and stop conditions are unchanged. See `engineering-fix.v1.diff` for the exact textual diff.
""".encode("utf-8"),
    )
    write_json_exclusive(
        "execution-start.v1.json",
        {
            "status": "RUNNING",
            "stage": "S2A_metrics_only",
            "started_at_utc": started_at,
            "route": "local Python execution",
            "registered_NGS_workflow_run": "NONE",
            "parent_plan_sha256": PLAN_SHA256,
            "S2A_supplement_sha256": SUPPLEMENT_SHA256,
            "retry_lineage": {
                "failed_output_directory": str(FAILED_OUT),
                "failed_script_sha256": FAILED_SCRIPT_SHA256,
                "failure_record_sha256": FAILED_RECORD_SHA256,
                "retry_script_sha256": retry_script_sha256,
                "failed_directory_preserved": True,
            },
            "free_C_bytes_before_preflight": free_before_preflight,
            "free_C_bytes_after_write_check": free_after_write_check,
            "write_check": write_check,
            "scope": "Technical QC metrics only; no filtering or biological interpretation",
        },
    )
    selftest = serialization_selftest()
    selftest["completed_at_utc"] = utc_now()
    selftest["completed_before_full_matrix_scan"] = True
    write_json_exclusive("json-serialization-selftest.v1.json", selftest)
    write_json_exclusive(
        "ngs-workbench-capability-check.v1.json",
        {
            "observed_at_utc": started_at,
            "skills_applied": ["understand-ngs-data", "run-ngs-analysis"],
            "starting_point": "GSE176078 published processed integer UMI MatrixMarket matrix plus producer metadata",
            "endpoint": "S2A cell-level and source-sample-level technical QC metrics only",
            "list_compute_targets": {
                "status": "SUCCESS",
                "count": 1,
                "target_id": "local",
                "title": "This computer",
                "executor": "local_process",
            },
            "list_workflows": {
                "status": "SUCCESS",
                "count": 12,
                "processed_matrix_to_S2A_compatible_registered_workflow": False,
                "scRNA_entries": [
                    {
                        "workflow_id": "oai_scrnaseq_fastq_to_count",
                        "revision": "source_sha256:6f7aa0dcf4ed6fdb6e187ff0f8d1128b6ffa93504bc688aee341fe250a893510",
                        "reason_not_selected": "FASTQ-to-count, not processed-matrix S2A metrics",
                    },
                    {
                        "workflow_id": "scrnaseq",
                        "revision": "nf-core/scrnaseq 4.2.0",
                        "reason_not_selected": "FASTQ-to-count, not processed-matrix S2A metrics",
                    },
                ],
            },
            "get_runtime_environment": {
                "status": "NO_RETURN_WITHIN_APPROXIMATELY_60_SECONDS",
                "action": "Waiting stopped; no runtime snapshot invented",
            },
            "selected_route": "local Python execution",
            "execution_plan_id": None,
            "registry_run_id": None,
            "registered_NGS_workflow_run": "NONE",
            "retry_lineage": {
                "failed_script_sha256": FAILED_SCRIPT_SHA256,
                "failure_record_sha256": FAILED_RECORD_SHA256,
            },
        },
    )

    genes, mt_mask, mt_membership = read_genes(input_paths["count_matrix_genes.tsv"])
    barcodes = read_barcodes(input_paths["count_matrix_barcodes.tsv"])
    metadata_barcodes, source_sample_ids, producer_minor, metadata_fields = read_metadata(
        input_paths["metadata.csv"], barcodes
    )
    source_values = sorted(set(source_sample_ids))
    label_values = sorted(set(producer_minor))
    total_umi, detected_genes, mitochondrial_umi, matrix_validation = parse_matrix_streaming(
        input_paths["count_matrix_sparse.mtx"], len(genes), len(barcodes), mt_mask
    )
    zero_umi = total_umi == 0
    mitochondrial_percent = np.full(len(barcodes), np.nan, dtype=np.float64)
    nonzero = ~zero_umi
    mitochondrial_percent[nonzero] = (
        100.0 * mitochondrial_umi[nonzero] / total_umi[nonzero]
    )

    write_bytes_exclusive("mitochondrial-feature-members.v1.tsv", mt_membership)
    write_json_exclusive(
        "mitochondrial-feature-mask.v1.json",
        {
            "rule": "case-sensitive exact MT- prefix on the published feature symbols",
            "feature_index_base": 1,
            "member_count": int(mt_mask.sum()),
            "members_file": "mitochondrial-feature-members.v1.tsv",
            "members_file_sha256_exact_bytes": hashlib.sha256(mt_membership).hexdigest(),
            "members": [
                {"feature_index_1_based": int(i) + 1, "gene_symbol": genes[int(i)]}
                for i in np.flatnonzero(mt_mask)
            ],
            "alias_expansion": False,
            "expression_selected": False,
        },
    )

    per_cell_path = OUT / "per-cell-QC.v1.csv.gz"
    storage_guard()
    with per_cell_path.open("xb") as raw:
        with gzip.GzipFile(
            filename="per-cell-QC.v1.csv", mode="wb", fileobj=raw, compresslevel=6, mtime=0
        ) as compressed:
            import io

            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                writer = csv.writer(text, lineterminator="\n")
                writer.writerow(
                    [
                        "barcode",
                        "source_sample_id",
                        "producer_celltype_minor",
                        "total_UMI",
                        "detected_genes",
                        "mitochondrial_percent",
                        "zero_UMI",
                        "total_UMI_missing",
                        "detected_genes_missing",
                        "mitochondrial_percent_missing",
                    ]
                )
                for i, barcode in enumerate(barcodes):
                    writer.writerow(
                        [
                            barcode,
                            source_sample_ids[i],
                            producer_minor[i],
                            int(total_umi[i]),
                            int(detected_genes[i]),
                            "" if zero_umi[i] else format(float(mitochondrial_percent[i]), ".17g"),
                            str(bool(zero_umi[i])).lower(),
                            "false",
                            "false",
                            str(bool(zero_umi[i])).lower(),
                        ]
                    )
                    if i % 10000 == 0:
                        storage_guard()
        raw.flush()
        os.fsync(raw.fileno())
    storage_guard()

    source_array = np.asarray(source_sample_ids, dtype=object)
    metric_rows: list[dict[str, Any]] = []
    missingness_by_source: dict[str, Any] = {}
    for source in source_values:
        chosen = source_array == source
        z = int(zero_umi[chosen].sum())
        summaries = {
            "total_UMI": metric_stats(total_umi[chosen], np.ones(chosen.sum(), dtype=bool), z),
            "detected_genes": metric_stats(
                detected_genes[chosen], np.ones(chosen.sum(), dtype=bool), z
            ),
            "mitochondrial_percent": metric_stats(
                mitochondrial_percent[chosen], ~np.isnan(mitochondrial_percent[chosen]), z
            ),
        }
        missingness_by_source[source] = {
            metric: {
                "cell_count": info["cell_count"],
                "valid_count": info["valid_count"],
                "missing_count": info["missing_count"],
                "zero_value_count_among_valid": info["zero_value_count_among_valid"],
                "zero_UMI_count": info["zero_UMI_count"],
            }
            for metric, info in summaries.items()
        }
        for metric, info in summaries.items():
            metric_rows.append({"source_sample_id": source, "metric": metric, **info})

    summary_headers = [
        "source_sample_id",
        "metric",
        "cell_count",
        "valid_count",
        "missing_count",
        "zero_value_count_among_valid",
        "zero_UMI_count",
        "minimum",
        "maximum",
        "median",
        "q01",
        "q05",
        "q25",
        "q75",
        "q95",
        "q99",
    ]
    import io

    summary_buffer = io.StringIO(newline="")
    writer = csv.DictWriter(summary_buffer, fieldnames=summary_headers, lineterminator="\n")
    writer.writeheader()
    for row in metric_rows:
        encoded = dict(row)
        for key in ["minimum", "maximum", "median", "q01", "q05", "q25", "q75", "q95", "q99"]:
            encoded[key] = format_float(encoded[key])
        writer.writerow(encoded)
    write_bytes_exclusive(
        "per-source-sample-QC.v1.csv", summary_buffer.getvalue().encode("utf-8")
    )

    overall_missingness = {
        "total_UMI": {
            "cell_count": len(barcodes),
            "valid_count": len(barcodes),
            "missing_count": 0,
            "zero_value_count": int((total_umi == 0).sum()),
        },
        "detected_genes": {
            "cell_count": len(barcodes),
            "valid_count": len(barcodes),
            "missing_count": 0,
            "zero_value_count": int((detected_genes == 0).sum()),
        },
        "mitochondrial_percent": {
            "cell_count": len(barcodes),
            "valid_count": int(nonzero.sum()),
            "missing_count": int(zero_umi.sum()),
            "missing_reason": "total_UMI=0",
            "zero_value_count_among_valid": int(
                (mitochondrial_percent[nonzero] == 0).sum()
            ),
        },
        "zero_UMI": {
            "cell_count": len(barcodes),
            "true_count": int(zero_umi.sum()),
            "false_count": int(nonzero.sum()),
            "missing_count": 0,
        },
    }
    write_json_exclusive(
        "missingness.v1.json",
        {
            "overall": overall_missingness,
            "by_source_sample_id": missingness_by_source,
            "policy": "mitochondrial_percent is missing when total_UMI=0; missing is never filled with zero",
        },
    )

    validation = {
        "status": "PASS",
        "scope": "Technical input and full count-value integrity only; not biological validation",
        "control_files": control_records,
        "S2A_inputs": input_records,
        "hash_gate": "PASS",
        "approved_parent_plan_sha256": PLAN_SHA256,
        "approved_S2A_supplement_sha256": SUPPLEMENT_SHA256,
        "matrix": matrix_validation,
        "features": {
            "count": len(genes),
            "all_nonempty": True,
            "unique_exact_symbols": True,
            "duplicate_exact_symbols": 0,
        },
        "barcodes": {
            "count": len(barcodes),
            "all_nonempty": True,
            "unique": True,
            "duplicates": 0,
        },
        "metadata": {
            "row_count": len(metadata_barcodes),
            "columns": metadata_fields,
            "barcode_unique": True,
            "barcode_order_and_values_equal_matrix_barcodes": True,
            "one_to_one_join": True,
            "identity_field_used": "orig.ident renamed only in outputs as source_sample_id",
            "patient_id_created": False,
            "source_sample_id_count": len(source_values),
            "missing_source_sample_id": 0,
            "producer_celltype_minor_distinct": len(label_values),
            "missing_producer_celltype_minor": 0,
            "producer_labels_reannotated_or_merged": False,
        },
        "alias": {
            "CID4290_CID4290A_merged": False,
            "status": "PENDING",
        },
        "cells_filtered_deleted_or_sampled": 0,
        "normalization_HVG_PCA_Leiden_integration_doublet_ambient_marker_label_evaluation_reference_construction_spatial_analysis": "NOT_RUN",
    }
    write_json_exclusive("input-validation.v1.json", validation)

    write_json_exclusive(
        "qc-threshold-proposal.v1.json",
        {
            "status": "AWAITING_HUMAN_APPROVAL",
            "created_at_utc": utc_now(),
            "source_metrics": [
                "per-cell-QC.v1.csv.gz",
                "per-source-sample-QC.v1.csv",
                "missingness.v1.json",
            ],
            "thresholds": {
                "minimum_detected_genes": None,
                "minimum_total_UMI": None,
                "maximum_detected_genes": None,
                "maximum_total_UMI": None,
                "maximum_mitochondrial_percent": None,
            },
            "threshold_application": "NOT_RUN",
            "cells_passed_or_failed": "NOT_ASSIGNED",
            "next_required_decision": "Human review must choose and hash-bind data-dependent thresholds and approve S2B separately",
            "constraints": [
                "Review distributions by source_sample_id",
                "Do not use boundary effects or biological outcome direction",
                "Do not create patient_id or merge CID4290/CID4290A",
                "Do not merge producer celltype_minor labels",
            ],
        },
    )

    elapsed_before_finalization = time.perf_counter() - script_started_wall
    peak_working_set = process.memory_info().peak_wset
    write_json_exclusive(
        "execution-environment.v1.json",
        {
            "created_at_utc": utc_now(),
            "route": "local Python execution",
            "registered_NGS_workflow_run": "NONE",
            "dependencies": dependencies,
            "new_dependencies_installed": False,
            "matrix_read_mode": "64 MiB byte chunks parsed to temporary numeric arrays; per-cell accumulators only",
            "sparse_or_streaming": True,
            "matrix_densified": False,
            "full_matrix_copy_created": False,
            "peak_working_set_bytes_observed_by_OS": peak_working_set,
            "peak_measurement_field": "psutil.Process.memory_info().peak_wset",
            "elapsed_seconds_before_final_manifest": elapsed_before_finalization,
        },
    )

    core_output_names = sorted(p.name for p in OUT.iterdir() if p.is_file())
    core_records = [
        {
            "file": name,
            "bytes": (OUT / name).stat().st_size,
            "sha256_exact_bytes": exact_sha256(OUT / name),
        }
        for name in core_output_names
    ]
    provenance = sidecar(
        activity_name="SpatialWarrant S2A technical QC metrics",
        input_files=[input_paths[name] for name in sorted(input_paths)],
        output_files=[OUT / name for name in core_output_names if name.endswith((".json", ".csv", ".gz", ".tsv"))],
        parameters={
            "parent_plan_sha256": PLAN_SHA256,
            "S2A_supplement_sha256": SUPPLEMENT_SHA256,
            "identity_key": "source_sample_id",
            "mitochondrial_feature_rule": "case-sensitive MT- prefix",
            "filtering": False,
            "sampling": False,
            "registered_NGS_workflow_run": "NONE",
            "retry_of_failed_script_sha256": FAILED_SCRIPT_SHA256,
            "retry_of_failure_record_sha256": FAILED_RECORD_SHA256,
        },
        method="Streaming full MatrixMarket count validation and metrics-only aggregation",
        backend="local Python execution",
    )
    provenance["scope_boundary"] = (
        "Technical provenance only; no scientific Warrant, biological validation, or conclusion"
    )
    provenance["BioNexus_machine_verdict"] = "PENDING"
    provenance["scientific_warrant_generated"] = False
    provenance["retry_lineage"] = {
        "failed_output_directory": str(FAILED_OUT),
        "failed_script_sha256": FAILED_SCRIPT_SHA256,
        "failure_record_sha256": FAILED_RECORD_SHA256,
        "retry_script_sha256": retry_script_sha256,
        "failed_directory_preserved": True,
    }
    write_json_exclusive("provenance.sidecar.v1.json", provenance)

    manifest_outputs = sorted(p.name for p in OUT.iterdir() if p.is_file())
    manifest_records = [
        {
            "file": name,
            "bytes": (OUT / name).stat().st_size,
            "sha256_exact_bytes": exact_sha256(OUT / name),
        }
        for name in manifest_outputs
    ]
    write_json_exclusive(
        "output-manifest.v1.json",
        {
            "status": "COMPLETED",
            "stage": "S2A_metrics_only",
            "created_at_utc": utc_now(),
            "parent_plan_sha256": PLAN_SHA256,
            "S2A_supplement_sha256": SUPPLEMENT_SHA256,
            "retry_lineage": {
                "failed_output_directory": str(FAILED_OUT),
                "failed_script_sha256": FAILED_SCRIPT_SHA256,
                "failure_record_sha256": FAILED_RECORD_SHA256,
                "retry_script_sha256": retry_script_sha256,
                "failed_directory_preserved": True,
            },
            "input_files": input_records,
            "outputs_created_before_this_manifest": manifest_records,
            "self_hash": "See SHA256SUMS.v1.txt to avoid a circular self-hash",
            "hash_semantics": "SHA-256 of exact bytes",
            "output_budget_bytes": OUTPUT_BUDGET_BYTES,
            "filtering_or_sampling": "NOT_RUN",
            "S2B": "PENDING",
            "S3": "BLOCKED",
            "patient_level_inference": "BLOCKED",
            "machine_verdict": "PENDING",
            "biological_conclusion": "PENDING",
        },
    )

    ended_at = utc_now()
    elapsed = time.perf_counter() - script_started_wall
    free_at_end_before_final_files = shutil.disk_usage("C:\\").free
    peak_working_set = process.memory_info().peak_wset

    def checkpoint_text(total_artifact_bytes: int) -> str:
        return f"""# SpatialWarrant S2A metrics checkpoint v1

Status: COMPLETED. STOPPED_AFTER_S2A; S2B_NOT_AUTHORIZED; S3_BLOCKED.
Started: {started_at}
Completed: {ended_at}
Actual execution route: local Python execution. Registered NGS workflow run: NONE.

- Approved parent plan SHA-256: {PLAN_SHA256}
- Approved S2A supplement SHA-256: {SUPPLEMENT_SHA256}
- Failed script SHA-256: {FAILED_SCRIPT_SHA256}; failure.v1.json SHA-256: {FAILED_RECORD_SHA256}; failed directory retained unchanged.
- Retry1 script SHA-256: {retry_script_sha256}; serialization self-test: PASS before the full matrix scan.
- Input: {len(barcodes)} cells, {len(genes)} genes, {len(source_values)} source_sample_id values, {matrix_validation['observed_coordinate_entries']} MatrixMarket coordinate entries.
- Full numeric scan: PASS (dimensions, indices, finite values, integer values, nonnegative counts, strict coordinate order and duplicate-coordinate check).
- Barcode/metadata one-to-one join: PASS; exact order and values match.
- Gene symbols and barcodes: unique; producer celltype_minor retained exactly; no patient_id created; CID4290 and CID4290A not merged.
- total_UMI missing: 0; detected_genes missing: 0; mitochondrial_percent missing: {int(zero_umi.sum())}, exactly where total_UMI=0; zero_UMI true: {int(zero_umi.sum())}.
- MT feature rule: case-sensitive exact MT- prefix; {int(mt_mask.sum())} members; no aliases.
- Start C free bytes: {free_before_preflight}; after write check: {free_after_write_check}; end snapshot before final checkpoint/hash files: {free_at_end_before_final_files}.
- Actual elapsed seconds: {elapsed:.6f}. OS-observed process peak working set bytes: {peak_working_set}.
- Final artifact total bytes (including this checkpoint and excluding only no file): {total_artifact_bytes}.
- S2A output budget: {OUTPUT_BUDGET_BYTES} bytes; within budget: true.

No filtering, deletion, sampling, normalization, HVG, PCA, Leiden, Harmony, BBKNN, doublet, ambient, marker, label evaluation, reference construction, spatial analysis, S2B or S3 was run. qc-threshold-proposal.v1.json is AWAITING_HUMAN_APPROVAL and contains no applied thresholds.

S2B: PENDING. S3: BLOCKED. Patient-level inference: BLOCKED. Machine verdict: PENDING. Biological conclusion: PENDING. This technical integrity result is not biological validation and not a scientific Warrant.
"""

    existing_names = sorted(p.name for p in OUT.iterdir() if p.is_file())
    future_names = existing_names + ["checkpoint.v1.md"]
    checksum_line_bytes = sum(
        len(f"{'0'*64}  {name}\n".encode("utf-8")) for name in future_names
    )
    base_bytes = directory_size(OUT)
    total_guess = base_bytes + checksum_line_bytes
    for _ in range(10):
        checkpoint_bytes = checkpoint_text(total_guess).encode("utf-8")
        new_guess = base_bytes + len(checkpoint_bytes) + checksum_line_bytes
        if new_guess == total_guess:
            break
        total_guess = new_guess
    checkpoint_bytes = checkpoint_text(total_guess).encode("utf-8")
    if base_bytes + len(checkpoint_bytes) + checksum_line_bytes != total_guess:
        raise RuntimeError("FINAL_ARTIFACT_SIZE_FIXED_POINT_FAILED")
    write_bytes_exclusive("checkpoint.v1.md", checkpoint_bytes)

    names_for_checksum = sorted(p.name for p in OUT.iterdir() if p.is_file())
    checksum_text = "".join(
        f"{exact_sha256(OUT / name)}  {name}\n" for name in names_for_checksum
    )
    write_bytes_exclusive("SHA256SUMS.v1.txt", checksum_text.encode("utf-8"))
    final_size = directory_size(OUT)
    if final_size != total_guess:
        raise RuntimeError(f"FINAL_ARTIFACT_SIZE_MISMATCH: actual={final_size}, recorded={total_guess}")
    if final_size > OUTPUT_BUDGET_BYTES:
        raise RuntimeError("FINAL_OUTPUT_BUDGET_EXCEEDED")
    final_free = shutil.disk_usage("C:\\").free
    print(
        json.dumps(
            {
                "status": "COMPLETED",
                "cells": len(barcodes),
                "genes": len(genes),
                "source_sample_ids": len(source_values),
                "nnz_scanned": matrix_validation["observed_coordinate_entries"],
                "full_numeric_scan": "PASS",
                "barcode_metadata_join": "PASS",
                "missingness": overall_missingness,
                "start_C_free_bytes": free_before_preflight,
                "end_C_free_bytes": final_free,
                "elapsed_seconds": time.perf_counter() - script_started_wall,
                "peak_working_set_bytes": process.memory_info().peak_wset,
                "artifact_total_bytes": final_size,
                "output_dir": str(OUT),
                "S2B": "PENDING",
                "S3": "BLOCKED",
                "patient_level_inference": "BLOCKED",
                "machine_verdict": "PENDING",
                "biological_conclusion": "PENDING",
            },
            ensure_ascii=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        failure = {
            "status": "FAILED",
            "failed_at_utc": utc_now(),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "output_dir_exists": OUT.exists(),
            "free_C_bytes": shutil.disk_usage("C:\\").free,
            "S2B": "PENDING",
            "S3": "BLOCKED",
            "patient_level_inference": "BLOCKED",
            "machine_verdict": "PENDING",
            "biological_conclusion": "PENDING",
            "retry_lineage": {
                "failed_output_directory": str(FAILED_OUT),
                "failed_script_sha256": FAILED_SCRIPT_SHA256,
                "failure_record_sha256": FAILED_RECORD_SHA256,
                "failed_directory_preserved": True,
            },
        }
        print(json.dumps(failure, ensure_ascii=True), flush=True)
        if OUT.exists() and shutil.disk_usage("C:\\").free >= WRITE_STOP_BELOW_BYTES:
            try:
                write_json_exclusive("failure.v1.json", failure)
            except Exception:
                pass
        raise
