"""
Unit tests for BioNexus Pre-Tool Guard & Runtime Interception Layer.
"""

from __future__ import annotations

from bionexus.guard import (
    BioNexusGuard,
    GuardStatus,
    inspect_code,
    inspect_command,
)


def test_guard_detects_pseudoreplication() -> None:
    code = """
    import scanpy as sc
    adata = sc.read_h5ad("sample.h5ad")
    sc.tl.rank_genes_groups(adata, groupby="condition", method="wilcoxon")
    """
    guard = BioNexusGuard()
    verdict = guard.inspect_code(code)

    assert verdict.status == GuardStatus.INJECT_CONSTRAINTS
    assert verdict.execution_permitted is True
    assert "BN-F006" in verdict.violation_ids
    assert any("not independent" in g for g in verdict.warrant_guidance)
    assert any("Population-level" in fc for fc in verdict.forbidden_claims)
    assert verdict.suggested_remedy is not None


def test_guard_blocks_raw_count_confusion() -> None:
    code = """
    import scvi
    scvi.model.SCVI.setup_anndata(adata, layer="normalized")
    """
    guard = BioNexusGuard()
    verdict = guard.inspect_code(code)

    assert verdict.status == GuardStatus.BLOCKED
    assert verdict.execution_permitted is False
    assert "BN-F001" in verdict.violation_ids


def test_guard_passes_clean_code() -> None:
    clean_code = """
    import scanpy as sc
    import pandas as pd
    # Aggregate to pseudobulk
    pb = adata.to_df().groupby([adata.obs['donor'], adata.obs['condition']]).sum()
    """
    guard = BioNexusGuard()
    verdict = guard.inspect_code(clean_code)

    assert verdict.status == GuardStatus.PASSED
    assert verdict.execution_permitted is True
    assert len(verdict.violation_ids) == 0


def test_guard_injection_prompt_formatting() -> None:
    code = "sc.tl.rank_genes_groups(adata, groupby='treatment')"
    verdict = inspect_code(code)
    prompt = verdict.format_agent_injection_prompt()

    assert "SCIENTIFIC WARRANT CONSTRAINT INJECTION" in prompt
    assert "FORBIDDEN CLAIMS" in prompt
    assert "CRITICAL INSTRUCTIONS FOR AI AGENT" in prompt


def test_guard_command_inspection() -> None:
    cmd = 'python -c "sc.tl.rank_genes_groups(adata, groupby=\'disease\')"'
    verdict = inspect_command(cmd)

    assert verdict.status == GuardStatus.INJECT_CONSTRAINTS
    assert "BN-F006" in verdict.violation_ids
