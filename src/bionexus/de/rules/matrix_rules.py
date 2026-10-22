"""
Expression matrix audit rules for differential expression analysis.

Validates the actual named count source, never just a layer name or sample.
"""

from __future__ import annotations

from typing import Any, List

from bionexus.de.models import (
    CheckRecord,
    CheckStatus,
    DEFinding,
    FindingCategory,
    FindingSeverity,
)


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

        layers = getattr(adata, "layers", {})
        if "counts" in layers:
            source, matrix = "adata.layers['counts']", layers["counts"]
        elif "raw" in layers:
            source, matrix = "adata.layers['raw']", layers["raw"]
        elif getattr(adata, "raw", None) is not None:
            source, matrix = "adata.raw.X", adata.raw.X
        else:
            matrix = getattr(adata, "X", None)
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
