"""
Unit tests for BioNexus Large-Scale Biological Matrix Memory Estimation & Streaming Engine (bionexus.bigdata).
"""


from bionexus.bigdata import (
    audit_dataset_storage,
    estimate_memory_requirements,
    generate_streaming_plan,
)


def test_estimate_memory_small_dataset():
    """Verify small single-cell dataset (10k cells x 20k genes) is marked SAFE."""
    est = estimate_memory_requirements(
        n_cells=10000,
        n_genes=20000,
        is_sparse=True,
        available_ram_gb=32.0,
    )
    assert est.can_fit_in_memory is True
    assert est.safety_verdict == "SAFE"
    assert est.recommended_strategy == "IN_MEMORY"
    assert est.recommended_ram_gb < 10.0


def test_estimate_memory_massive_dataset_oom_refusal():
    """Verify 2 million cells x 30k genes exceeds typical RAM and is flagged CRITICAL_OOM_REFUSAL."""
    est = estimate_memory_requirements(
        n_cells=2000000,
        n_genes=30000,
        is_sparse=True,
        available_ram_gb=32.0,
    )
    assert est.can_fit_in_memory is False
    assert est.safety_verdict == "CRITICAL_OOM_REFUSAL"
    assert est.recommended_strategy == "HPC_CLUSTER_DISPATCH"
    assert "HPC cluster" in est.actionable_remedy


def test_estimate_memory_dense_vs_sparse():
    """Verify dense matrix memory is ~10x higher than 90% sparse CSR matrix."""
    est_sparse = estimate_memory_requirements(n_cells=50000, n_genes=20000, is_sparse=True, sparsity=0.90)
    est_dense = estimate_memory_requirements(n_cells=50000, n_genes=20000, is_sparse=False)

    assert est_dense.dense_matrix_gb > est_sparse.sparse_csr_gb * 2.0


def test_audit_dataset_storage_h5ad(tmp_path):
    """Verify storage auditing of H5AD file format."""
    dummy_h5ad = tmp_path / "sample.h5ad"
    dummy_h5ad.write_text("DUMMY HDF5 HEADER", encoding="utf-8")

    rep = audit_dataset_storage(dummy_h5ad)
    assert rep.format == "h5ad"
    assert rep.is_chunked is True
    assert rep.supports_out_of_core is True
    assert rep.streaming_compatibility == "PARTIAL_BACKED"


def test_audit_dataset_storage_zarr(tmp_path):
    """Verify storage auditing of Zarr directory store."""
    zarr_dir = tmp_path / "sample.zarr"
    zarr_dir.mkdir()
    (zarr_dir / ".zgroup").write_text("{}", encoding="utf-8")
    (zarr_dir / "data.raw").write_text("DATA", encoding="utf-8")

    rep = audit_dataset_storage(zarr_dir)
    assert rep.format == "zarr"
    assert rep.is_chunked is True
    assert rep.supports_out_of_core is True
    assert rep.streaming_compatibility == "FULL"


def test_audit_dataset_storage_missing_path():
    """Verify missing path handling."""
    rep = audit_dataset_storage("missing_file.h5ad")
    assert rep.format == "missing"
    assert rep.streaming_compatibility == "NONE"


def test_generate_streaming_plan():
    """Verify out-of-core streaming plan generation with chunk division and memory budgeting."""
    plan = generate_streaming_plan(
        total_cells=500000,
        total_genes=30000,
        target_ram_mb=1024.0,  # 1GB RAM budget per chunk
    )
    assert plan.total_cells == 500000
    assert plan.num_chunks > 1
    assert plan.chunk_size < 500000
    assert plan.estimated_memory_per_chunk_mb <= 1500.0
    assert len(plan.streaming_pipeline_steps) >= 4
    assert any("IncrementalPCA" in s for s in plan.streaming_pipeline_steps)
