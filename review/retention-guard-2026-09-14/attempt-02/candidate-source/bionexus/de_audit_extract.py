"""Unified extraction of Scanpy ``rank_genes_groups`` results.

Scanpy stores ``adata.uns['rank_genes_groups']`` fields as numpy structured
arrays (recarrays) whose field names are the compared groups.  Gene identifiers
and numeric columns must be read as whole field values.  Taking ``x[0]`` of a
string identifier truncates ``IFITM1`` to ``I``.

This module does not special-case a single layout.  Dicts, DataFrames, and
structured ndarrays are normalized through one group-keyed table reader.
Parse failures are returned explicitly; callers must not treat an empty frame
as a successful extraction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    import numpy as np
except ImportError:
    np = None

try:
    import pandas as pd
except ImportError:
    pd = None

logger = logging.getLogger(__name__)

__all__ = [
    "RankGenesGroupsExtract",
    "extract_rank_genes_groups",
]

_NAME_FIELDS = ("names", "name", "gene", "genes", "index")
_PVAL_FIELDS = ("pvals", "pvalue", "pvals_adj", "p_val", "p_val_adj")
_PADJ_FIELDS = ("pvals_adj", "padj", "p_val_adj", "qval", "qvals")
_LFC_FIELDS = ("logfoldchanges", "log2fc", "log2FoldChange", "avg_log2FC", "lfc")


@dataclass
class RankGenesGroupsExtract:
    """Result of reading ``adata.uns['rank_genes_groups']``."""

    frame: Any = None
    error: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    source: str = "none"

    @property
    def ok(self) -> bool:
        return self.error is None and self.frame is not None and not _is_empty(self.frame)


def _is_empty(frame: Any) -> bool:
    if frame is None:
        return True
    if pd is not None and isinstance(frame, pd.DataFrame):
        return frame.empty
    return len(frame) == 0


def _as_identifier(value: Any) -> str:
    """Preserve the full identifier. Never take the first character of a string."""
    if value is None:
        return ""
    if np is not None and isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if np is not None and isinstance(value, np.void):
        if value.shape == ():
            try:
                value = value.item()
            except Exception:
                value = value.tolist()
        if isinstance(value, (list, tuple)) and len(value) == 1:
            return _as_identifier(value[0])
        return str(value)
    if isinstance(value, (list, tuple)) and len(value) == 1 and not isinstance(value[0], (str, bytes)):
        return _as_identifier(value[0])
    return str(value)


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if np is not None:
        try:
            if bool(np.isnan(value)):
                return None
        except (TypeError, ValueError):
            pass
        if isinstance(value, np.generic):
            value = value.item()
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_sequence(values: Any) -> List[Any]:
    if values is None:
        return []
    if np is not None and isinstance(values, np.ndarray):
        if values.dtype.names:
            return values.tolist()
        return [_unwrap_element(v) for v in values.tolist()]
    if pd is not None and isinstance(values, pd.Series):
        return [_unwrap_element(v) for v in values.tolist()]
    if isinstance(values, (list, tuple)):
        return [_unwrap_element(v) for v in values]
    if hasattr(values, "tolist"):
        try:
            return [_unwrap_element(v) for v in values.tolist()]
        except Exception:
            pass
    return [_unwrap_element(values)]


def _unwrap_element(value: Any) -> Any:
    if np is not None and isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _group_keys(rec: Any) -> List[str]:
    if rec is None:
        return []
    names = getattr(getattr(rec, "dtype", None), "names", None)
    if names:
        return [str(n) for n in names]
    if pd is not None and isinstance(rec, pd.DataFrame):
        return [str(c) for c in rec.columns]
    if isinstance(rec, dict):
        return [str(k) for k in rec.keys() if str(k) != "params"]
    if hasattr(rec, "keys"):
        try:
            return [str(k) for k in rec.keys() if str(k) != "params"]
        except Exception:
            return []
    return []


def _group_values(rec: Any, key: str) -> List[Any]:
    if rec is None:
        return []
    names = getattr(getattr(rec, "dtype", None), "names", None)
    try:
        if names is not None:
            if key not in names:
                return []
            return _as_sequence(rec[key])
        if pd is not None and isinstance(rec, pd.DataFrame):
            if key not in rec.columns:
                return []
            return _as_sequence(rec[key])
        if isinstance(rec, dict):
            if key not in rec:
                return []
            return _as_sequence(rec[key])
        if hasattr(rec, "__getitem__"):
            return _as_sequence(rec[key])
    except Exception as exc:
        logger.debug("Failed reading group %s: %s", key, exc)
        return []
    return []


def _first_present(mapping: Dict[str, Any], keys: Sequence[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def _normalize_extracted_frame(frame: Any) -> Any:
    if pd is None or frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return frame
    rename = {}
    lower = {str(c).lower(): c for c in frame.columns}
    mapping = {
        "names": "gene",
        "name": "gene",
        "genes": "gene",
        "pvals": "pvalue",
        "pvals_adj": "padj",
        "logfoldchanges": "log2fc",
        "group": "cluster",
        "groups": "cluster",
    }
    for src, dst in mapping.items():
        if src in lower and dst not in frame.columns:
            rename[lower[src]] = dst
    if rename:
        frame = frame.rename(columns=rename)
    if "gene" in frame.columns:
        frame = frame.copy()
        frame["gene"] = [_as_identifier(v) for v in frame["gene"].tolist()]
    return frame


def _records_from_group_tables(
    names_rec: Any,
    pvals_rec: Any,
    padj_rec: Any,
    lfc_rec: Any,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    groups = _group_keys(names_rec)
    if not groups:
        return [], "rank_genes_groups['names'] has no group fields"
    records: List[Dict[str, Any]] = []
    for group in groups:
        genes = _group_values(names_rec, group)
        if not genes:
            return [], f"rank_genes_groups['names'] group '{group}' is empty or unreadable"
        pvals = _group_values(pvals_rec, group) if pvals_rec is not None else []
        padjs = _group_values(padj_rec, group) if padj_rec is not None else []
        lfcs = _group_values(lfc_rec, group) if lfc_rec is not None else []
        for idx, gene in enumerate(genes):
            records.append(
                {
                    "cluster": str(group),
                    "gene": _as_identifier(gene),
                    "pvalue": _as_float(pvals[idx]) if idx < len(pvals) else None,
                    "padj": _as_float(padjs[idx]) if idx < len(padjs) else None,
                    "log2fc": _as_float(lfcs[idx]) if idx < len(lfcs) else None,
                }
            )
    return records, None


def _extract_via_scanpy(adata: Any) -> Optional[RankGenesGroupsExtract]:
    try:
        import scanpy as sc
    except ImportError:
        return None
    getter = getattr(getattr(sc, "get", None), "rank_genes_groups_df", None)
    if getter is None:
        return None
    try:
        frame = getter(adata, group=None)
        frame = _normalize_extracted_frame(frame)
        if frame is None or (pd is not None and isinstance(frame, pd.DataFrame) and frame.empty):
            return RankGenesGroupsExtract(
                frame=frame if frame is not None else (pd.DataFrame() if pd is not None else None),
                error="scanpy.get.rank_genes_groups_df returned no rows",
                params=dict(getattr(adata, "uns", {}).get("rank_genes_groups", {}).get("params") or {}),
                source="scanpy.get.rank_genes_groups_df",
            )
        return RankGenesGroupsExtract(
            frame=frame,
            error=None,
            params=dict(getattr(adata, "uns", {}).get("rank_genes_groups", {}).get("params") or {}),
            source="scanpy.get.rank_genes_groups_df",
        )
    except TypeError:
        rgg = getattr(adata, "uns", {}).get("rank_genes_groups", {}) or {}
        groups = _group_keys(rgg.get("names"))
        if not groups or pd is None:
            return None
        frames = []
        for group in groups:
            part = getter(adata, group=group)
            part = _normalize_extracted_frame(part)
            if part is None or part.empty:
                continue
            if "cluster" not in part.columns:
                part = part.copy()
                part.insert(0, "cluster", group)
            frames.append(part)
        if not frames:
            return None
        return RankGenesGroupsExtract(
            frame=pd.concat(frames, ignore_index=True),
            error=None,
            params=dict(rgg.get("params") or {}),
            source="scanpy.get.rank_genes_groups_df",
        )
    except Exception as exc:
        logger.info("Official Scanpy extractor failed; falling back to unified reader: %s", exc)
        return None


def extract_rank_genes_groups(adata: Any) -> RankGenesGroupsExtract:
    """Extract a DE table from ``adata.uns['rank_genes_groups']``.

    Returns an object whose ``error`` is set on any failure.  An empty table
    without ``error`` is not a valid success.
    """
    if pd is None:
        return RankGenesGroupsExtract(error="pandas is required to extract rank_genes_groups")
    uns = getattr(adata, "uns", None)
    if uns is None or "rank_genes_groups" not in uns:
        return RankGenesGroupsExtract(error="adata.uns has no rank_genes_groups")
    rgg = uns.get("rank_genes_groups")
    params = dict(rgg.get("params") or {}) if isinstance(rgg, dict) else {}
    if not rgg:
        return RankGenesGroupsExtract(
            error="rank_genes_groups is empty",
            params=params,
            source="rank_genes_groups",
        )
    if not isinstance(rgg, dict) or "names" not in rgg:
        return RankGenesGroupsExtract(
            error="rank_genes_groups is present but missing 'names'",
            params=params,
            source="rank_genes_groups",
        )

    official = _extract_via_scanpy(adata)
    if official is not None and official.ok:
        official.params = official.params or params
        return official

    try:
        records, rec_error = _records_from_group_tables(
            rgg.get("names"),
            _first_present(rgg, ("pvals", "pvalue", "p_val")),
            _first_present(rgg, ("pvals_adj", "padj", "p_val_adj")),
            _first_present(rgg, ("logfoldchanges", "log2fc", "log2FoldChange")),
        )
        if rec_error:
            return RankGenesGroupsExtract(frame=pd.DataFrame(), error=rec_error, params=params, source="unified")
        frame = pd.DataFrame.from_records(records)
        if frame.empty:
            return RankGenesGroupsExtract(
                frame=frame,
                error="rank_genes_groups was present but yielded no gene rows",
                params=params,
                source="unified",
            )
        return RankGenesGroupsExtract(frame=frame, error=None, params=params, source="unified")
    except Exception as exc:
        logger.exception("Failed to parse rank_genes_groups")
        return RankGenesGroupsExtract(
            frame=pd.DataFrame(),
            error=f"Failed to parse adata.uns['rank_genes_groups']: {exc}",
            params=params,
            source="unified",
        )
