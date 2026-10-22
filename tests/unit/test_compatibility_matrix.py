"""Stable compatibility matrix for mainstream analysis products."""

from __future__ import annotations

import json

from bionexus.cli import main
from bionexus.compatibility_matrix import (
    REQUIRED_PRODUCTS,
    get_product,
    load_compatibility_matrix,
    product_status,
)
from bionexus.schema_registry import validate_document


def test_matrix_lists_required_products_with_closed_statuses():
    matrix = load_compatibility_matrix()
    result = validate_document(matrix, family="compatibility-matrix")
    assert result.valid, result.errors
    ids = {item["id"] for item in matrix["products"]}
    assert set(REQUIRED_PRODUCTS) <= ids
    assert get_product("seurat")["native_runtime"] is False
    assert get_product("seurat")["status"] == "EXPORTED_ARTIFACT_VERIFIED"
    assert product_status("scanpy") == "FIXTURE_VERIFIED"
    assert product_status("cellranger") == "FIXTURE_VERIFIED"
    assert product_status("nf-core") == "FIXTURE_VERIFIED"
    assert "rds" in " ".join(get_product("seurat")["limitations"]).lower()


def test_cli_matrix_json(capsys):
    code = main(["deploy", "matrix", "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == "bionexus.compatibility-matrix.v1"
    assert {item["id"] for item in payload["products"]} >= set(REQUIRED_PRODUCTS)
