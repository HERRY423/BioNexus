"""
DE results table audit rules for differential expression analysis.

Audits probability validity, pseudoreplication p-value signatures, and FDR control.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

from bionexus.de.models import (
    CheckRecord,
    CheckStatus,
    DEFinding,
    FindingCategory,
    FindingSeverity,
    PIDecisionItem,
)
from bionexus.de.parsers import _match_column

if TYPE_CHECKING:
    import pandas as pd
else:
    try:
        import pandas as pd
    except ImportError:
        pd = None

logger = logging.getLogger(__name__)


def _audit_de_table(
    de_df: pd.DataFrame,
    findings: List[DEFinding],
    pi_decisions: List[PIDecisionItem],
    checks: List[CheckRecord],
    fdr_threshold: float = 0.05,
    claim_text: Optional[str] = None,
) -> None:
    """Audit DE results table for probability validity, pseudoreplication p-value signatures, and FDR control."""
    p_col = _match_column(de_df.columns, ["pvalue", "p_val", "pval", "p.value", "pvals"])
    padj_col = _match_column(de_df.columns, ["padj", "p_val_adj", "qval", "p.adjusted", "fdr", "pvals_adj"])

    # Missing estimates are not negative results. Validate before any comparisons,
    # and use the same numeric view throughout without mutating the input table.
    de_df = de_df.copy()
    probability_status = CheckStatus.ASSESSED
    probability_details = []
    for column in dict.fromkeys(c for c in (p_col, padj_col) if c):
        original = de_df[column]
        numeric = pd.to_numeric(original, errors="coerce")
        invalid = original.notna() & numeric.isna()
        # Booleans are not probability estimates, even though Python casts them.
        invalid |= original.map(pd.api.types.is_bool)
        # Complex ordering is defined by some array libraries but has no
        # interpretation as a real probability, including a zero imaginary part.
        if pd.api.types.is_complex_dtype(numeric.dtype):
            invalid |= numeric.notna()
            numeric = pd.Series(float("nan"), index=original.index)
        missing_count = int(original.isna().sum())
        finite_count = int(numeric.between(0.0, 1.0).sum())
        probability_details.append(
            f"{column}: finite_in_range={finite_count}, missing={missing_count}, invalid={int(invalid.sum())}"
        )
        if invalid.any():
            probability_status = CheckStatus.PARSE_FAILED
        elif not numeric.notna().any() and probability_status != CheckStatus.PARSE_FAILED:
            probability_status = CheckStatus.MISSING_EVIDENCE
        de_df[column] = numeric

    if probability_status != CheckStatus.ASSESSED:
        checks.append(CheckRecord(
            check_id="fdr_and_testing", title="FDR / 多重检验",
            status=probability_status, required_for_pass=True,
            summary="概率列无可估计值或含非法文本；不能解释为阴性结果。" + "; ".join(probability_details),
        ))
        return

    # 0. Probability Range and Numeric Validity Check
    if p_col and pd is not None:
        try:
            p_numeric = pd.to_numeric(de_df[p_col], errors="coerce")
            if (p_numeric < 0.0).any() or (p_numeric > 1.0).any():
                min_p = float(p_numeric.min())
                max_p = float(p_numeric.max())
                findings.append(
                    DEFinding(
                        rule_id="BFA-003c",
                        severity=FindingSeverity.HIGH_IMPACT,
                        category=FindingCategory.FDR_AND_TESTING,
                        title="统计量数值非法：P 值超出有效概率区间 [0, 1] (Invalid P-value Range)",
                        impact_on_conclusion=(
                            f"检测到 P 值超出 [0, 1] 范围（最小 p={min_p}, 最大 p={max_p}）。"
                            "概率统计量必须在 [0, 1] 区间内，负数或 >1 的 P 值表明数据损坏或模型输出异常。"
                        ),
                        step_or_location=f"DE table column '{p_col}'",
                        minimal_fix="核查生成 DE 表的统计模型与提取脚本，确保输出了正确的未越界 p-value。",
                        evidence_data={"column": p_col, "min_p": min_p, "max_p": max_p},
                    )
                )
        except Exception as exc:
            logger.info("P-value range check exception: %s", exc)

    if padj_col and pd is not None:
        try:
            padj_numeric = pd.to_numeric(de_df[padj_col], errors="coerce")
            if (padj_numeric < 0.0).any() or (padj_numeric > 1.0).any():
                min_padj = float(padj_numeric.min())
                max_padj = float(padj_numeric.max())
                findings.append(
                    DEFinding(
                        rule_id="BFA-003c",
                        severity=FindingSeverity.HIGH_IMPACT,
                        category=FindingCategory.FDR_AND_TESTING,
                        title="统计量数值非法：FDR/调整 P 值超出有效概率区间 [0, 1] (Invalid Adjusted P-value Range)",
                        impact_on_conclusion=(
                            f"检测到调整后 P 值超出 [0, 1] 范围（最小 padj={min_padj}, 最大 padj={max_padj}）。"
                            "多重检验校正后的 q/padj 必须在 [0, 1] 区间内，负数或非法值表明校正程序故障。"
                        ),
                        step_or_location=f"DE table column '{padj_col}'",
                        minimal_fix="核查多重检验校正步骤（如 Benjamini-Hochberg），确保校正值落在 [0, 1] 闭区间。",
                        evidence_data={"column": padj_col, "min_padj": min_padj, "max_padj": max_padj},
                    )
                )
        except Exception as exc:
            logger.info("Padj range check exception: %s", exc)

    # 1. Check Multiple Testing Correction / FDR
    if not padj_col and p_col:
        findings.append(
            DEFinding(
                rule_id="BFA-003",
                severity=FindingSeverity.HIGH_IMPACT,
                category=FindingCategory.FDR_AND_TESTING,
                title="缺失 FDR 多重假设检验校正 (Missing FDR / Adjusted P-value)",
                impact_on_conclusion="差异分析结果表中仅报告了原始 p 值，未进行 Benjamini-Hochberg (FDR) 校正。单细胞转录组同时检验数万个基因，若仅以 p < 0.05 筛选，存在成百上千个假阳性基因被当做真实生物学发现的风险。",
                step_or_location="Differential Expression Post-processing",
                minimal_fix=(
                    "from statsmodels.stats.multitest import multipletests\n"
                    f"_, padj, _, _ = multipletests(de_df['{p_col}'], method='fdr_bh')\n"
                    "de_df['padj'] = padj\n"
                    "sig_degs = de_df[de_df['padj'] < 0.05]"
                ),
            )
        )
    elif padj_col and p_col:
        # Check for excessive uncorrected reporting vs honest negative finding
        try:
            sig_raw = (de_df[p_col] < 0.05).sum()
            sig_adj = (de_df[padj_col] < fdr_threshold).sum()
            if sig_raw > 100 and sig_adj == 0:
                is_honest_null = False
                if claim_text:
                    txt = claim_text.lower()
                    null_cues = [
                        "no genes were significant",
                        "no significant",
                        "zero significant",
                        "0 significant",
                        "none significant",
                        "not significant",
                        "无显著",
                        "未发现显著",
                        "未检测到显著",
                        "fdr后无显著",
                        "fdr 后无显著",
                        "校正后无显著",
                        "全表无显著",
                    ]
                    if any(cue in txt for cue in null_cues):
                        is_honest_null = True

                if not is_honest_null:
                    findings.append(
                        DEFinding(
                            rule_id="BFA-003b",
                            severity=FindingSeverity.HIGH_IMPACT,
                            category=FindingCategory.FDR_AND_TESTING,
                            title="FDR 校正后无显著基因 (Zero DEGs Surviving Multiple Testing Correction)",
                            impact_on_conclusion=f"原始 p < 0.05 有 {sig_raw} 个基因，但 FDR < {fdr_threshold} 存活基因数为 0。若在文稿中仅依据原始 p 值报告差异基因，属于学术不端隐患（Selective Reporting / P-hacking）。",
                            step_or_location="Significance Filtering",
                            minimal_fix=(
                                "# 严禁仅汇报 raw p < 0.05 的基因！最小修复：\n"
                                "# 1. 诚实报告在当前样本量下未检测到达到全转录组 FDR < 0.05 的显著基因；\n"
                                "# 2. 或适当放宽至 FDR < 0.10 并结合 |log2FC| > 1.0 作为「待验证候选」明确声明。"
                            ),
                        )
                    )
                else:
                    checks.append(
                        CheckRecord(
                            check_id="fdr_multiple_testing",
                            title="FDR 多重假设检验校正",
                            status=CheckStatus.ASSESSED,
                            summary=f"全表无 FDR < {fdr_threshold} 显著基因；文稿诚实声明阴性结果 (Honest Negative Result)。",
                            required_for_pass=True,
                        )
                    )
        except Exception:
            pass

    # 2. Check Pseudoreplication Signature in P-values
    if p_col:
        try:
            min_p = de_df[p_col].min()
            zero_or_tiny_p = (de_df[p_col] < 1e-100).sum()
            if zero_or_tiny_p > 10:
                findings.append(
                    DEFinding(
                        rule_id="BFA-001c",
                        severity=FindingSeverity.HIGH_IMPACT,
                        category=FindingCategory.PSEUDOREPLICATION,
                        title="极小 P 值诊断信号：提示需核验统计单位，非方法学无效充分条件 (Extreme P-value Diagnostic Signal)",
                        impact_on_conclusion=(
                            f"检测到 {zero_or_tiny_p} 个基因的 p 值低于 1e-100（最小 p={min_p}）。"
                            "极小 P 值为诊断信号（diagnostic signal），提示需核验分析是否在单细胞级别直接检验（存在伪重复方差膨胀），"
                            "而非方法学无效（methodological invalidity）的充分条件。"
                            "在缺乏供体级执行凭证时提示核验；若供体级聚合已验证且无 p=0 极端截断，反映强生物学效应，降为 ADVISORY 审阅提示。"
                        ),
                        step_or_location="DE table p-value column",
                        minimal_fix=(
                            "# extreme P 是诊断信号，不是方法学无效的充分条件：\n"
                            "# 1. 若实际已按供体级 Pseudobulk 分析，提供执行记录（execution_record）进行供体级凭证绑定，规则将降为 ADVISORY 审阅提示；\n"
                            "# 2. 若实际检验直接在细胞级别（如 cell-level Wilcoxon/t-test）进行，则存在伪重复膨胀，应改用供体级 Pseudobulk + PyDESeq2。"
                        ),
                        evidence_data={"tiny_p_count": int(zero_or_tiny_p), "min_p": float(min_p)},
                    )
                )
        except Exception as exc:
            logger.info("P-value heuristic could not be evaluated: %s", exc)
            checks.append(
                CheckRecord(
                    check_id="pvalue_heuristic",
                    title="极小 P 值诊断信号",
                    status=CheckStatus.PARSE_FAILED,
                    summary=f"p 值列无法计算：{exc}",
                    required_for_pass=False,
                )
            )

    padj_finding = any(f.rule_id in {"BFA-003", "BFA-003b", "BFA-003c"} for f in findings)
    if padj_finding:
        checks.append(
            CheckRecord(
                check_id="fdr_and_testing",
                title="FDR / 多重检验",
                status=CheckStatus.ISSUE_FOUND,
                summary="已检查 DE 表：缺失、非法或未使用 FDR 校正。",
                required_for_pass=True,
            )
        )
    elif padj_col:
        checks.append(
            CheckRecord(
                check_id="fdr_and_testing",
                title="FDR / 多重检验",
                status=CheckStatus.ASSESSED,
                summary=f"已检查 DE 表：调整 p 值列 `{padj_col}` 含可估计值。" + "; ".join(probability_details),
                required_for_pass=True,
            )
        )
    elif p_col:
        checks.append(
            CheckRecord(
                check_id="fdr_and_testing",
                title="FDR / 多重检验",
                status=CheckStatus.ISSUE_FOUND,
                summary="已检查 DE 表：仅有原始 p 值。",
                required_for_pass=True,
            )
        )
    else:
        checks.append(
            CheckRecord(
                check_id="fdr_and_testing",
                title="FDR / 多重检验",
                status=CheckStatus.MISSING_EVIDENCE,
                summary="DE 表无可识别的 p 值或 padj 列。",
                required_for_pass=True,
            )
        )
