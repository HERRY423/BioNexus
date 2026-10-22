"""Machine-readable analysis-product compatibility matrix.

The matrix is a packaged contract. Status values are closed-vocabulary and
must not be paraphrased as vendor certification.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from bionexus.schema_registry import SchemaError, load_json_schema, validate_document

MATRIX_FILE = "compatibility-matrix.v1.json"
REQUIRED_PRODUCTS = ("scanpy", "seurat", "deseq2", "edger", "cellranger", "nf-core")
VERIFIED_ADAPTER_STATUSES = frozenset({"FIXTURE_VERIFIED", "EXPORTED_ARTIFACT_VERIFIED"})


def load_compatibility_matrix() -> Dict[str, Any]:
    """Load and validate the packaged compatibility matrix."""
    matrix = load_json_schema(MATRIX_FILE)
    result = validate_document(matrix, family="compatibility-matrix")
    if not result.valid:
        raise SchemaError("compatibility matrix failed its own schema: " + "; ".join(result.errors))
    ids = [str(item.get("id")) for item in matrix.get("products") or []]
    if len(ids) != len(set(ids)):
        raise SchemaError("compatibility matrix contains duplicate product ids")
    missing = [name for name in REQUIRED_PRODUCTS if name not in ids]
    if missing:
        raise SchemaError("compatibility matrix missing required products: " + ", ".join(missing))
    return matrix


def list_products() -> List[Dict[str, Any]]:
    return list(load_compatibility_matrix()["products"])


def get_product(product_id: str) -> Dict[str, Any]:
    needle = product_id.strip().lower()
    for item in list_products():
        if str(item.get("id")).lower() == needle:
            return item
    raise SchemaError(f"unknown compatibility product: {product_id!r}")


def product_status(product_id: str) -> str:
    return str(get_product(product_id)["status"])


def matrix_summary(*, product: Optional[str] = None) -> Dict[str, Any]:
    matrix = load_compatibility_matrix()
    products = list_products()
    if product:
        products = [get_product(product)]
    return {
        "schema_version": matrix["schema_version"],
        "bionexus_version": matrix["bionexus_version"],
        "honesty_note": matrix.get("honesty_note"),
        "products": [
            {
                "id": item["id"],
                "status": item["status"],
                "native_runtime": item["native_runtime"],
                "versions": item["versions"],
                "input_formats": item["input_formats"],
                "acceptance_id": item["acceptance_id"],
                "limitations": item["limitations"],
            }
            for item in products
        ],
    }
