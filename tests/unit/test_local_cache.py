"""
Unit tests for BioNexus Air-Gapped Local Knowledge Cache.
"""

from __future__ import annotations

import time

from bionexus.local_cache import BioLocalCache


def test_local_cache_gene_lookup_symbol() -> None:
    cache = BioLocalCache()
    gene = cache.get_gene("TP53")

    assert gene is not None
    assert gene["symbol"] == "TP53"
    assert gene["ensembl_id"] == "ENSG00000141510"
    assert gene["uniprot_id"] == "P04637"
    assert gene["chromosome"] == "17"


def test_local_cache_gene_lookup_synonym_and_ensembl() -> None:
    cache = BioLocalCache()

    # Synonym lookup
    gene_syn = cache.get_gene("HER1")
    assert gene_syn is not None
    assert gene_syn["symbol"] == "EGFR"

    gene_p53 = cache.get_gene("p53")
    assert gene_p53 is not None
    assert gene_p53["symbol"] == "TP53"

    # Ensembl ID lookup
    gene_ens = cache.get_gene("ENSG00000146648")
    assert gene_ens is not None
    assert gene_ens["symbol"] == "EGFR"


def test_local_cache_cell_markers() -> None:
    cache = BioLocalCache()

    t_markers = cache.get_markers("T cell")
    assert "CD3D" in t_markers
    assert "CD3E" in t_markers

    b_markers = cache.get_markers("B cell")
    assert "CD19" in b_markers
    assert "MS4A1" in b_markers

    nk_markers = cache.get_markers("NK cell")
    assert "NCAM1" in nk_markers


def test_local_cache_pathways() -> None:
    cache = BioLocalCache()
    pathways = cache.get_pathways_for_gene("TP53")

    assert len(pathways) >= 2
    st_ids = [p["stId"] for p in pathways]
    assert "R-HSA-1640170" in st_ids  # Cell Cycle
    assert "R-HSA-109581" in st_ids   # Apoptosis


def test_local_cache_pdb_summary() -> None:
    cache = BioLocalCache()
    pdb_tp53 = cache.get_pdb_summary("TP53")

    assert pdb_tp53 is not None
    assert pdb_tp53["pdb_id"] == "1TUP"
    assert pdb_tp53["uniprot_id"] == "P04637"


def test_local_cache_kv_ttl() -> None:
    cache = BioLocalCache()
    cache.set_kv("temp_key", {"data": 123}, ttl_seconds=0.1)

    assert cache.get_kv("temp_key") == {"data": 123}
    time.sleep(0.15)
    assert cache.get_kv("temp_key") is None
