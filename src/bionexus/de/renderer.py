"""
BioNexus DE Audit Report Renderers.

Renders terminal summary text with ANSI coloring and publication-ready Markdown reports.
"""

from __future__ import annotations

from typing import Any


def render_summary_text(result: Any, use_color: bool = True) -> str:
    """Render a clean, human-readable terminal output."""
    from bionexus.de.models import CHECK_STATUS_ZH, CheckStatus, FindingSeverity

    red = "\033[91m" if use_color else ""
    yellow = "\033[93m" if use_color else ""
    green = "\033[92m" if use_color else ""
    cyan = "\033[96m" if use_color else ""
    bold = "\033[1m" if use_color else ""
    reset = "\033[0m" if use_color else ""

    lines = []
    from bionexus.evidence_contract import contract_text
    lines.append(contract_text(result.evidence_contract))
    lines.append(f"{bold}================================================================================{reset}")
    lines.append(f"{bold} BioNexus 证据审计：多供体单细胞差异表达（组会/投稿/共享前审阅）{reset}")
    lines.append(f"{bold}================================================================================{reset}")

    # Status badge — never treat missing evidence as a pass
    if result.overall_status == "BLOCKER_DETECTED" or result.blocker_count > 0:
        status_badge = f"{red}[🔴 存在阻断性问题 - 结论暂不能成立]{reset}"
    elif result.overall_status == "NEEDS_REVISION" or result.high_impact_count > 0:
        status_badge = f"{yellow}[🟡 存在高影响风险 - 需修正后投稿]{reset}"
    elif result.overall_status in ("NEEDS_DATA", "NOT_ASSESSED"):
        status_badge = f"{yellow}[⚪ 缺少证据 - 未评估 / 不能通过]{reset}"
    elif result.overall_status == "ROBUST_PASS":
        status_badge = f"{green}[🟢 所列产物检查通过 - 科学前提仍需复核]{reset}"
    else:
        status_badge = f"{yellow}[⚪ 未评估]{reset}"

    lines.append(f"\n【审计结论】 {status_badge}  `{result.overall_status}`")
    lines.append(
        f"  阻断性问题 (Blocker): {result.blocker_count} | 高风险问题 (High Impact): {result.high_impact_count} | 方法学建议 (Advisory): {result.advisory_count}"
    )

    if result.cohort_summary:
        donors = result.cohort_summary.get("n_donors", "未知")
        conds = result.cohort_summary.get("conditions", {})
        cells = result.cohort_summary.get("n_cells", "未知")
        lines.append(f"  队列概况: 供体总数 N={donors} | 细胞总数: {cells} | 条件分布: {conds}")

    # 1. 哪个问题会影响当前结论
    lines.append(f"\n{bold}--------------------------------------------------------------------------------{reset}")
    lines.append(f"{bold} 1. 哪个问题会影响当前结论 (Issues Affecting Conclusions){reset}")
    lines.append(f"{bold}--------------------------------------------------------------------------------{reset}")
    if result.checks:
        lines.append("\n  检查覆盖：")
        for chk in result.checks:
            lines.append(f"    • {chk.title}: {CHECK_STATUS_ZH[chk.status]} — {chk.summary}")

    if not result.findings:
        if any(c.status in (CheckStatus.MISSING_EVIDENCE, CheckStatus.PARSE_FAILED) for c in result.checks):
            lines.append(f"  {yellow}○ 未完成评估：必要证据缺失或解析失败，不能视为通过。{reset}")
        else:
            lines.append(f"  {green}✔ 已检查项未发现影响结论的方法学或统计学缺陷。{reset}")
    else:
        for idx, f in enumerate(result.findings, 1):
            icon = (
                "🔴"
                if f.severity == FindingSeverity.BLOCKER
                else ("🟡" if f.severity == FindingSeverity.HIGH_IMPACT else "🔵")
            )
            lines.append(f"\n  {bold}{idx}. {icon} [{f.severity.value}] {f.title}{reset} ({f.rule_id})")
            lines.append(f"     {bold}为什么影响结论：{reset}{f.impact_on_conclusion}")

    # 2. 问题对应哪个样本、步骤或声明
    lines.append(f"\n{bold}--------------------------------------------------------------------------------{reset}")
    lines.append(f"{bold} 2. 问题对应哪个样本、步骤或声明 (Sample, Step & Claim Mapping){reset}")
    lines.append(f"{bold}--------------------------------------------------------------------------------{reset}")
    for idx, f in enumerate(result.findings, 1):
        lines.append(f"  [{idx}] {f.title}:")
        if f.sample_or_donor:
            lines.append(f"      • 涉及样本/供体：{cyan}{f.sample_or_donor}{reset}")
        if f.step_or_location:
            lines.append(f"      • 涉及分析步骤/代码：{cyan}{f.step_or_location}{reset}")
        if f.claim_affected:
            lines.append(f"      • 涉及结论声明：{cyan}{f.claim_affected}{reset}")

    # 3. 最小修复是什么
    lines.append(f"\n{bold}--------------------------------------------------------------------------------{reset}")
    lines.append(f"{bold} 3. 最小修复是什么 (Minimal Actionable Fixes){reset}")
    lines.append(f"{bold}--------------------------------------------------------------------------------{reset}")
    for idx, f in enumerate(result.findings, 1):
        if f.minimal_fix:
            lines.append(f"\n  [{idx}] 针对「{f.title}」的最小修复建议：")
            for fix_line in f.minimal_fix.strip().splitlines():
                lines.append(f"      {fix_line}")

    # 4. 当前可以陈述到什么范围
    if result.claim_boundary:
        lines.append(f"\n{bold}--------------------------------------------------------------------------------{reset}")
        lines.append(f"{bold} 4. 当前可以陈述到什么范围 (Permissible Scientific Claim Scope){reset}")
        lines.append(f"{bold}--------------------------------------------------------------------------------{reset}")
        lines.append(f"  {green}✅ 当前证据【可以陈述】的范围：{reset}")
        lines.append(f"     {result.claim_boundary.allowed_scope}")
        lines.append(f"\n  {red}❌ 当前证据【严禁越界陈述】的范围：{reset}")
        lines.append(f"     {result.claim_boundary.prohibited_scope}")
        lines.append(f"\n  📝 {bold}已执行方法（仅来自执行记录）：{reset}")
        lines.append(f"     \"{result.claim_boundary.executed_methods_text}\"")
        lines.append(f"\n  📝 {bold}建议分析（不作为已完成事实）：{reset}")
        lines.append(f"     \"{result.claim_boundary.recommended_methods_text}\"")
        lines.append(f"\n  📝 {bold}推荐结果表述：{reset}")
        lines.append(f"     \"{result.claim_boundary.recommended_results_text}\"")

    # 5. 哪些分歧需要负责人一次性裁决
    if result.pi_decisions:
        lines.append(f"\n{bold}--------------------------------------------------------------------------------{reset}")
        lines.append(f"{bold} 5. 哪些分歧需要负责人一次性裁决 (PI One-Time Decisions){reset}")
        lines.append(f"{bold}--------------------------------------------------------------------------------{reset}")
        for d in result.pi_decisions:
            lines.append(f"\n  ⚖️ {bold}{d.decision_id}：{d.title}{reset}")
            lines.append(f"     背景事实：{d.context}")
            lines.append(f"     • 选项 A {'[推荐]' if d.recommended_option == 'A' else ''}：{d.option_a}")
            lines.append(f"     • 选项 B {'[推荐]' if d.recommended_option == 'B' else ''}：{d.option_b}")
            lines.append(f"     权衡考量：{d.tradeoff_explanation}")

    if result.claim_conditions:
        from bionexus.de.conditions import render_conditions
        lines.append(render_conditions(result.claim_conditions))
    if result.alternative_analysis:
        from bionexus.de.alternatives import render_alternatives
        lines.append(render_alternatives(result.alternative_analysis))
    if result.selection_history:
        from bionexus.de.selection import render_selection_history
        lines.append(render_selection_history(result.selection_history))
    lines.append(f"\n{bold}================================================================================{reset}\n")
    return "\n".join(lines)


def render_markdown(result: Any) -> str:
    """Render a publication-ready Markdown report."""
    from bionexus.de.models import CHECK_STATUS_ZH, CheckStatus, FindingSeverity

    md = []
    from bionexus.evidence_contract import contract_text
    md.append(contract_text(result.evidence_contract))
    md.append("# BioNexus 证据审计报告：多供体单细胞差异表达")
    md.append(
        f"\n> **审计状态**：`{result.overall_status}` | **通过**：`{result.passed}` | "
        f"**阻断性问题**：{result.blocker_count} | **高风险问题**：{result.high_impact_count} | **方法学建议**：{result.advisory_count}\n"
    )

    if result.cohort_summary:
        md.append("## 实验设计与队列概况")
        md.append(f"- **供体总数 (Donors)**: {result.cohort_summary.get('n_donors', 'N/A')}")
        md.append(f"- **细胞总数 (Cells)**: {result.cohort_summary.get('n_cells', 'N/A')}")
        conds = result.cohort_summary.get("conditions", {})
        if conds:
            cond_str = ", ".join([f"{k}: {v} 供体" for k, v in conds.items()])
            md.append(f"- **组别分布 (Conditions)**: {cond_str}")
        if "batches" in result.cohort_summary:
            md.append(f"- **批次数量 (Batches)**: {result.cohort_summary['batches']}")
        md.append("")

    if result.checks:
        md.append("## 检查覆盖 (Assessed / Issue Found / Missing Evidence)")
        md.append("| 检查项 | 状态 | 说明 | 通过所必需 |")
        md.append("| :--- | :--- | :--- | :--- |")
        for chk in result.checks:
            md.append(
                f"| {chk.title} | {CHECK_STATUS_ZH[chk.status]} (`{chk.status.value}`) | {chk.summary} | "
                f"{'yes' if chk.required_for_pass else 'no'} |"
            )
        md.append("")

    # 1. 哪个问题会影响当前结论
    md.append("## 1. 哪个问题会影响当前结论 (Issues Affecting Conclusions)")
    if not result.findings:
        if any(c.status in (CheckStatus.MISSING_EVIDENCE, CheckStatus.PARSE_FAILED) for c in result.checks):
            md.append("> [!WARNING]\n> 未完成评估：必要证据缺失或解析失败，不能视为通过。\n")
        else:
            md.append("> [!NOTE]\n> 已检查项未发现影响差异表达结论的致命伤或严重偏差。\n")
    else:
        for f in result.findings:
            alert_type = (
                "CAUTION"
                if f.severity == FindingSeverity.BLOCKER
                else ("WARNING" if f.severity == FindingSeverity.HIGH_IMPACT else "NOTE")
            )
            md.append(f"### [{f.severity.value}] {f.title} (`{f.rule_id}`)")
            md.append(f"> [!{alert_type}]\n> **对结论的影响**：{f.impact_on_conclusion}\n")

    # 2. 定位映射
    md.append("## 2. 问题对应哪个样本、步骤或声明 (Sample, Step & Claim Mapping)")
    md.append("| 编号 | 审计问题 | 对应样本/供体 | 对应分析步骤/代码 | 对应声明受损 |")
    md.append("| :--- | :--- | :--- | :--- | :--- |")
    for idx, f in enumerate(result.findings, 1):
        s = f.sample_or_donor or "-"
        st = f"`{f.step_or_location}`" if f.step_or_location else "-"
        c = f.claim_affected or "-"
        md.append(f"| {idx} | {f.title} | {s} | {st} | {c} |")
    md.append("")

    # 3. 最小修复
    md.append("## 3. 最小修复是什么 (Minimal Actionable Fixes)")
    for idx, f in enumerate(result.findings, 1):
        if f.minimal_fix:
            md.append(f"#### 针对问题 {idx}（{f.title}）：")
            md.append("```python")
            md.append(f.minimal_fix.strip())
            md.append("```\n")

    # 4. 当前可以陈述到什么范围
    if result.claim_boundary:
        md.append("## 4. 当前可以陈述到什么范围 (Permissible Scientific Claim Scope)")
        md.append(f"> [!TIP]\n> **允许陈述的科学范围**：\n> {result.claim_boundary.allowed_scope}\n")
        md.append(f"> [!WARNING]\n> **严禁越界声称的范围**：\n> {result.claim_boundary.prohibited_scope}\n")
        md.append("### 已执行方法 vs 建议分析")
        md.append("**Executed methods (past tense only from execution records)**:")
        md.append(f"> \"{result.claim_boundary.executed_methods_text}\"\n")
        md.append("**Recommended analysis (not claimed as completed)**:")
        md.append(f"> \"{result.claim_boundary.recommended_methods_text}\"\n")
        md.append("**Results phrasing**:")
        md.append(f"> \"{result.claim_boundary.recommended_results_text}\"\n")

    # 5. 负责人一次性裁决
    if result.pi_decisions:
        md.append("## 5. 哪些分歧需要负责人一次性裁决 (PI One-Time Decision Deck)")
        for d in result.pi_decisions:
            rec_badge = " [推荐]" if d.recommended_option == "A" else ""
            rec_badge_b = " [推荐]" if d.recommended_option == "B" else ""
            md.append(f"### ⚖️ {d.decision_id}：{d.title}")
            md.append(f"- **背景事实**：{d.context}")
            md.append(f"- **选项 A{rec_badge}**：{d.option_a}")
            md.append(f"- **选项 B{rec_badge_b}**：{d.option_b}")
            md.append(f"- **权衡考量**：{d.tradeoff_explanation}\n")

    if result.claim_conditions:
        from bionexus.de.conditions import render_conditions
        md.append(render_conditions(result.claim_conditions))
    if result.alternative_analysis:
        from bionexus.de.alternatives import render_alternatives
        md.append(render_alternatives(result.alternative_analysis))
    if result.selection_history:
        from bionexus.de.selection import render_selection_history
        md.append(render_selection_history(result.selection_history))
    md.append("---\n*BioNexus Scientific Assertion Firewall (BNS-013 / BNS-015)*\n")
    return "\n".join(md)
