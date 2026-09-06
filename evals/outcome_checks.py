"""Check declared planted-signal endpoints, without inferring empirical calibration."""

from __future__ import annotations

import math


def _number(value, name: str) -> float:
    if isinstance(value, (bool, str)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _genes(metadata, key: str) -> list[str]:
    genes = metadata[key]
    if not isinstance(genes, list) or not genes or any(not isinstance(g, str) or not g for g in genes):
        raise ValueError(f"{key} must be a nonempty gene list")
    if len(set(genes)) != len(genes):
        raise ValueError(f"{key} must contain unique genes")
    return genes


def check_de_recovery(table, metadata) -> list[str]:
    """Require rank, adjusted significance and the declared positive effect size."""
    genes = _genes(metadata, "expected_de_genes")
    q_max = _number(metadata["fdr_q_max"], "fdr_q_max")
    fc_min = _number(metadata["min_log2fc"], "min_log2fc")
    if not 0 < q_max <= 1 or fc_min < 0:
        raise ValueError("Invalid DE endpoint thresholds")
    required = {"gene", "pvalue", "padj", "log2FoldChange"}
    if not required.issubset(table.columns) or table["gene"].duplicated().any():
        raise ValueError("DE results need unique genes and pvalue/padj/log2FoldChange columns")
    top = set(table.sort_values("pvalue").head(5)["gene"].astype(str))
    failures = []
    for gene in genes:
        rows = table.loc[table["gene"] == gene]
        if len(rows) != 1 or gene not in top:
            failures.append(f"L3 Failure: Planted DEG '{gene}' absent from top 5 findings")
            continue
        row = rows.iloc[0]
        try:
            p = _number(row["pvalue"], "pvalue")
            q = _number(row["padj"], "padj")
            fc = _number(row["log2FoldChange"], "log2FoldChange")
            if not 0 <= p <= 1 or not 0 <= q < q_max or fc < fc_min:
                failures.append(
                    f"L3 Failure: {gene} p={p}, padj={q}, log2FC={fc}; requires padj < {q_max}, log2FC >= {fc_min}"
                )
        except (TypeError, ValueError) as exc:
            failures.append(f"L3 Failure: {gene} invalid DE endpoint: {exc}")
    return failures


def check_spatial_effects(table, metadata) -> list[str]:
    """Every declared spatial gene must have a finite Moran statistic above the floor."""
    genes = _genes(metadata, "expected_genes")
    minimum = _number(metadata["moran_i_min"], "moran_i_min")
    failures = []
    for gene in genes:
        rows = table.loc[table["gene"] == gene]
        if len(rows) != 1:
            failures.append(f"L3 Failure: {gene} missing or duplicated in spatial results")
            continue
        try:
            value = _number(rows.iloc[0]["morans_i"], "morans_i")
            if value < minimum:
                failures.append(f"L3 Failure: {gene} Moran's I {value} < threshold {minimum}")
        except (TypeError, ValueError) as exc:
            failures.append(f"L3 Failure: {gene} invalid spatial endpoint: {exc}")
    return failures
