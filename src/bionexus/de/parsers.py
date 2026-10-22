"""
Parsers, loaders, and column heuristics for differential expression inputs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional, Sequence, Union

from bionexus.de_audit_extract import extract_rank_genes_groups

if TYPE_CHECKING:
    import pandas as pd
else:
    try:
        import pandas as pd
    except ImportError:
        pd = None

logger = logging.getLogger(__name__)

DONOR_KEYWORDS = [
    "donor",
    "donor_id",
    "sample",
    "sample_id",
    "patient",
    "patient_id",
    "subject",
    "mouse_id",
    "specimen",
]
CONDITION_KEYWORDS = [
    "condition",
    "group",
    "disease",
    "status",
    "treatment",
    "stim",
    "genotype",
    "phenotype",
    "cohort",
]
CELLTYPE_KEYWORDS = [
    "cell_type",
    "celltype",
    "cluster",
    "leiden",
    "louvain",
    "seurat_clusters",
    "annotation",
    "cell_label",
    "lineage",
]
BATCH_KEYWORDS = [
    "batch",
    "pool",
    "lane",
    "run",
    "experiment",
    "date",
    "seq_run",
    "gem_group",
    "orig.ident",
]


def _match_column(cols: Iterable[str], keywords: Sequence[str]) -> Optional[str]:
    """Find best matching column name ignoring case and punctuation."""
    lower_map = {c.lower().replace("_", "").replace("-", ""): c for c in cols}
    for kw in keywords:
        clean_kw = kw.lower().replace("_", "").replace("-", "")
        if clean_kw in lower_map:
            return lower_map[clean_kw]
    # Substring search
    for kw in keywords:
        clean_kw = kw.lower().replace("_", "").replace("-", "")
        for k_norm, orig in lower_map.items():
            if clean_kw in k_norm:
                return orig
    return None


def _load_anndata(path: Union[str, Path]) -> Any:
    """Load an AnnData object from an .h5ad path."""
    try:
        import anndata as ad
        return ad.read_h5ad(path)
    except Exception as e:
        raise RuntimeError(f"Failed to load AnnData from {path}: {e}")


def _load_dataframe(obj: Union[pd.DataFrame, str, Path]) -> pd.DataFrame:
    """Load a pandas DataFrame from memory or file."""
    if pd is not None and isinstance(obj, pd.DataFrame):
        return obj
    path = Path(obj)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    if pd is None:
        raise RuntimeError("pandas is required to load tabular data")
    if path.suffix.lower() in (".tsv", ".txt"):
        return pd.read_csv(path, sep="\t")
    return pd.read_csv(path)


def _extract_de_from_anndata_uns(adata: Any) -> pd.DataFrame:
    """Extract a DE table from Scanpy uns; empty frame only when error is reported by caller."""
    extracted = extract_rank_genes_groups(adata)
    if extracted.error or extracted.frame is None:
        logger.info("rank_genes_groups extraction failed: %s", extracted.error)
        return pd.DataFrame() if pd is not None else None
    return extracted.frame
