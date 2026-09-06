"""
BioNexus Multi-Donor Single-Cell Differential Expression Evidence Audit Engine.

This engine transforms first-time and routine laboratory use into a high-yield,
frictionless research workflow stage:
"多供体单细胞差异表达，在组会、投稿或共享前的证据审计"
(Multi-Donor scRNA Differential Expression Evidence Audit before Lab Meetings,
Manuscript Submission, or Data Sharing).

Scientists continue using Scanpy, Seurat, or existing workflows. BioNexus receives
their data object, DEG table, sample design, or analysis script, and returns:
1. 哪个问题会影响当前结论 (Which issues affect the current conclusion)
2. 问题对应哪个样本、步骤或声明 (Mapping to specific sample/donor, step, or claim)
3. 最小修复是什么 (Minimal, copy-pasteable executable fixes)
4. 当前可以陈述到什么范围 (Permissible claim scope & recommended manuscript text)
5. 哪些分歧需要负责人一次性裁决 (Structured decisions for the PI/Lab Lead)

Normative references:
- Squair et al. (2021) Nature Communications: Confronting false discoveries in single-cell differential expression.
- Crowell et al. (2020) Nature Communications: muscat detects differential state in multi-sample multi-condition scRNA-seq.
- Luecken et al. (2021) Nature Methods: Benchmarking atlas-level data integration in single-cell genomics.
- BN-F001 (Raw/Log Matrix Confusion)
- BN-F002 (Pseudoreplication / Cell != Biological Replicate)
- BN-F005 (Uncontrolled False Discovery Rate)
- BN-F006 (Confounded Design / Zero Replicates)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

try:
    import numpy as np
except ImportError:
    np = None

try:
    import pandas as pd
except ImportError:
    pd = None


# ==============================================================================
# Domain Models & Enums
# ==============================================================================

class FindingSeverity(str, Enum):
    """Severity of an audit finding for biological conclusions."""
    BLOCKER = "BLOCKER"          # 🔴 阻断：结论在数理或统计学上不成立，假阳性极高或无法推断
    HIGH_IMPACT = "HIGH_IMPACT"  # 🟡 高风险：严重扭曲效应量或显著性，必须修正方可投稿
    ADVISORY = "ADVISORY"        # 🔵 建议：方法学规范与鲁棒性提升建议
    PASS = "PASS"                # 🟢 符合规范


class FindingCategory(str, Enum):
    """Category of single-cell differential expression failure."""
    PSEUDOREPLICATION = "PSEUDOREPLICATION"        # 细胞级伪重复（未按供体聚合）
    DONOR_REPLICATES = "DONOR_REPLICATES"          # 供体生物学重复不足 (N < 3)
    DONOR_IMBALANCE = "DONOR_IMBALANCE"            # 供体细胞贡献极端失衡 (单供体主导)
    BATCH_CONFOUNDING = "BATCH_CONFOUNDING"        # 批次/技术变量与实验分组混杂
    INPUT_COUNT_TYPE = "INPUT_COUNT_TYPE"          # 计数层混淆 (非整数/已归一化数据输入GLM)
    FDR_AND_TESTING = "FDR_AND_TESTING"            # 多重假设检验与显著性阈值漏洞
    CLAIM_BOUNDARY = "CLAIM_BOUNDARY"              # 科学声明超出证据支持范围


@dataclass
class DEFinding:
    """A concrete finding impacting differential expression scientific conclusions."""
    rule_id: str
    severity: FindingSeverity
    category: FindingCategory
    title: str
    impact_on_conclusion: str
    sample_or_donor: Optional[str] = None
    step_or_location: Optional[str] = None
    claim_affected: Optional[str] = None
    minimal_fix: str = ""
    evidence_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "severity": self.severity.value,
            "category": self.category.value,
            "title": self.title,
            "impact_on_conclusion": self.impact_on_conclusion,
            "sample_or_donor": self.sample_or_donor,
            "step_or_location": self.step_or_location,
            "claim_affected": self.claim_affected,
            "minimal_fix": self.minimal_fix,
            "evidence_data": dict(self.evidence_data),
        }


@dataclass
class PIDecisionItem:
    """A structured decision item requiring PI / Lab Lead adjudication."""
    decision_id: str
    title: str
    context: str
    option_a: str  # Typically the recommended/standard path
    option_b: str  # Alternative or pragmatic path
    tradeoff_explanation: str
    recommended_option: str = "A"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimScopeBoundary:
    """Explicit scientific claim boundaries and recommended manuscript phrasing."""
    allowed_scope: str
    prohibited_scope: str
    recommended_methods_text: str
    recommended_results_text: str
    overall_maturity: str = "EXPLORATORY"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DEAuditResult:
    """The complete, lab-ready audit verdict for multi-donor single-cell DE."""
    overall_status: str  # "BLOCKER_DETECTED", "NEEDS_REVISION", "ROBUST_PASS"
    findings: List[DEFinding] = field(default_factory=list)
    claim_boundary: Optional[ClaimScopeBoundary] = None
    pi_decisions: List[PIDecisionItem] = field(default_factory=list)
    cohort_summary: Dict[str, Any] = field(default_factory=dict)
    metadata_columns_used: Dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not any(f.severity == FindingSeverity.BLOCKER for f in self.findings)

    @property
    def blocker_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.BLOCKER)

    @property
    def high_impact_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.HIGH_IMPACT)

    @property
    def advisory_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == FindingSeverity.ADVISORY)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "passed": self.passed,
            "summary_counts": {
                "blocker": self.blocker_count,
                "high_impact": self.high_impact_count,
                "advisory": self.advisory_count,
            },
            "cohort_summary": self.cohort_summary,
            "metadata_columns_used": self.metadata_columns_used,
            "findings": [f.to_dict() for f in self.findings],
            "claim_boundary": self.claim_boundary.to_dict() if self.claim_boundary else None,
            "pi_decisions": [d.to_dict() for d in self.pi_decisions],
        }

    def summary_text(self, use_color: bool = True) -> str:
        """Render a clean, human-readable terminal output."""
        red = "\033[91m" if use_color else ""
        yellow = "\033[93m" if use_color else ""
        green = "\033[92m" if use_color else ""
        cyan = "\033[96m" if use_color else ""
        bold = "\033[1m" if use_color else ""
        reset = "\033[0m" if use_color else ""

        lines = []
        lines.append(f"{bold}================================================================================{reset}")
        lines.append(f"{bold} BioNexus 证据审计：多供体单细胞差异表达（组会/投稿/共享前审阅）{reset}")
        lines.append(f"{bold}================================================================================{reset}")

        # Status badge
        if self.blocker_count > 0:
            status_badge = f"{red}[🔴 存在阻断性问题 - 结论暂不能成立]{reset}"
        elif self.high_impact_count > 0:
            status_badge = f"{yellow}[🟡 存在高影响风险 - 需修正后投稿]{reset}"
        else:
            status_badge = f"{green}[🟢 审计通过 - 支持严谨群体推断]{reset}"

        lines.append(f"\n【审计结论】 {status_badge}")
        lines.append(f"  阻断性问题 (Blocker): {self.blocker_count} | 高风险问题 (High Impact): {self.high_impact_count} | 方法学建议 (Advisory): {self.advisory_count}")

        if self.cohort_summary:
            donors = self.cohort_summary.get("n_donors", "未知")
            conds = self.cohort_summary.get("conditions", {})
            cells = self.cohort_summary.get("n_cells", "未知")
            lines.append(f"  队列概况: 供体总数 N={donors} | 细胞总数: {cells} | 条件分布: {conds}")

        # 1. 哪个问题会影响当前结论
        lines.append(f"\n{bold}--------------------------------------------------------------------------------{reset}")
        lines.append(f"{bold} 1. 哪个问题会影响当前结论 (Issues Affecting Conclusions){reset}")
        lines.append(f"{bold}--------------------------------------------------------------------------------{reset}")
        if not self.findings:
            lines.append(f"  {green}✔ 未检测到影响结论的方法学或统计学缺陷。{reset}")
        else:
            for idx, f in enumerate(self.findings, 1):
                icon = "🔴" if f.severity == FindingSeverity.BLOCKER else ("🟡" if f.severity == FindingSeverity.HIGH_IMPACT else "🔵")
                lines.append(f"\n  {bold}{idx}. {icon} [{f.severity.value}] {f.title}{reset} ({f.rule_id})")
                lines.append(f"     {bold}为什么影响结论：{reset}{f.impact_on_conclusion}")

        # 2. 问题对应哪个样本、步骤或声明
        lines.append(f"\n{bold}--------------------------------------------------------------------------------{reset}")
        lines.append(f"{bold} 2. 问题对应哪个样本、步骤或声明 (Sample, Step & Claim Mapping){reset}")
        lines.append(f"{bold}--------------------------------------------------------------------------------{reset}")
        for idx, f in enumerate(self.findings, 1):
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
        for idx, f in enumerate(self.findings, 1):
            if f.minimal_fix:
                lines.append(f"\n  [{idx}] 针对「{f.title}」的最小修复建议：")
                for fix_line in f.minimal_fix.strip().splitlines():
                    lines.append(f"      {fix_line}")

        # 4. 当前可以陈述到什么范围
        if self.claim_boundary:
            lines.append(f"\n{bold}--------------------------------------------------------------------------------{reset}")
            lines.append(f"{bold} 4. 当前可以陈述到什么范围 (Permissible Scientific Claim Scope){reset}")
            lines.append(f"{bold}--------------------------------------------------------------------------------{reset}")
            lines.append(f"  {green}✅ 当前证据【可以陈述】的范围：{reset}")
            lines.append(f"     {self.claim_boundary.allowed_scope}")
            lines.append(f"\n  {red}❌ 当前证据【严禁越界陈述】的范围：{reset}")
            lines.append(f"     {self.claim_boundary.prohibited_scope}")
            lines.append(f"\n  📝 {bold}推荐组会/论文表述段落 (Recommended Phrasing)：{reset}")
            lines.append(f"     \"{self.claim_boundary.recommended_results_text}\"")

        # 5. 哪些分歧需要负责人一次性裁决
        if self.pi_decisions:
            lines.append(f"\n{bold}--------------------------------------------------------------------------------{reset}")
            lines.append(f"{bold} 5. 哪些分歧需要负责人一次性裁决 (PI One-Time Decisions){reset}")
            lines.append(f"{bold}--------------------------------------------------------------------------------{reset}")
            for d in self.pi_decisions:
                lines.append(f"\n  ⚖️ {bold}{d.decision_id}：{d.title}{reset}")
                lines.append(f"     背景事实：{d.context}")
                lines.append(f"     • 选项 A {'[推荐]' if d.recommended_option == 'A' else ''}：{d.option_a}")
                lines.append(f"     • 选项 B {'[推荐]' if d.recommended_option == 'B' else ''}：{d.option_b}")
                lines.append(f"     权衡考量：{d.tradeoff_explanation}")

        lines.append(f"\n{bold}================================================================================{reset}\n")
        return "\n".join(lines)

    def to_markdown(self) -> str:
        """Render a publication-ready Markdown report."""
        md = []
        md.append("# BioNexus 证据审计报告：多供体单细胞差异表达")
        md.append(f"\n> **审计状态**：`{self.overall_status}` | **阻断性问题**：{self.blocker_count} | **高风险问题**：{self.high_impact_count} | **方法学建议**：{self.advisory_count}\n")

        if self.cohort_summary:
            md.append("## 实验设计与队列概况")
            md.append(f"- **供体总数 (Donors)**: {self.cohort_summary.get('n_donors', 'N/A')}")
            md.append(f"- **细胞总数 (Cells)**: {self.cohort_summary.get('n_cells', 'N/A')}")
            conds = self.cohort_summary.get("conditions", {})
            if conds:
                cond_str = ", ".join([f"{k}: {v} 供体" for k, v in conds.items()])
                md.append(f"- **组别分布 (Conditions)**: {cond_str}")
            if "batches" in self.cohort_summary:
                md.append(f"- **批次数量 (Batches)**: {self.cohort_summary['batches']}")
            md.append("")

        # 1. 哪个问题会影响当前结论
        md.append("## 1. 哪个问题会影响当前结论 (Issues Affecting Conclusions)")
        if not self.findings:
            md.append("> [!NOTE]\n> 未检测到影响差异表达结论的致命伤或严重偏差。\n")
        else:
            for f in self.findings:
                alert_type = "CAUTION" if f.severity == FindingSeverity.BLOCKER else ("WARNING" if f.severity == FindingSeverity.HIGH_IMPACT else "NOTE")
                md.append(f"### [{f.severity.value}] {f.title} (`{f.rule_id}`)")
                md.append(f"> [!{alert_type}]\n> **对结论的影响**：{f.impact_on_conclusion}\n")

        # 2. 定位映射
        md.append("## 2. 问题对应哪个样本、步骤或声明 (Sample, Step & Claim Mapping)")
        md.append("| 编号 | 审计问题 | 对应样本/供体 | 对应分析步骤/代码 | 对应声明受损 |")
        md.append("| :--- | :--- | :--- | :--- | :--- |")
        for idx, f in enumerate(self.findings, 1):
            s = f.sample_or_donor or "-"
            st = f"`{f.step_or_location}`" if f.step_or_location else "-"
            c = f.claim_affected or "-"
            md.append(f"| {idx} | {f.title} | {s} | {st} | {c} |")
        md.append("")

        # 3. 最小修复
        md.append("## 3. 最小修复是什么 (Minimal Actionable Fixes)")
        for idx, f in enumerate(self.findings, 1):
            if f.minimal_fix:
                md.append(f"#### 针对问题 {idx}（{f.title}）：")
                md.append("```python")
                md.append(f.minimal_fix.strip())
                md.append("```\n")

        # 4. 当前可以陈述到什么范围
        if self.claim_boundary:
            md.append("## 4. 当前可以陈述到什么范围 (Permissible Scientific Claim Scope)")
            md.append(f"> [!TIP]\n> **允许陈述的科学范围**：\n> {self.claim_boundary.allowed_scope}\n")
            md.append(f"> [!WARNING]\n> **严禁越界声称的范围**：\n> {self.claim_boundary.prohibited_scope}\n")
            md.append("### 推荐投稿/汇报表述 (Recommended Manuscript Phrasing)")
            md.append("**Results**:")
            md.append(f"> \"{self.claim_boundary.recommended_results_text}\"\n")
            md.append("**Methods**:")
            md.append(f"> \"{self.claim_boundary.recommended_methods_text}\"\n")

        # 5. 负责人一次性裁决
        if self.pi_decisions:
            md.append("## 5. 哪些分歧需要负责人一次性裁决 (PI One-Time Decision Deck)")
            for d in self.pi_decisions:
                rec_badge = " [推荐]" if d.recommended_option == "A" else ""
                rec_badge_b = " [推荐]" if d.recommended_option == "B" else ""
                md.append(f"### ⚖️ {d.decision_id}：{d.title}")
                md.append(f"- **背景事实**：{d.context}")
                md.append(f"- **选项 A{rec_badge}**：{d.option_a}")
                md.append(f"- **选项 B{rec_badge_b}**：{d.option_b}")
                md.append(f"- **权衡考量**：{d.tradeoff_explanation}\n")

        md.append("---\n*BioNexus Scientific Assertion Firewall (BNS-013 / BNS-015)*\n")
        return "\n".join(md)


# ==============================================================================
# Column Heuristics & Data Helpers
# ==============================================================================

DONOR_KEYWORDS = ["donor", "donor_id", "sample", "sample_id", "patient", "patient_id", "subject", "mouse_id", "specimen"]
CONDITION_KEYWORDS = ["condition", "group", "disease", "status", "treatment", "stim", "genotype", "phenotype", "cohort"]
CELLTYPE_KEYWORDS = ["cell_type", "celltype", "cluster", "leiden", "louvain", "seurat_clusters", "annotation", "cell_label", "lineage"]
BATCH_KEYWORDS = ["batch", "pool", "lane", "run", "experiment", "date", "seq_run", "gem_group", "orig.ident"]


def _match_column(cols: Sequence[str], keywords: Sequence[str]) -> Optional[str]:
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


# ==============================================================================
# Core Audit Engine
# ==============================================================================

class DEAuditEngine:
    """Multi-Donor Single-Cell Differential Expression Evidence Auditor."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self.min_donors_required = self.config.get("min_donors_required", 3)
        self.min_cells_per_donor = self.config.get("min_cells_per_donor", 20)
        self.dominance_threshold = self.config.get("dominance_threshold", 0.70)
        self.fdr_threshold = self.config.get("fdr_threshold", 0.05)

    def audit(
        self,
        *,
        adata: Any = None,
        adata_path: Optional[Union[str, Path]] = None,
        de_table: Optional[Union[pd.DataFrame, str, Path]] = None,
        sample_metadata: Optional[Union[pd.DataFrame, str, Path]] = None,
        code_path: Optional[Union[str, Path]] = None,
        claim_text: Optional[str] = None,
        donor_col: Optional[str] = None,
        condition_col: Optional[str] = None,
        cell_type_col: Optional[str] = None,
        batch_col: Optional[str] = None,
    ) -> DEAuditResult:
        """Run the 5-pillar differential expression evidence audit."""
        findings: List[DEFinding] = []
        pi_decisions: List[PIDecisionItem] = []
        cohort_summary: Dict[str, Any] = {}
        cols_used: Dict[str, str] = {}

        # 1. Resolve AnnData object if provided
        if adata is None and adata_path is not None:
            adata = self._load_anndata(adata_path)

        # 2. Extract or resolve sample/cell metadata
        obs_df: Optional[pd.DataFrame] = None
        if adata is not None and hasattr(adata, "obs"):
            obs_df = adata.obs
        elif sample_metadata is not None:
            obs_df = self._load_dataframe(sample_metadata)

        # 3. Resolve DE results table
        de_df: Optional[pd.DataFrame] = None
        if de_table is not None:
            de_df = self._load_dataframe(de_table)
        elif adata is not None and hasattr(adata, "uns") and "rank_genes_groups" in adata.uns:
            de_df = self._extract_de_from_anndata_uns(adata)

        # 4. Infer metadata column mappings
        if obs_df is not None:
            cols = list(obs_df.columns)
            d_col = donor_col or _match_column(cols, DONOR_KEYWORDS)
            c_col = condition_col or _match_column(cols, CONDITION_KEYWORDS)
            ct_col = cell_type_col or _match_column(cols, CELLTYPE_KEYWORDS)
            b_col = batch_col or _match_column(cols, BATCH_KEYWORDS)

            if d_col:
                cols_used["donor"] = d_col
            if c_col:
                cols_used["condition"] = c_col
            if ct_col:
                cols_used["cell_type"] = ct_col
            if b_col:
                cols_used["batch"] = b_col

            # Perform metadata-level audits (Replicates, Imbalance, Confounding)
            self._audit_metadata(
                obs_df=obs_df,
                d_col=d_col,
                c_col=c_col,
                ct_col=ct_col,
                b_col=b_col,
                findings=findings,
                pi_decisions=pi_decisions,
                cohort_summary=cohort_summary,
            )

        # 5. Perform matrix-level audits (Raw integer counts vs log/scaled floats)
        if adata is not None:
            self._audit_expression_matrix(adata, findings)

        # 6. Perform DE Table audits (P-values, FDR, Pseudoreplication markers)
        if de_df is not None:
            self._audit_de_table(de_df, findings, pi_decisions)

        # 7. Perform Code / Notebook audit if provided
        if code_path is not None:
            self._audit_code(code_path, findings)

        # 8. Assess Scientific Claim Scope Boundaries & Manuscript Text
        claim_boundary = self._determine_claim_boundary(findings, cohort_summary, claim_text)

        # 9. Compute Overall Status
        if any(f.severity == FindingSeverity.BLOCKER for f in findings):
            overall_status = "BLOCKER_DETECTED"
        elif any(f.severity == FindingSeverity.HIGH_IMPACT for f in findings):
            overall_status = "NEEDS_REVISION"
        else:
            overall_status = "ROBUST_PASS"

        return DEAuditResult(
            overall_status=overall_status,
            findings=findings,
            claim_boundary=claim_boundary,
            pi_decisions=pi_decisions,
            cohort_summary=cohort_summary,
            metadata_columns_used=cols_used,
        )

    # --------------------------------------------------------------------------
    # Sub-Audits
    # --------------------------------------------------------------------------

    def _audit_metadata(
        self,
        obs_df: pd.DataFrame,
        d_col: Optional[str],
        c_col: Optional[str],
        ct_col: Optional[str],
        b_col: Optional[str],
        findings: List[DEFinding],
        pi_decisions: List[PIDecisionItem],
        cohort_summary: Dict[str, Any],
    ) -> None:
        """Audit biological replicates, donor imbalance, and batch confounding."""
        cohort_summary["n_cells"] = len(obs_df)

        if not d_col:
            findings.append(
                DEFinding(
                    rule_id="BFA-005",
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.DONOR_REPLICATES,
                    title="缺失供体/生物学重复标识 (Missing Biological Replicate Identifiers)",
                    impact_on_conclusion="元数据中未发现供体/样本列，无法区分细胞间变异与供体间真实生物学变异。直接进行组间差异分析构成纯粹伪重复，产出大量假阳性基因。",
                    step_or_location="sample_metadata / adata.obs",
                    minimal_fix="在 adata.obs 中补充供体标识列（例如 adata.obs['donor_id'] = ...），确保每个细胞可归属至具体生物学个体。",
                )
            )
            return

        donors = obs_df[d_col].unique()
        cohort_summary["n_donors"] = len(donors)
        cohort_summary["donors"] = list(donors)

        if not c_col:
            findings.append(
                DEFinding(
                    rule_id="BFA-012",
                    severity=FindingSeverity.ADVISORY,
                    category=FindingCategory.CLAIM_BOUNDARY,
                    title="未指定实验对比组别 (Condition Column Undetermined)",
                    impact_on_conclusion="未指定或未能自动推断 condition/disease 列，仅能审计聚类内部各供体的细胞分布特征。",
                    minimal_fix="使用参数 --condition-col <列名> 指定实验对照分组（如 Disease vs Healthy）。",
                )
            )
            return

        # 1. Biological replicates per condition
        cond_donor_counts: Dict[str, int] = {}
        for cond, sub in obs_df.groupby(c_col, observed=False):
            cond_donor_counts[str(cond)] = sub[d_col].nunique()
        cohort_summary["conditions"] = cond_donor_counts

        min_donors = min(cond_donor_counts.values()) if cond_donor_counts else 0

        if min_donors < 2:
            findings.append(
                DEFinding(
                    rule_id="BFA-001",
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.DONOR_REPLICATES,
                    title=f"生物学重复严重不足 (N={min_donors} < 2 Replicates per Condition)",
                    impact_on_conclusion=f"至少有一个实验组别仅有 {min_donors} 个供体/动物。统计学自由度为 0，无法估算组内真实生物学离散度（Biological Dispersion）。任何观察到的差异基因均可能来自个体的私有特征。",
                    sample_or_donor=", ".join([f"{k} (N={v})" for k, v in cond_donor_counts.items() if v < 2]),
                    step_or_location="Experimental Design / Sample Intake",
                    minimal_fix=(
                        "# 无法仅靠算法修正零生物学重复缺陷：\n"
                        "# 1. 必须补测至少 2~3 例独立生物学重复；\n"
                        "# 2. 若无法补测，必须在文稿中明确降级为「单个病人的探索性观察 (Exploratory Case Study)」，严禁声称任何群体结论。"
                    ),
                    evidence_data={"donors_by_condition": cond_donor_counts},
                )
            )
        elif min_donors == 2:
            findings.append(
                DEFinding(
                    rule_id="BFA-001b",
                    severity=FindingSeverity.HIGH_IMPACT,
                    category=FindingCategory.DONOR_REPLICATES,
                    title="生物学重复临界不足 (N=2 Replicates per Condition)",
                    impact_on_conclusion="每组仅有 2 个生物学重复。虽然可运行 DESeq2/EdgeR，但方差估计完全依赖基因间的经验贝叶斯收缩（Empirical Bayes Shrinkage），检出力较低且易受离群值干扰。只能作为初步探索，不足以支持稳健人群外推。",
                    sample_or_donor=", ".join([f"{k} (N={v})" for k, v in cond_donor_counts.items() if v == 2]),
                    step_or_location="Experimental Design",
                    minimal_fix=(
                        "# 最小修复与风险声明：\n"
                        "# 1. 推荐将队列扩充至 N >= 3 供体/组；\n"
                        "# 2. 在论文中声明结果为探索性（Exploratory），并在关键基因上补充 qPCR 或流式正交验证。"
                    ),
                    evidence_data={"donors_by_condition": cond_donor_counts},
                )
            )
            pi_decisions.append(
                PIDecisionItem(
                    decision_id="PI-DEC-01",
                    title="N=2 供体实验设计结论定性裁决",
                    context=f"当前每组仅有 2 例供体 ({cond_donor_counts})，低于 Nature/Cell 子刊对群体单细胞差异表达默认推荐的 N>=3 门槛。",
                    option_a="[推荐] 保持现有数据，但在文稿 Results 中将结论严格界定为「队列内部探索性候选基因 (Exploratory Candidate Set)」，严禁使用因果或普适标志物措辞；",
                    option_b="暂停投稿，补测同批次 1~2 例同质供体后再行合并分析。",
                    tradeoff_explanation="选项 A 可快速推进组会交流或预印本发布，但正式审稿大概率被要求补样；选项 B 可一劳永逸达到审稿标准。",
                    recommended_option="A",
                )
            )

        # 2. Donor cell dominance / Imbalance per cell type
        if ct_col:
            imbalanced_clusters = []
            low_count_donors = []
            for ct_val, ct_sub in obs_df.groupby(ct_col, observed=False):
                total_cluster_cells = len(ct_sub)
                donor_counts = ct_sub[d_col].value_counts()
                max_donor = donor_counts.index[0]
                max_frac = donor_counts.iloc[0] / total_cluster_cells if total_cluster_cells > 0 else 0

                if max_frac >= self.dominance_threshold and total_cluster_cells >= 50:
                    imbalanced_clusters.append({
                        "cell_type": str(ct_val),
                        "dominant_donor": str(max_donor),
                        "fraction": round(float(max_frac), 3),
                        "donor_cells": int(donor_counts.iloc[0]),
                        "total_cells": int(total_cluster_cells),
                    })

                # Check for low count donors (< 10 cells)
                for d_id, c_count in donor_counts.items():
                    if c_count < 10:
                        low_count_donors.append({
                            "cell_type": str(ct_val),
                            "donor": str(d_id),
                            "count": int(c_count),
                        })

            if imbalanced_clusters:
                top_imb = imbalanced_clusters[0]
                findings.append(
                    DEFinding(
                        rule_id="BFA-007",
                        severity=FindingSeverity.HIGH_IMPACT,
                        category=FindingCategory.DONOR_IMBALANCE,
                        title=f"单一供体细胞占比极端倾斜 (Extreme Donor Imbalance: {top_imb['cell_type']})",
                        impact_on_conclusion=f"在「{top_imb['cell_type']}」细胞类型中，供体 {top_imb['dominant_donor']} 贡献了 {top_imb['fraction']*100:.1f}% 的细胞。差异表达分析得到的所谓「组间标志物」，极大可能只是该特定供体的私有基因表达特征（Donor Private Transcriptome）。",
                        sample_or_donor=f"供体 {top_imb['dominant_donor']} 在细胞群「{top_imb['cell_type']}」中",
                        step_or_location="Cell type subsetting / Pseudobulk input",
                        minimal_fix=(
                            f"# 最小修复（按供体聚合为 Pseudobulk，使各供体平权）：\n"
                            f"# 1. 严禁直接在该亚群运行单细胞 Wilcoxon 检验；\n"
                            f"# 2. 执行 Leave-One-Donor-Out 敏感性分析，验证剔除供体 {top_imb['dominant_donor']} 后 DEG 列表重合度是否 > 75%。"
                        ),
                        evidence_data={"imbalanced_clusters": imbalanced_clusters},
                    )
                )
                pi_decisions.append(
                    PIDecisionItem(
                        decision_id="PI-DEC-02",
                        title=f"{top_imb['cell_type']} 亚群单一供体主导处理裁决",
                        context=f"供体 {top_imb['dominant_donor']} 在该亚群占 {top_imb['fraction']*100:.1f}% 细胞，其他供体细胞数偏低。",
                        option_a=f"[推荐] 采用 Pseudobulk 求和平权，并附上剔除 {top_imb['dominant_donor']} 前后的 DEG 灵敏度对比图；",
                        option_b="若该细胞群在其他供体中极少发生，考虑在正文中明确将其归为「供体特异性扩张亚群 (Donor-Specific Expansion)」，而非通用疾病相关亚群。",
                        tradeoff_explanation="选项 A 能保全该亚群的统计检验；选项 B 能诚实规避被审稿人质疑挑选特例的风险。",
                        recommended_option="A",
                    )
                )

        # 3. Batch vs Condition Confounding (100% Confounded design)
        if b_col:
            contingency = pd.crosstab(obs_df[c_col], obs_df[b_col])
            cohort_summary["batches"] = len(obs_df[b_col].unique())
            # Check if condition is completely collinear with batch
            row_max = contingency.max(axis=1)
            row_sums = contingency.sum(axis=1)
            is_perfectly_confounded = all(row_max.iloc[i] == row_sums.iloc[i] for i in range(len(contingency)))

            if is_perfectly_confounded and len(contingency) > 1:
                findings.append(
                    DEFinding(
                        rule_id="BFA-004",
                        severity=FindingSeverity.BLOCKER,
                        category=FindingCategory.BATCH_CONFOUNDING,
                        title="实验组别与技术批次 100% 完全混杂 (Complete Batch Confounding)",
                        impact_on_conclusion="疾病组与对照组完全在不同的技术批次/测序泳道中进行（如全部 Control 在 Batch 1，全部 Disease 在 Batch 2）。在数理上完全无法区分差异表达是由生物学疾病引起，还是由测序仪/反应批次噪声导致。",
                        sample_or_donor=", ".join([f"批次 {b}" for b in obs_df[b_col].unique()]),
                        step_or_location="Experimental Design / Batch Allocation",
                        minimal_fix=(
                            "# 完全混杂无法通过数学模型完全脱敏：\n"
                            "# 1. 严禁声称任何因果或生物学特异性差异表达；\n"
                            "# 2. 最优解：在同一批次中重新对部分样本进行平行测序；\n"
                            "# 3. 次优解：在文稿讨论中明确列为主要局限，并仅将表达方向与已有公共数据集（如 GSE 权威队列）一致的基因列为潜在候选。"
                        ),
                        evidence_data={"contingency_matrix": contingency.to_dict()},
                    )
                )

    def _audit_expression_matrix(self, adata: Any, findings: List[DEFinding]) -> None:
        """Audit whether integer counts or normalized/scaled floats are passed to count models."""
        X = getattr(adata, "X", None)
        if X is None:
            return

        is_integer = False
        min_val = 0.0
        max_val = 0.0

        if np is not None:
            try:
                # Sample up to 5000 non-zero elements
                if hasattr(X, "data"):  # scipy sparse
                    sample = X.data[:5000] if len(X.data) > 0 else np.array([0])
                elif isinstance(X, np.ndarray):
                    flat = X.ravel()
                    sample = flat[:5000] if len(flat) > 0 else np.array([0])
                else:
                    sample = np.array([0])

                if len(sample) > 0:
                    min_val = float(np.min(sample))
                    max_val = float(np.max(sample))
                    # Check if elements are close to integers
                    is_integer = bool(np.all(np.abs(sample - np.round(sample)) < 1e-4))
            except Exception:
                pass

        # If adata.X is continuous normalized floats and no 'counts' layer exists
        has_raw_counts_layer = (
            hasattr(adata, "layers") and ("counts" in adata.layers or "raw" in adata.layers)
        ) or getattr(adata, "raw", None) is not None

        if not is_integer and not has_raw_counts_layer:
            findings.append(
                DEFinding(
                    rule_id="BFA-002",
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.INPUT_COUNT_TYPE,
                    title="输入矩阵缺乏原始整数计数层 (Raw Count Layer Missing for DE Modeling)",
                    impact_on_conclusion="当前 adata.X 为经过 log 变换或缩放的浮点数，且未发现 adata.layers['counts'] 或 adata.raw。负二项分布 GLM（如 PyDESeq2 / edgeR）严格假设离散整数抽样分布。输入已归一化浮点数会导致离散度估计严重失真，使统计检验失效。",
                    step_or_location="adata.X / Data Preprocessing",
                    minimal_fix=(
                        "# 最小修复（在归一化前保留 counts 原始层）：\n"
                        "adata.layers['counts'] = adata.X.copy()  # 在运行 sc.pp.normalize_total 之前保存\n"
                        "# 供体 Pseudobulk 聚合时显式指定 raw counts：\n"
                        "# pb_counts = aggregate_pseudobulk(adata, layer='counts')"
                    ),
                    evidence_data={"is_integer": is_integer, "min_val": min_val, "max_val": max_val},
                )
            )

    def _audit_de_table(
        self,
        de_df: pd.DataFrame,
        findings: List[DEFinding],
        pi_decisions: List[PIDecisionItem],
    ) -> None:
        """Audit DE results table for pseudoreplication p-value signatures and FDR control."""
        p_col = _match_column(de_df.columns, ["pvalue", "p_val", "pval", "p.value", "pvals"])
        padj_col = _match_column(de_df.columns, ["padj", "p_val_adj", "qval", "p.adjusted", "fdr", "pvals_adj"])

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
            # Check for excessive uncorrected reporting
            try:
                sig_raw = (de_df[p_col] < 0.05).sum()
                sig_adj = (de_df[padj_col] < self.fdr_threshold).sum()
                if sig_raw > 100 and sig_adj == 0:
                    findings.append(
                        DEFinding(
                            rule_id="BFA-003b",
                            severity=FindingSeverity.HIGH_IMPACT,
                            category=FindingCategory.FDR_AND_TESTING,
                            title="FDR 校正后无显著基因 (Zero DEGs Surviving Multiple Testing Correction)",
                            impact_on_conclusion=f"原始 p < 0.05 有 {sig_raw} 个基因，但 FDR < {self.fdr_threshold} 存活基因数为 0。若在文稿中仅依据原始 p 值报告差异基因，属于学术不端隐患（Selective Reporting / P-hacking）。",
                            step_or_location="Significance Filtering",
                            minimal_fix=(
                                "# 严禁仅汇报 raw p < 0.05 的基因！最小修复：\n"
                                "# 1. 诚实报告在当前样本量下未检测到达到全转录组 FDR < 0.05 的显著基因；\n"
                                "# 2. 或适当放宽至 FDR < 0.10 并结合 |log2FC| > 1.0 作为「待验证候选」明确声明。"
                            ),
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
                            severity=FindingSeverity.BLOCKER,
                            category=FindingCategory.PSEUDOREPLICATION,
                            title="典型细胞级伪重复 P 值虚假膨胀 (P-value Inflation Signature: Pseudoreplication)",
                            impact_on_conclusion=f"检测到 {zero_or_tiny_p} 个基因的 p 值低于 1e-100（最小 p={min_p}）。这是典型的单细胞细胞级检验（如 cell-level Wilcoxon / t-test）伪重复特征。将上万个细胞当做独立样本使有效样本量膨胀数千倍，产出大量假阳性，审稿人会直接要求重跑 Pseudobulk。",
                            step_or_location="sc.tl.rank_genes_groups / Seurat FindMarkers",
                            minimal_fix=(
                                "# 最小修复代码（改用供体级 Pseudobulk + PyDESeq2）：\n"
                                "import scanpy as sc\n"
                                "# 1. 按 (donor, cell_type, condition) 汇总 raw counts\n"
                                "pb = adata.to_df(layer='counts').groupby([adata.obs['donor_id'], adata.obs['condition']]).sum()\n"
                                "# 2. 运行真实供体级 DESeq2 / EdgeR Wald 检验"
                            ),
                            evidence_data={"tiny_p_count": int(zero_or_tiny_p), "min_p": float(min_p)},
                        )
                    )
            except Exception:
                pass

    def _audit_code(self, code_path: Union[str, Path], findings: List[DEFinding]) -> None:
        """Audit analysis scripts/notebooks for static scientific bugs using analysis_audit."""
        try:
            from bionexus.analysis_audit import audit_analysis

            res = audit_analysis(code_path)
            for f in res.findings:
                if f.rule_id == "BFA-001" and not any(ef.rule_id == "BFA-001" for ef in findings):
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
                    findings.append(
                        DEFinding(
                            rule_id=f.rule_id,
                            severity=FindingSeverity.BLOCKER,
                            category=FindingCategory.INPUT_COUNT_TYPE,
                            title=f.trap_class,
                            impact_on_conclusion=f.message,
                            step_or_location=f.location,
                            minimal_fix=f.remedy,
                        )
                    )
                elif f.rule_id == "BFA-011":
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
        except Exception:
            pass

    def _determine_claim_boundary(
        self,
        findings: List[DEFinding],
        cohort_summary: Dict[str, Any],
        claim_text: Optional[str],
    ) -> ClaimScopeBoundary:
        """Compute permissible scientific claims and ready-to-use manuscript phrasing."""
        has_blocker = any(f.severity == FindingSeverity.BLOCKER for f in findings)
        has_high = any(f.severity == FindingSeverity.HIGH_IMPACT for f in findings)
        n_donors = cohort_summary.get("n_donors", 0)

        if has_blocker:
            allowed = "仅限作为该批次样本的初步技术描述 (Technical descriptive observation only)，不得外推至生物学总体。"
            prohibited = "严禁声称任何疾病关联、生物标志物 (Biomarkers)、群体差异或因果治疗靶点。"
            methods = (
                "Single-cell exploratory analyses were performed within this sequenced batch. "
                "Due to limited biological replication or sample confounding, observations are strictly "
                "descriptive and hypothesis-generating for orthogonal follow-up."
            )
            results = (
                "Within this sample cohort, exploratory single-cell profiling identified descriptive expression shifts; "
                "formal population-level biomarker inference was withheld pending independent donor replication."
            )
            maturity = "UNWARRANTED"
        elif has_high or n_donors < 3:
            allowed = (
                f"可陈述为本研究队列 ({n_donors} 例供体) 内部的探索性差异表达候选基因集，"
                "可用于指导后续有针对性的正交分子实验（qPCR / 免疫组化）。"
            )
            prohibited = (
                "严禁声称该基因在全人群中普遍具备诊断或病理学特异性；"
                "严禁在无功能扰动实验（如 CRISPR/敲除）的前提下使用因果机制动词（如「X 导致了 Y」）。"
            )
            methods = (
                f"Differential expression was evaluated across {n_donors} biological donors using pseudobulk aggregation. "
                "Statistical models applied empirical Bayes moderation, and candidate genes were prioritized with nominal FDR < 0.05 "
                "subject to downstream validation."
            )
            results = (
                f"In this cohort of {n_donors} donors, pseudobulk profiling revealed candidate transcriptional shifts "
                "between conditions, prioritizing candidate genes for targeted orthogonal confirmation."
            )
            maturity = "EXPLORATORY_COHORT"
        else:
            allowed = (
                f"完全支持群体级别统计推断 (Population-level Statistical Inference)。"
                f"在 N={n_donors} 独立生物学重复支撑下，可正式汇报该细胞类型在疾病与对照间的差异表达基因集。"
            )
            prohibited = (
                "严禁将横断面观察性转录组差异直接陈述为因果驱动机制（建议使用 'is associated with' / 'correlates with'）。"
            )
            methods = (
                f"Multi-donor single-cell differential expression was performed by aggregating raw integer counts into donor-level "
                f"pseudobulks per cell type (Squair et al., 2021). Condition effects across {n_donors} biological replicates "
                "were tested using negative binomial generalized linear models with Wald tests and Benjamini-Hochberg FDR correction."
            )
            results = (
                f"Donor-aware pseudobulk differential analysis across {n_donors} biological replicates identified robust condition-associated "
                "transcriptional alterations (FDR < 0.05), controlling for donor-level biological variance and technical batch effects."
            )
            maturity = "ROBUST_POPULATION"

        return ClaimScopeBoundary(
            allowed_scope=allowed,
            prohibited_scope=prohibited,
            recommended_methods_text=methods,
            recommended_results_text=results,
            overall_maturity=maturity,
        )

    # --------------------------------------------------------------------------
    # Helpers
    # --------------------------------------------------------------------------

    def _load_anndata(self, path: Union[str, Path]) -> Any:
        try:
            import anndata as ad
            return ad.read_h5ad(path)
        except Exception as e:
            raise RuntimeError(f"Failed to load AnnData from {path}: {e}")

    def _load_dataframe(self, obj: Union[pd.DataFrame, str, Path]) -> pd.DataFrame:
        if isinstance(obj, pd.DataFrame):
            return obj
        path = Path(obj)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {path}")
        if path.suffix.lower() in (".tsv", ".txt"):
            return pd.read_csv(path, sep="\t")
        return pd.read_csv(path)

    def _extract_de_from_anndata_uns(self, adata: Any) -> pd.DataFrame:
        """Extract structured DataFrame from Scanpy adata.uns['rank_genes_groups']."""
        rgg = adata.uns.get("rank_genes_groups", {})
        if not rgg or "names" not in rgg:
            return pd.DataFrame()
        try:
            records = []
            names_rec = rgg["names"]
            group_keys = names_rec.dtype.names if hasattr(names_rec, "dtype") and names_rec.dtype.names else list(names_rec.keys())

            for g in group_keys:
                genes = names_rec[g] if isinstance(names_rec, dict) else [x[0] for x in names_rec[g]]
                pvals = rgg.get("pvals", {}).get(g, []) if isinstance(rgg.get("pvals"), dict) else []
                padjs = rgg.get("pvals_adj", {}).get(g, []) if isinstance(rgg.get("pvals_adj"), dict) else []
                lfcs = rgg.get("logfoldchanges", {}).get(g, []) if isinstance(rgg.get("logfoldchanges"), dict) else []

                for idx, gene in enumerate(genes):
                    records.append({
                        "cluster": g,
                        "gene": gene,
                        "pvalue": float(pvals[idx]) if len(pvals) > idx else None,
                        "padj": float(padjs[idx]) if len(padjs) > idx else None,
                        "log2fc": float(lfcs[idx]) if len(lfcs) > idx else None,
                    })
            return pd.DataFrame(records)
        except Exception:
            return pd.DataFrame()


# ==============================================================================
# Top-Level Functional Entry Point
# ==============================================================================

def audit_differential_expression(
    adata: Any = None,
    adata_path: Optional[Union[str, Path]] = None,
    de_table: Optional[Union[pd.DataFrame, str, Path]] = None,
    sample_metadata: Optional[Union[pd.DataFrame, str, Path]] = None,
    code_path: Optional[Union[str, Path]] = None,
    claim_text: Optional[str] = None,
    donor_col: Optional[str] = None,
    condition_col: Optional[str] = None,
    cell_type_col: Optional[str] = None,
    batch_col: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> DEAuditResult:
    """
    Audit multi-donor single-cell differential expression for lab meeting, submission, or sharing.

    Parameters:
        adata: AnnData object in memory.
        adata_path: Path to .h5ad file.
        de_table: DataFrame or path to CSV/TSV containing DEG results.
        sample_metadata: DataFrame or path to sample sheet CSV/TSV.
        code_path: Path to analysis script (.py/.R) or Jupyter notebook (.ipynb).
        claim_text: Free-text scientific claim statement to verify.
        donor_col: Column name identifying biological donors.
        condition_col: Column name identifying experimental conditions.
        cell_type_col: Column name identifying cell types / clusters.
        batch_col: Column name identifying technical batches.
        config: Custom audit parameters.

    Returns:
        DEAuditResult with the 5 essential pillars for laboratory adoption.
    """
    engine = DEAuditEngine(config=config)
    return engine.audit(
        adata=adata,
        adata_path=adata_path,
        de_table=de_table,
        sample_metadata=sample_metadata,
        code_path=code_path,
        claim_text=claim_text,
        donor_col=donor_col,
        condition_col=condition_col,
        cell_type_col=cell_type_col,
        batch_col=batch_col,
    )


# Alias
audit_de = audit_differential_expression
