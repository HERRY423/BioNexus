"""
Analysis code and notebook static audit rules for differential expression.

Audits scripts/notebooks for cell-level DE calls, count layer misuse, and causality overclaims.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Union

from bionexus.de.models import (
    CheckRecord,
    CheckStatus,
    DEFinding,
    FindingCategory,
    FindingSeverity,
)

logger = logging.getLogger(__name__)


def _audit_code(
    code_path: Union[str, Path],
    findings: List[DEFinding],
    checks: List[CheckRecord],
) -> None:
    """Audit analysis scripts/notebooks for static scientific bugs using analysis_audit."""
    try:
        from bionexus.analysis_audit import audit_analysis

        res = audit_analysis(code_path)
    except Exception as exc:
        logger.info("Analysis code audit failed: %s", exc)
        checks.append(
            CheckRecord(
                check_id="analysis_code",
                title="分析脚本/笔记本",
                status=CheckStatus.PARSE_FAILED,
                summary=f"分析脚本无法审计：{exc}",
                required_for_pass=False,
            )
        )
        findings.append(
            DEFinding(
                rule_id="BFA-PARSE",
                severity=FindingSeverity.HIGH_IMPACT,
                category=FindingCategory.CLAIM_BOUNDARY,
                title="分析脚本解析失败",
                impact_on_conclusion="无法读取脚本/笔记本，不能把未检查的代码当作已通过。",
                step_or_location=str(code_path),
                minimal_fix="提供可解析的 .py / .ipynb / .R 源码后再审计。",
                evidence_data={"error": str(exc)},
            )
        )
        return

    code_issue = False
    for f in res.findings:
        if f.rule_id == "BFA-001" and not any(ef.rule_id == "BFA-001" for ef in findings):
            code_issue = True
            findings.append(
                DEFinding(
                    rule_id=f.rule_id,
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.PSEUDOREPLICATION,
                    title="代码中存在细胞级伪重复调用 (Cell-level DE Call in Code)",
                    impact_on_conclusion=f.message,
                    step_or_location=f.location,
                    minimal_fix=f.remedy,
                )
            )
        elif f.rule_id == "BFA-002" and not any(ef.rule_id == "BFA-002" for ef in findings):
            code_issue = True
            findings.append(
                DEFinding(
                    rule_id=f.rule_id,
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.INPUT_COUNT_TYPE,
                    title=f.rule_name,
                    impact_on_conclusion=f.message,
                    step_or_location=f.location,
                    minimal_fix=f.remedy,
                )
            )
        elif f.rule_id == "BFA-011":
            code_issue = True
            findings.append(
                DEFinding(
                    rule_id=f.rule_id,
                    severity=FindingSeverity.HIGH_IMPACT,
                    category=FindingCategory.CLAIM_BOUNDARY,
                    title="文稿或代码注释过度声称因果机制 (Overclaimed Causality)",
                    impact_on_conclusion=f.message,
                    step_or_location=f.location,
                    minimal_fix=f.remedy,
                )
            )
    checks.append(
        CheckRecord(
            check_id="analysis_code",
            title="分析脚本/笔记本",
            status=CheckStatus.ISSUE_FOUND if code_issue else CheckStatus.ASSESSED,
            summary=(
                "静态审计发现问题。" if code_issue else "已检查分析脚本；静态规则未发现阻断性调用。"
            ),
            required_for_pass=False,
        )
    )
