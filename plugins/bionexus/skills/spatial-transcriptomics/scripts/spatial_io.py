#!/usr/bin/env python3
"""Load SpatialData .zarr or AnnData .h5ad into a single AnnData with coords."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_SRC = Path(__file__).resolve().parents[3] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.backends import require
from bionexus.contracts import GRADE_A, attach_meta


def _looks_like_zarr(path: Path) -> bool:
    if str(path).endswith(".zarr"):
        return True
    if not path.is_dir():
        return False
    return (path / ".zgroup").exists() or (path / "zarr.json").exists()


def list_spatialdata_tables(sdata: Any) -> list[str]:
    tables = getattr(sdata, "tables", None)
    if tables:
        return list(tables.keys())
    if getattr(sdata, "table", None) is not None:
        return ["table"]
    return []


def _table_from_spatialdata(sdata: Any, table_key: Optional[str] = None):
    names = list_spatialdata_tables(sdata)
    if not names:
        raise ValueError("SpatialData object has no table/AnnData to analyze.")
    if len(names) > 1 and not table_key:
        raise ValueError(
            f"SpatialData has multiple tables {names}. Pass --table <name>. Refusing to silently pick the first table."
        )
    key = table_key or names[0]
    tables = getattr(sdata, "tables", None)
    if tables and key in tables:
        adata = tables[key].copy()
    elif key == "table" and getattr(sdata, "table", None) is not None:
        adata = sdata.table.copy()
    else:
        raise ValueError(f"table '{key}' not found. Available: {names}")
    adata.uns["spatialdata_table"] = key
    return adata


def _coords_from_spatialdata(sdata: Any, adata) -> Optional[Any]:
    shapes = getattr(sdata, "shapes", None)
    if not shapes:
        return None
    try:
        frame = next(iter(shapes.values()))
        if hasattr(frame, "geometry"):
            xs = frame.geometry.centroid.x.to_numpy()
            ys = frame.geometry.centroid.y.to_numpy()
            import numpy as np

            coords = np.column_stack([xs, ys])
            if coords.shape[0] == adata.n_obs:
                return coords
    except Exception:
        return None
    return None


def load_spatial_anndata(path: str, table_key: Optional[str] = None):
    """Return AnnData. SpatialData .zarr requires the spatialdata extra."""
    dest = Path(path)
    if _looks_like_zarr(dest):
        require("spatialdata", for_method="load_spatial_anndata")
        import spatialdata as sd

        sdata = sd.read_zarr(str(dest))
        adata = _table_from_spatialdata(sdata, table_key=table_key)
        if "spatial" not in adata.obsm:
            coords = _coords_from_spatialdata(sdata, adata)
            if coords is not None:
                adata.obsm["spatial"] = coords
        adata.uns.setdefault("spatialdata_source", str(dest))
        return adata
    if table_key:
        raise ValueError("--table applies only to SpatialData .zarr, not .h5ad")
    require("scanpy", for_method="load_spatial_anndata")
    import scanpy as sc

    return sc.read_h5ad(str(dest))


def resolve_spatial_key(adata, preferred: str = "spatial") -> str:
    if preferred in adata.obsm:
        return preferred
    for key in adata.obsm.keys():
        name = str(key).lower()
        if "spatial" in name or name in {"x_spatial", "spatial_coords"}:
            return str(key)
    raise ValueError(
        "No spatial coordinates in adata.obsm. Expected 'spatial' (n_obs × 2). "
        "This gold chain does not invent coordinates."
    )


def spatial_load_contract(path: str, adata, spatial_key: str) -> dict:
    return attach_meta(
        {
            "input": path,
            "n_obs": int(adata.n_obs),
            "n_vars": int(adata.n_vars),
            "spatial_key": spatial_key,
            "table_key": adata.uns.get("spatialdata_table"),
            "has_counts_layer": "counts" in adata.layers,
        },
        method="spatialdata.read_zarr" if _looks_like_zarr(Path(path)) else "scanpy.read_h5ad",
        backend="spatialdata" if _looks_like_zarr(Path(path)) else "anndata",
        evidence_grade=GRADE_A,
        limitations=["Coordinates must already exist; this loader does not register images."],
    )
