"""
BioNexus Large-Scale Biological Data & Out-of-Core Memory Safety Engine.

Provides capabilities for processing multi-million cell datasets:
1. Memory Estimation & Safeguard: Predicts RAM consumption for single-cell & spatial matrices (dense vs sparse) and prevents OOM crashes.
2. Format Auditing: Assesses storage efficiency of H5AD, AnnData Zarr, TileDB-SOMA, and SpatialData Zarr.
3. Out-of-Core Chunking & Streaming: Generates streaming plans for Leiden clustering, PCA, and QC metrics without loading full matrices into memory.
"""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


@dataclass
class MemoryEstimation:
    """Detailed memory estimation for large-scale biological expression matrices."""

    n_cells: int
    n_genes: int
    sparsity: float = 0.90  # Default 90% zero entries for scRNA-seq UMI counts
    precision_bytes: int = 4  # float32 = 4 bytes, float64 = 8 bytes
    dense_matrix_gb: float = 0.0
    sparse_csr_gb: float = 0.0
    layers_overhead_gb: float = 0.0
    graph_and_pca_overhead_gb: float = 0.0
    recommended_ram_gb: float = 0.0
    can_fit_in_memory: bool = True
    available_system_ram_gb: float = 0.0
    safety_verdict: str = "SAFE"
    recommended_strategy: str = "IN_MEMORY"
    actionable_remedy: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def estimate_memory_requirements(
    n_cells: int,
    n_genes: int,
    is_sparse: bool = True,
    sparsity: float = 0.90,
    n_layers: int = 1,
    n_pcs: int = 50,
    n_neighbors: int = 15,
    precision: str = "float32",
    available_ram_gb: Optional[float] = None,
    safety_margin_multiplier: float = 2.5,
) -> MemoryEstimation:
    """
    Estimate RAM requirement for single-cell AnnData / SpatialData matrices with biological overheads.
    Safety margin accounts for Scanpy / SciPy intermediate copies (e.g. log1p, scaling, KNN graph, UMAP).
    """
    bytes_per_elem = 8 if precision == "float64" else 4
    total_elements = n_cells * n_genes

    # 1. Raw matrix size
    dense_bytes = total_elements * bytes_per_elem
    dense_gb = dense_bytes / (1024**3)

    if is_sparse:
        # CSR format: data (bytes_per_elem), indices (int32 = 4 bytes), indptr (int32 or int64)
        nnz = int(total_elements * (1.0 - sparsity))
        indptr_bytes = (n_cells + 1) * (8 if nnz > 2**31 else 4)
        sparse_bytes = (nnz * bytes_per_elem) + (nnz * 4) + indptr_bytes
        matrix_gb = sparse_bytes / (1024**3)
        sparse_csr_gb = matrix_gb
    else:
        matrix_gb = dense_gb
        sparse_csr_gb = matrix_gb

    # 2. Layers overhead (e.g. raw counts + normalized layer)
    layers_overhead_gb = matrix_gb * max(0, (n_layers - 1))

    # 3. PCA & KNN Neighborhood Graph overhead
    # PCA: n_cells * n_pcs * 4 bytes + loadings
    # KNN Graph: sparse adjacency n_cells * n_neighbors * 8 bytes
    pca_bytes = (n_cells * n_pcs * 4) + (n_genes * n_pcs * 4)
    knn_bytes = n_cells * n_neighbors * 12  # data + indices
    graph_and_pca_overhead_gb = (pca_bytes + knn_bytes) / (1024**3)

    # 4. Total Working Memory with algorithm safety margin multiplier
    base_footprint_gb = matrix_gb + layers_overhead_gb + graph_and_pca_overhead_gb
    total_recommended_gb = round(base_footprint_gb * safety_margin_multiplier, 2)

    # 5. Check against host system RAM
    if available_ram_gb is None:
        try:
            import psutil

            sys_ram = round(psutil.virtual_memory().total / (1024**3), 2)
        except Exception:
            sys_ram = 16.0
    else:
        sys_ram = available_ram_gb

    can_fit = total_recommended_gb <= (sys_ram * 0.80)  # 80% RAM utilization cap

    if can_fit:
        verdict = "SAFE"
        strategy = "IN_MEMORY"
        remedy = "Dataset fits comfortably within local memory. Standard in-memory pipeline permitted."
    elif total_recommended_gb <= (sys_ram * 1.5):
        verdict = "RISK_OF_OOM"
        strategy = "BACKED_OR_CHUNKED"
        remedy = (
            f"Dataset requires ~{total_recommended_gb}GB RAM (available: {sys_ram}GB). "
            "Use AnnData backed mode (`backed='r'`) or convert matrix to Zarr chunked format."
        )
    else:
        verdict = "CRITICAL_OOM_REFUSAL"
        strategy = "HPC_CLUSTER_DISPATCH"
        remedy = (
            f"Dataset requires ~{total_recommended_gb}GB RAM, which far exceeds available {sys_ram}GB. "
            "In-memory analysis will crash. Must dispatch to an HPC cluster (bionexus cluster submit) "
            "or use Out-of-Core streaming with TileDB-SOMA / SpatialData Zarr."
        )

    return MemoryEstimation(
        n_cells=n_cells,
        n_genes=n_genes,
        sparsity=sparsity,
        precision_bytes=bytes_per_elem,
        dense_matrix_gb=round(dense_gb, 3),
        sparse_csr_gb=round(sparse_csr_gb, 3),
        layers_overhead_gb=round(layers_overhead_gb, 3),
        graph_and_pca_overhead_gb=round(graph_and_pca_overhead_gb, 3),
        recommended_ram_gb=total_recommended_gb,
        can_fit_in_memory=can_fit,
        available_system_ram_gb=sys_ram,
        safety_verdict=verdict,
        recommended_strategy=strategy,
        actionable_remedy=remedy,
    )


# ==============================================================================
# Storage Format & Big Data Auditor
# ==============================================================================


@dataclass
class StorageAuditReport:
    """Audit of biological dataset storage representation and streaming feasibility."""

    path: str
    format: str  # 'h5ad', 'zarr', 'spatialdata_zarr', 'csv', 'unknown'
    file_size_mb: float
    is_chunked: bool
    supports_out_of_core: bool
    recommended_chunk_size: Tuple[int, int] = (10000, 2000)  # (cells, genes)
    streaming_compatibility: str = "FULL"
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def audit_dataset_storage(path: Union[str, Path]) -> StorageAuditReport:
    """Audit dataset file format, disk layout, and out-of-core streaming readiness."""
    p = Path(path)
    if not p.exists():
        return StorageAuditReport(
            path=str(path),
            format="missing",
            file_size_mb=0.0,
            is_chunked=False,
            supports_out_of_core=False,
            streaming_compatibility="NONE",
            notes=[f"Dataset path '{path}' does not exist."],
        )

    if p.is_file():
        file_size_mb = round(p.stat().st_size / (1024**2), 2)
    else:
        # Directory (e.g. Zarr store)
        total_size = sum(f.stat().st_size for f in p.glob("**/*") if f.is_file())
        file_size_mb = round(total_size / (1024**2), 2)

    notes: List[str] = []
    suffix = p.suffix.lower()

    if suffix in (".zarr",) or (p.is_dir() and (p / ".zgroup").exists()):
        fmt = "zarr"
        is_chunked = True
        out_of_core = True
        comp = "FULL"
        notes.append("Native Zarr chunked storage: supports parallel streaming and out-of-core Dask computation.")
    elif suffix in (".h5ad", ".h5"):
        fmt = "h5ad"
        is_chunked = True  # HDF5 has internal chunking
        out_of_core = True  # Supports backed='r'
        comp = "PARTIAL_BACKED"
        notes.append("HDF5 AnnData format: supports backed='r' mode for sequential out-of-core operations.")
    elif suffix in (".csv", ".tsv", ".txt"):
        fmt = "flat_text"
        is_chunked = False
        out_of_core = False
        comp = "POOR"
        notes.append("Uncompressed flat text table: inefficient for >50k cells. Convert to H5AD or Zarr immediately.")
    else:
        fmt = "unknown"
        is_chunked = False
        out_of_core = False
        comp = "UNKNOWN"
        notes.append(f"Unrecognized format extension: '{suffix}'")

    return StorageAuditReport(
        path=str(p.resolve()),
        format=fmt,
        file_size_mb=file_size_mb,
        is_chunked=is_chunked,
        supports_out_of_core=out_of_core,
        streaming_compatibility=comp,
        notes=notes,
    )


# ==============================================================================
# Streaming Plan Generator
# ==============================================================================


@dataclass
class StreamingPlan:
    """Execution plan for out-of-core streaming analysis."""

    total_cells: int
    chunk_size: int
    num_chunks: int
    estimated_memory_per_chunk_mb: float
    streaming_pipeline_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_streaming_plan(
    total_cells: int,
    total_genes: int,
    target_ram_mb: float = 2048.0,  # Cap at 2GB per chunk
) -> StreamingPlan:
    """Calculate optimal chunk size and chunked execution workflow for huge datasets."""
    # Approximate bytes per cell (sparse matrix + annotations)
    bytes_per_cell = (total_genes * 0.10 * 8) + 200  # ~10% nnz
    cells_per_chunk = max(1000, int((target_ram_mb * 1024**2) / (bytes_per_cell * 3.0)))
    cells_per_chunk = min(total_cells, cells_per_chunk)

    num_chunks = math.ceil(total_cells / cells_per_chunk)
    mem_per_chunk_mb = round((cells_per_chunk * bytes_per_cell * 3.0) / (1024**2), 1)

    steps = [
        "1. Streamed QC Filter: compute n_counts, n_genes, and mito_percent per chunk without full memory load.",
        "2. Streamed HVG Selection: compute mean and dispersion across chunks using online Welford accumulator.",
        "3. Incremental PCA: fit sklearn.decomposition.IncrementalPCA in mini-batches across chunks.",
        "4. Approximate Nearest Neighbors: build HNSW or Annoy index on incremental PCA embeddings.",
        "5. Leiden Clustering: execute community detection on the constructed sparse neighborhood graph.",
    ]

    return StreamingPlan(
        total_cells=total_cells,
        chunk_size=cells_per_chunk,
        num_chunks=num_chunks,
        estimated_memory_per_chunk_mb=mem_per_chunk_mb,
        streaming_pipeline_steps=steps,
    )
