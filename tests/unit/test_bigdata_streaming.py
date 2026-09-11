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


def test_online_welford_stats_matches_numpy():
    """Verify online Welford accumulator matches full numpy mean, variance, and sparsity."""
    import numpy as np

    from bionexus.bigdata import OnlineWelfordStats

    rng = np.random.default_rng(123)
    n_features = 15
    chunks = [rng.poisson(lam=5, size=(40, n_features)).astype(float) for _ in range(5)]
    full_matrix = np.vstack(chunks)

    stats = OnlineWelfordStats(n_features=n_features)
    for c in chunks:
        stats.update(c)

    assert stats.count == 200
    np.testing.assert_allclose(stats.mean, np.mean(full_matrix, axis=0), rtol=1e-5)
    np.testing.assert_allclose(stats.variance, np.var(full_matrix, axis=0, ddof=1), rtol=1e-5)
    np.testing.assert_allclose(stats.standard_deviation, np.std(full_matrix, axis=0, ddof=1), rtol=1e-5)
    expected_sparsity = 1.0 - (np.count_nonzero(full_matrix) / full_matrix.size)
    assert abs(stats.sparsity - expected_sparsity) < 1e-4


def test_streaming_pseudobulk_aggregator():
    """Verify StreamingPseudobulkAggregator aggregates correctly across streaming chunks."""
    import numpy as np
    import pandas as pd

    from bionexus.bigdata import StreamingPseudobulkAggregator

    genes = ["gA", "gB", "gC"]
    agg = StreamingPseudobulkAggregator(gene_names=genes, group_keys=["donor", "condition"])

    # Chunk 1: donor1_ctrl, donor2_ctrl
    c1 = np.array([[10, 20, 30], [5, 15, 25]])
    obs1 = pd.DataFrame({"donor": ["d1", "d2"], "condition": ["ctrl", "ctrl"]})
    agg.add_chunk(c1, obs1)

    # Chunk 2: donor1_ctrl again (streaming more cells from same donor), donor1_stim
    c2 = np.array([[15, 25, 35], [50, 60, 70]])
    obs2 = pd.DataFrame({"donor": ["d1", "d1"], "condition": ["ctrl", "stim"]})
    agg.add_chunk(c2, obs2)

    counts_df, design_df = agg.to_dataframe()

    # d1__ctrl should have [10+15, 20+25, 30+35] = [25, 45, 65], cell_count = 2
    assert "d1__ctrl" in counts_df.index
    assert list(counts_df.loc["d1__ctrl"]) == [25, 45, 65]
    assert int(design_df.loc["d1__ctrl", "cell_count"]) == 2

    # d1__stim should have [50, 60, 70], cell_count = 1
    assert "d1__stim" in counts_df.index
    assert list(counts_df.loc["d1__stim"]) == [50, 60, 70]
    assert int(design_df.loc["d1__stim", "cell_count"]) == 1

    # d2__ctrl should have [5, 15, 25], cell_count = 1
    assert "d2__ctrl" in counts_df.index
    assert list(counts_df.loc["d2__ctrl"]) == [5, 15, 25]


def test_stream_raw_count_matrix_audit():
    """Verify stream_raw_count_matrix_audit validates integer counts and catches infractions."""
    import numpy as np
    import pytest

    from bionexus.bigdata import stream_raw_count_matrix_audit
    from bionexus.integrity import ScientificInputError

    # Valid chunks
    valid_chunks = [np.array([[1, 2, 3], [4, 5, 6]]), np.array([[7, 8, 9]])]
    res = stream_raw_count_matrix_audit(valid_chunks, n_features=3)
    assert res["integer_counts_verified"] is True
    assert res["n_samples"] == 3

    # Invalid non-integer chunk
    bad_chunks = [np.array([[1.0, 2.5, 3.0]])]
    with pytest.raises(ScientificInputError, match="non-integer values"):
        stream_raw_count_matrix_audit(bad_chunks, n_features=3)

    # Invalid negative chunk
    negative_chunks = [np.array([[1, -2, 3]])]
    with pytest.raises(ScientificInputError, match="negative values"):
        stream_raw_count_matrix_audit(negative_chunks, n_features=3)

