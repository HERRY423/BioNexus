"""
Expression matrix audit rules for differential expression analysis.

Validates the actual named count source, never just a layer name or sample.
"""

from __future__ import annotations

from typing import Any, List

import numpy as np
import pandas as pd

from bionexus.de.models import (
    CheckRecord,
    CheckStatus,
    DEFinding,
    FindingCategory,
    FindingSeverity,
)
from bionexus.de.pseudobulk_counts import PseudobulkLibraries, collect_libraries
from bionexus.de.rules.sample_design import _design


def _count_source(adata: Any) -> tuple[str, Any, Any]:
    layers = getattr(adata, "layers", {})
    for name in ("counts", "raw"):
        if name in layers:
            return f"adata.layers['{name}']", layers[name], getattr(adata, "var_names", None)
    raw = getattr(adata, "raw", None)
    if raw is not None:
        return "adata.raw.X", raw.X, getattr(raw, "var_names", None)
    return "adata.X", getattr(adata, "X", None), getattr(adata, "var_names", None)


def _audit_expression_matrix(
    adata: Any,
    findings: List[DEFinding],
    checks: List[CheckRecord],
) -> None:
    """Validate the actual named count source, never just a layer name/sample.

    This establishes numerical availability only, not which matrix an
    external analysis used or whether its producer is authenticated.
    """
    source = "adata.X"
    try:
        from bionexus.integrity import ScientificInputError, require_raw_count_matrix

        source, matrix, _ = _count_source(adata)
        if matrix is None:
            checks.append(
                CheckRecord(
                    check_id="input_count_type",
                    title="原始整数计数层",
                    status=CheckStatus.MISSING_EVIDENCE,
                    summary=f"{source} 缺失；计数输入未评估。",
                    required_for_pass=True,
                )
            )
            return
        try:
            require_raw_count_matrix(matrix, label=source)
        except ScientificInputError as exc:
            findings.append(
                DEFinding(
                    rule_id="BFA-002",
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.INPUT_COUNT_TYPE,
                    title="输入矩阵不满足计数要求 (Invalid Count Input)",
                    impact_on_conclusion=(
                        f"{source} 未通过完整计数检查：{exc}。"
                        "该输入不能作为有效计数证据；层名不证明数据类型。"
                    ),
                    step_or_location=source,
                    minimal_fix=(
                        "从原始来源恢复并核对非负有限整数 counts，"
                        "保留输入来源和实际分析所用矩阵记录；不要四舍五入变换数据或静默切换层。"
                    ),
                    evidence_data={"checked_source": source, "validation_error": str(exc)},
                )
            )
            checks.append(
                CheckRecord(
                    check_id="input_count_type",
                    title="原始整数计数层",
                    status=CheckStatus.ISSUE_FOUND,
                    summary=f"{source} 计数检查失败：{exc}",
                    required_for_pass=True,
                )
            )
            return
    except Exception as exc:
        checks.append(
            CheckRecord(
                check_id="input_count_type",
                title="原始整数计数层",
                status=CheckStatus.PARSE_FAILED,
                summary=f"{source} 无法检查：{type(exc).__name__}；不视为通过。",
                required_for_pass=True,
            )
        )
        return
    checks.append(
        CheckRecord(
            check_id="input_count_type",
            title="原始整数计数层",
            status=CheckStatus.ASSESSED,
            summary=(
                f"已完整检查 {source}：非空、有限、非负、整数值。"
                "这仅确认可用计数，不证明实际分析使用了该矩阵。"
            ),
            required_for_pass=True,
        )
    )


def _measure_count_strata(
    adata: Any, strata: list[dict[str, Any]], *, d_col: str, c_col: str, ct_col: str | None, b_col: str | None,
) -> tuple[dict[str | None, dict[str, Any]], PseudobulkLibraries | None]:
    """Measure each stratum even without DE estimates or a signed claim."""
    source, matrix, _ = _count_source(adata)
    measured: dict[str | None, dict[str, Any]] = {}
    selected = None
    for stratum in strata:
        levels = tuple(stratum["donors_by_condition"])
        if len(levels) != 2 or stratum["row_unit"] != "cell":
            continue
        ct = stratum["cell_type"]
        try:
            libraries = collect_libraries(matrix, adata.obs, d_col=d_col, c_col=c_col, ct_col=ct_col,
                                          cell_type=ct, levels=levels, min_cells=stratum["min_cells_per_donor"])
            measured[ct] = {**libraries.power_inputs(), "count_source": source}
            if libraries.zero_libraries:
                # An all-zero bridging sample cannot make a batch-adjusted
                # contrast estimable. Rebuild the design from usable libraries.
                obs = adata.obs
                if ct is not None and ct_col:
                    obs = obs.loc[obs[ct_col].astype("string").eq(ct).fillna(False)]
                sample = pd.DataFrame({"condition": obs[c_col].astype("string"), "donor": obs[d_col].astype("string")})
                if b_col:
                    sample["batch"] = obs[b_col].astype("string").replace(r"^\s*$", pd.NA, regex=True)
                valid = pd.DataFrame({"condition": libraries.condition, "donor": pd.Series(libraries.donors, dtype=str)})
                sample = sample.drop_duplicates().merge(valid, on=["condition", "donor"])
                measured[ct]["design"] = _design(sample, list(levels), "donor", "condition", "batch" if b_col else None)
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            measured[ct] = {"reason": str(exc), "count_source": source}
            continue
        if len(strata) == 1:
            selected = libraries
    return measured, selected


def _comparison_rows(table: pd.DataFrame, *, case: str | None, ref: str | None,
                     cell_type: str | None, ct_col: str, c_col: str, obs: pd.DataFrame,
                     rgg_params: dict | None) -> tuple[pd.DataFrame, dict[str, str]]:
    """Restrict to the requested test before resolving missing labels."""
    labels = {"numerator": case, "denominator": ref, "cell_type": cell_type}
    columns = {key: key for key in labels if key in table}
    if rgg_params is not None:
        if rgg_params.get("groupby") != c_col or "cluster" not in table:
            raise ValueError("Scanpy 比较组未绑定到条件列。")
        columns["numerator"] = "cluster"
        reference = rgg_params.get("reference", "rest")
        if reference != "rest":
            if ref is not None and str(ref) != str(reference):
                raise ValueError("指定的 reference 与 Scanpy 记录不同。")
            labels["denominator"] = reference
    elif "cell_type" not in columns and ct_col in table:
        columns["cell_type"] = ct_col

    for key, col in columns.items():
        if labels[key] is not None:
            table = table.loc[table[col].astype("string").eq(str(labels[key])).fillna(False)]
    if table.empty:
        raise ValueError("结果表没有与所给细胞类型和有序对比一致的行。")
    for key, col in columns.items():
        if labels[key] is None:
            levels = table[col].dropna().astype(str).unique()
            if len(levels) != 1 or table[col].isna().any():
                raise ValueError(f"结果表中 {key} 不唯一或缺失，请指定比较范围。")
            labels[key] = levels[0]
    if rgg_params is not None and rgg_params.get("reference", "rest") == "rest":
        # A one-versus-rest estimate is a two-level contrast only in a
        # strictly binary dataset, even if the caller names a reference.
        levels = set(obs[c_col].dropna().astype(str))
        numerator = str(labels["numerator"])
        if len(levels) != 2 or numerator not in levels:
            raise ValueError("Scanpy rest 含多个或未知条件，不能还原指定的二组对比。")
        reference = (levels - {numerator}).pop()
        if ref is not None and str(ref) != reference:
            raise ValueError("Scanpy rest 与指定的参考水平不同。")
        labels["denominator"] = reference
    if labels["cell_type"] is None and ct_col in obs:
        levels = obs[ct_col].dropna().astype(str).unique()
        if len(levels) == 1:
            labels["cell_type"] = levels[0]
    if any(value is None or not str(value).strip() for value in labels.values()):
        raise ValueError("缺少细胞类型或 case/reference 有序对比。")
    resolved = {key: str(value) for key, value in labels.items()}
    if resolved["numerator"] == resolved["denominator"]:
        raise ValueError("case 和 reference 必须是不同水平。")
    return table, resolved


def _compare_counts(matrix: Any, obs: pd.DataFrame, var_names: Any, table: pd.DataFrame,
                    labels: dict[str, str], *, d_col: str, c_col: str, ct_col: str,
                    min_cells_per_donor: int, top_n: int = 200, min_mean_cpm: float = 1.0,
                    libraries: PseudobulkLibraries | None = None) -> dict[str, Any]:
    """Compare the largest reported effects with donor-averaged log2(CPM+1)."""
    ids = pd.Index(var_names)
    if len(ids) != matrix.shape[1] or ids.hasnans or not ids.astype(str).is_unique:
        raise ValueError("计数矩阵的基因标识缺失、重复或与列数不一致。")
    if len(obs) != matrix.shape[0]:
        raise ValueError("细胞元数据与计数矩阵行数不一致。")
    indexed_columns = {str(c).casefold(): c for c in table}
    gene_col = next((indexed_columns[c] for c in ("gene", "symbol", "names", "gene_name", "gene_id", "id")
                     if c in indexed_columns), None)
    lfc_col = next((indexed_columns[c] for c in ("log2_fold_change", "log2foldchange", "logfoldchanges",
                    "log2fc", "avg_log2fc", "logfc", "lfc") if c in indexed_columns), None)
    if lfc_col is None or (gene_col is None and pd.api.types.infer_dtype(table.index) != "string"):
        raise ValueError("缺少明确的基因名或 logFC 列。")
    genes = pd.Index(table[gene_col] if gene_col is not None else table.index)
    if genes.hasnans or not genes.astype(str).is_unique:
        raise ValueError("同一对比内的结果基因标识缺失或重复。")
    effects = pd.to_numeric(table[lfc_col], errors="coerce")
    if pd.api.types.is_complex_dtype(effects) or pd.api.types.is_bool_dtype(effects):
        raise ValueError("logFC 应为实数。")
    reported = pd.Series(effects.to_numpy(dtype=float, na_value=np.nan), index=genes.astype(str))
    groups = (labels["numerator"], labels["denominator"])
    if libraries is None or libraries.cell_type != labels["cell_type"] or set(libraries.levels) != set(groups):
        libraries = collect_libraries(matrix, obs, d_col=d_col, c_col=c_col, ct_col=ct_col,
                                      cell_type=labels["cell_type"], levels=groups, min_cells=min_cells_per_donor)
    n_donors = libraries.donors_by_condition
    result = {"donors_per_group": n_donors, "zero_libraries": libraries.zero_libraries, **labels,
              "top_n": top_n, "min_mean_cpm": min_mean_cpm, "min_cells_per_donor": min_cells_per_donor}
    if min(n_donors.values()) < 2:
        return {**result, "status": "NOT_ESTIMABLE", "reason": "至少一组不足两个有可用计数的合格供体。"}
    cpm = libraries.counts / libraries.counts.sum(axis=1, keepdims=True) * 1e6
    case, ref = groups
    log_cpm = np.log2(cpm + 1.)
    diff = log_cpm[libraries.condition == case].mean(0) - log_cpm[libraries.condition == ref].mean(0)
    expressed = cpm.mean(0) >= min_mean_cpm
    # Ties have no direction. Exclude them before choosing the top genes.
    usable = expressed & ~np.isclose(diff, 0, rtol=0, atol=1e-12)
    measured = pd.Series(diff[usable], index=ids.astype(str)[usable])
    reported = reported.loc[np.isfinite(reported) & reported.ne(0) & reported.index.isin(measured.index)]
    chosen = reported.loc[reported.abs().nlargest(top_n).index]
    if chosen.empty:
        return {**result, "status": "NOT_ESTIMABLE", "reason": "没有共同表达且方向可比较的基因。"}
    agree = np.sign(chosen) == np.sign(measured.loc[chosen.index])
    return {**result, "status": "COMPARED", "n_genes": len(chosen),
            "sign_agreement": float(agree.mean()), "discordant_genes": chosen.index[~agree].tolist()[:20]}


def _audit_lfc_concordance(adata: Any, de_df: pd.DataFrame | None, findings: list[DEFinding],
                           checks: list[CheckRecord], *, d_col: str | None, c_col: str | None,
                           ct_col: str | None, cell_type: str | None = None, case: str | None = None,
                           ref: str | None = None, min_cells_per_donor: int = 1,
                           rgg_params: dict | None = None, libraries: PseudobulkLibraries | None = None) -> dict[str, Any]:
    """Record a direction diagnostic for an explicit cell type and ordered comparison."""
    from bionexus.statistical_rules import STATISTICAL_THRESHOLDS

    try:
        source, matrix, var_names = _count_source(adata)
        obs = getattr(adata, "obs", None)
        if (de_df is None or obs is None or d_col is None or c_col is None or ct_col is None
                or not {d_col, c_col, ct_col} <= set(obs)):
            raise ValueError("缺少结果表或细胞类型、供体、条件元数据。")
        table, labels = _comparison_rows(de_df, case=case, ref=ref, cell_type=cell_type, ct_col=ct_col,
                                         c_col=c_col, obs=obs, rgg_params=rgg_params)
        input_check = next((check for check in checks if check.check_id == "input_count_type"), None)
        if input_check is None:
            _audit_expression_matrix(adata, findings, checks)
            input_check = checks[-1]
        if input_check.status != CheckStatus.ASSESSED or var_names is None:
            raise ValueError("缺少经检查的原始计数或该矩阵的基因标识。")
        result = _compare_counts(matrix, obs, var_names, table, labels, d_col=d_col, c_col=c_col, ct_col=ct_col,
                                 min_cells_per_donor=min_cells_per_donor, libraries=libraries)
        result["count_source"] = source
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        result = {"status": "NOT_ESTIMABLE", "reason": str(exc)}
    check_status = CheckStatus.MISSING_EVIDENCE
    if result["status"] == "COMPARED":
        n_genes, agreement = result["n_genes"], result["sign_agreement"]
        summary = f"{n_genes} 个可比较基因的方向一致率为 {agreement:.1%}。"
        min_genes = STATISTICAL_THRESHOLDS["lfc_sign_agreement_min_genes"]
        if n_genes < min_genes:
            summary += f"少于诊断阈值 {min_genes} 个基因，仅报告观察值。"
        elif agreement < STATISTICAL_THRESHOLDS["lfc_sign_agreement_advisory_below"]:
            reversed_signs = agreement < STATISTICAL_THRESHOLDS["lfc_sign_agreement_reversal_below"]
            findings.append(DEFinding(
                rule_id="BFA-016",
                severity=FindingSeverity.HIGH_IMPACT if reversed_signs else FindingSeverity.ADVISORY,
                category=FindingCategory.CLAIM_BOUNDARY,
                title="原始计数与 DE 表的效应方向不一致",
                impact_on_conclusion=summary + ("需核验 case/reference 是否颠倒。" if reversed_signs else
                                                 "细胞子集、归一化或模型协变量可能影响方向。"),
                step_or_location=source,
                minimal_fix="核对有序对比、细胞子集、计数层、模型协变量和导出的基因标识。",
                evidence_data=result.copy(),
            ))
            check_status = CheckStatus.ISSUE_FOUND
        else:
            check_status = CheckStatus.ASSESSED
    else:
        summary = result["reason"]
    checks.append(CheckRecord(check_id="lfc_concordance", title="原始计数效应方向复核",
                              status=check_status, summary=summary, required_for_pass=False))
    return result
