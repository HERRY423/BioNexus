"""
DE Audit Engine orchestrator and top-level execution interface.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from bionexus.de.binding import (
    _audit_claim_vs_table_facts,
    _collect_execution_record,
    _execution_json_object,
    _verify_execution_binding,
)
from bionexus.de.models import (
    CheckRecord,
    CheckStatus,
    ClaimScopeBoundary,
    DEAuditResult,
    DEFinding,
    ExecutionRecord,
    FindingCategory,
    FindingSeverity,
    PIDecisionItem,
)
from bionexus.de.parsers import (
    BATCH_KEYWORDS,
    CELLTYPE_KEYWORDS,
    CONDITION_KEYWORDS,
    DONOR_KEYWORDS,
    _extract_de_from_anndata_uns,
    _load_anndata,
    _load_dataframe,
    _match_column,
)
from bionexus.de.policy import (
    _compute_overall_status,
    _determine_claim_boundary,
    _set_check_status,
)
from bionexus.de.rules import (
    _audit_code,
    _audit_de_table,
    _audit_expression_matrix,
    _audit_metadata,
    _record_metadata_checks,
)
from bionexus.de_audit_extract import extract_rank_genes_groups

if TYPE_CHECKING:
    import pandas as pd
else:
    try:
        import pandas as pd
    except ImportError:
        pd = None

logger = logging.getLogger(__name__)


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
        execution_record: Optional[Union[Dict[str, Any], ExecutionRecord, str, Path]] = None,
        claim_contract: Optional[Union[str, Path]] = None,
        alternative_plan: Optional[Union[str, Path]] = None,
        alternative_runs: Optional[Union[str, Path]] = None,
        selection_history: Optional[Union[str, Path]] = None,
        selection_expected_head: Optional[str] = None,
    ) -> DEAuditResult:
        """Run the 5-pillar differential expression evidence audit."""
        findings: List[DEFinding] = []
        checks: List[CheckRecord] = []
        pi_decisions: List[PIDecisionItem] = []
        cohort_summary: Dict[str, Any] = {}
        cols_used: Dict[str, str] = {}
        rgg_params: Dict[str, Any] = {}
        supplied = any(
            x is not None
            for x in (adata, adata_path, de_table, sample_metadata, code_path, claim_text, execution_record,
                      claim_contract, alternative_plan, alternative_runs, selection_history, selection_expected_head)
        )

        # 1. Resolve AnnData object if provided
        if adata is None and adata_path is not None:
            adata = self._load_anndata(adata_path)

        # 2. Extract or resolve sample/cell metadata
        obs_df: Optional[pd.DataFrame] = None
        if adata is not None and hasattr(adata, "obs"):
            obs_df = adata.obs
        elif sample_metadata is not None:
            obs_df = self._load_dataframe(sample_metadata)

        # 3. Resolve DE results table. Parse failure is a check outcome, not an empty pass.
        de_df: Optional[pd.DataFrame] = None
        de_parse_error: Optional[str] = None
        de_source = "none"
        if de_table is not None:
            de_df = self._load_dataframe(de_table)
            de_source = "de_table"
            if de_df is None or (pd is not None and de_df.empty):
                de_df = None
                de_source = "none"
        elif adata is not None and hasattr(adata, "uns") and "rank_genes_groups" in adata.uns:
            extracted = extract_rank_genes_groups(adata)
            rgg_params = dict(extracted.params or {})
            de_source = extracted.source or "rank_genes_groups"
            if extracted.error:
                de_parse_error = extracted.error
                de_df = None
                findings.append(
                    DEFinding(
                        rule_id="BFA-PARSE",
                        severity=FindingSeverity.HIGH_IMPACT,
                        category=FindingCategory.FDR_AND_TESTING,
                        title="差异表达结果解析失败 (rank_genes_groups parse failure)",
                        impact_on_conclusion=(
                            "adata.uns['rank_genes_groups'] 存在但未能按 Scanpy 官方结构读取基因标识与统计量。"
                            "不得将空表当作已检查的阴性结果。"
                        ),
                        step_or_location="adata.uns['rank_genes_groups']",
                        minimal_fix="使用 scanpy.get.rank_genes_groups_df(adata) 导出完整基因名、pvals、pvals_adj、logfoldchanges 后再审计。",
                        evidence_data={"parse_error": extracted.error, "source": extracted.source},
                    )
                )
            else:
                de_df = extracted.frame

        # 4. Infer metadata column mappings
        d_col = c_col = ct_col = b_col = None
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
                cohort_summary["condition_key"] = c_col
            if ct_col:
                cols_used["cell_type"] = ct_col
            if b_col:
                cols_used["batch"] = b_col

            self._audit_metadata(
                obs_df=obs_df,
                d_col=d_col,
                c_col=c_col,
                ct_col=ct_col,
                b_col=b_col,
                findings=findings,
                pi_decisions=pi_decisions,
                cohort_summary=cohort_summary,
                checks=checks,
            )
        else:
            checks.append(
                CheckRecord(
                    check_id="donor_replicates",
                    title="供体/生物学重复设计",
                    status=CheckStatus.MISSING_EVIDENCE,
                    summary="未提供样本表或 adata.obs，无法检查供体重复。",
                    required_for_pass=True,
                )
            )
            checks.append(
                CheckRecord(
                    check_id="batch_confounding",
                    title="批次与组别混杂",
                    status=CheckStatus.MISSING_EVIDENCE,
                    summary="未提供样本设计，批次混杂未评估。",
                    required_for_pass=False,
                )
            )
            checks.append(
                CheckRecord(
                    check_id="donor_imbalance",
                    title="供体细胞贡献失衡",
                    status=CheckStatus.MISSING_EVIDENCE,
                    summary="未提供细胞级元数据，供体失衡未评估。",
                    required_for_pass=False,
                )
            )

        # 5. Matrix-level audits
        if adata is not None:
            self._audit_expression_matrix(adata, findings, checks)
        else:
            checks.append(
                CheckRecord(
                    check_id="input_count_type",
                    title="原始整数计数层",
                    status=CheckStatus.MISSING_EVIDENCE,
                    summary="未提供表达矩阵，计数层未评估。",
                    required_for_pass=False,
                )
            )

        # 6. DE table audits
        if de_parse_error and de_source != "none":
            checks.append(
                CheckRecord(
                    check_id="de_results",
                    title="差异表达结果表",
                    status=CheckStatus.PARSE_FAILED,
                    summary=de_parse_error,
                    required_for_pass=True,
                )
            )
            checks.append(
                CheckRecord(
                    check_id="fdr_and_testing",
                    title="FDR / 多重检验",
                    status=CheckStatus.PARSE_FAILED,
                    summary="结果表解析失败，FDR 未评估。",
                    required_for_pass=True,
                )
            )
        elif de_df is not None and not (pd is not None and de_df.empty):
            checks.append(
                CheckRecord(
                    check_id="de_results",
                    title="差异表达结果表",
                    status=CheckStatus.ASSESSED,
                    summary=f"已读取 {len(de_df)} 行差异表达结果（来源: {de_source}）。",
                    required_for_pass=True,
                )
            )
            self._audit_de_table(de_df, findings, pi_decisions, checks, claim_text=claim_text)
        else:
            checks.append(
                CheckRecord(
                    check_id="de_results",
                    title="差异表达结果表",
                    status=CheckStatus.MISSING_EVIDENCE,
                    summary=de_parse_error or "未提供 DE 表或可解析的 rank_genes_groups。",
                    required_for_pass=True,
                )
            )
            checks.append(
                CheckRecord(
                    check_id="fdr_and_testing",
                    title="FDR / 多重检验",
                    status=CheckStatus.MISSING_EVIDENCE,
                    summary="无差异表达结果，FDR 未评估。",
                    required_for_pass=True,
                )
            )

        # 7. Code / notebook audit
        if code_path is not None:
            self._audit_code(code_path, findings, checks)
        else:
            checks.append(
                CheckRecord(
                    check_id="analysis_code",
                    title="分析脚本/笔记本",
                    status=CheckStatus.MISSING_EVIDENCE,
                    summary="未提供分析脚本，静态方法学调用未评估。",
                    required_for_pass=False,
                )
            )

        execution = self._collect_execution_record(
            de_df=de_df,
            de_source=de_source,
            rgg_params=rgg_params,
            code_path=code_path,
            findings=findings,
            supplied_execution=execution_record,
        )
        if execution.cell_level_condition_test and not any(f.rule_id == "BFA-001" for f in findings):
            findings.append(
                DEFinding(
                    rule_id="BFA-001",
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.PSEUDOREPLICATION,
                    title="执行记录显示细胞级条件差异检验 (Cell-level condition DE)",
                    impact_on_conclusion=(
                        f"rank_genes_groups params 记录 method={execution.method}，"
                        "这是细胞级检验，不能当作供体级 NB GLM / Wald 结果。"
                    ),
                    step_or_location="adata.uns['rank_genes_groups']['params']",
                    minimal_fix="按 (donor, cell_type, condition) 聚合 raw counts 后用 PyDESeq2 / edgeR 做供体级检验。",
                    evidence_data={"params": rgg_params},
                )
            )
            self._set_check_status(
                checks,
                "de_results",
                CheckStatus.ISSUE_FOUND,
                f"执行记录为细胞级方法 {execution.method}，不能支持群体推断。",
            )

        # 8. Check Analysis Execution & Artifact Binding (Format Recognized -> Analysis Fact Verified)
        is_donor_execution_verified = self._verify_execution_binding(
            execution=execution,
            supplied_execution=execution_record,
            de_table=de_table,
            de_df=de_df,
            obs_df=obs_df,
            cohort_summary=cohort_summary,
            findings=findings,
            checks=checks,
            sample_metadata_source=sample_metadata,
        )

        # Decouple BFA-001c when donor execution binding is verified and p > 0
        if is_donor_execution_verified:
            for f in findings:
                if f.rule_id == "BFA-001c":
                    min_p_val = f.evidence_data.get("min_p", 0.0) if f.evidence_data else 0.0
                    if min_p_val > 0.0:
                        f.severity = FindingSeverity.ADVISORY
                        f.impact_on_conclusion = (
                            f"检测到 {f.evidence_data.get('tiny_p_count', 0)} 个基因的 p 值低于 1e-100（最小 p={min_p_val:.2e}）。"
                            "已核验供体级执行凭证且未发现 p=0 极端数值截断。根据核心科学准则，extreme P 是 diagnostic signal，"
                            "不是 methodological invalidity 的充分条件。该数值本身不能证明效应大小或生物学有效性，"
                            "作为审阅提示（ADVISORY）保留，不阻断群体推断通过。"
                        )

        # 9. Targeted User Scientific Claim Audit (Analysis Fact Verified -> Specific Claim Supported)
        if claim_text and str(claim_text).strip():
            self._audit_claim_vs_table_facts(
                claim_text=str(claim_text).strip(),
                de_df=de_df,
                findings=findings,
                checks=checks,
            )
            try:
                from bionexus.claim_semantics import (
                    DeterministicClaimParser,
                    DeterministicWarrantEngine,
                    EvidenceProfile,
                )
                claim_ir = DeterministicClaimParser.parse(str(claim_text).strip(), claim_id="CLAIM-USER-DE")
                reps_count = cohort_summary.get("n_donors") or 0
                has_observational = bool(de_df is not None and not de_df.empty)

                ev_profile = EvidenceProfile(
                    observational_data=has_observational,
                    biological_replicates_count=reps_count,
                    pseudobulk_aggregated=is_donor_execution_verified,
                    confound_controls=[],
                    perturbation=False,
                    clinical_ground_truth=False,
                    regulatory_certification=False,
                    causal_identification_status="UNASSESSED",
                )

                warrant_res = DeterministicWarrantEngine.evaluate(claim_ir, ev_profile)
                if claim_ir.generalization_scope.value == "population_general":
                    checks.append(CheckRecord(
                        check_id="claim_population_transport", title="总体外推证据",
                        status=CheckStatus.MISSING_EVIDENCE, required_for_pass=True,
                        summary="供体数与 DE 结果不能证明目标总体代表性；总体外推需要独立的抽样与适用域审阅。",
                    ))
                if warrant_res.is_fully_warranted:
                    checks.append(
                        CheckRecord(
                            check_id="claim_targeted_warrant",
                            title="科学声明定向审计",
                            status=CheckStatus.ASSESSED,
                            summary=f"声明符合当前证据支持边界：{warrant_res.epistemic_summary}",
                            required_for_pass=False,
                        )
                    )
                else:
                    gap_str = ", ".join(warrant_res.evidence_gaps) if warrant_res.evidence_gaps else "缺乏因果扰动或临床实证"
                    findings.append(
                        DEFinding(
                            rule_id="BFA-008",
                            severity=FindingSeverity.HIGH_IMPACT,
                            category=FindingCategory.CLAIM_BOUNDARY,
                            title="科学声明超出证据边界 (Claim Exceeds Evidence Ceiling)",
                            impact_on_conclusion=(
                                f"用户提交的具体声明 '{claim_text}' 断言了超出当前证据上限的结论 "
                                f"（请求类别: {warrant_res.requested_claim_class}，证据上限: {warrant_res.evidence_ceiling}）。"
                                f"缺失关键证据: {gap_str}。"
                            ),
                            step_or_location="User Claim Text Audit",
                            claim_affected=str(claim_text),
                            minimal_fix="修改文稿声明，仅陈述为已观察到的转录组差异表达关联，不得在无扰动实验或临床金标准时断言因果靶点。",
                            evidence_data=warrant_res.to_dict(),
                        )
                    )
                    checks.append(
                        CheckRecord(
                            check_id="claim_targeted_warrant",
                            title="科学声明定向审计",
                            status=CheckStatus.ISSUE_FOUND,
                            summary=f"声明超出证据边界：{warrant_res.epistemic_summary} (缺失: {gap_str})",
                            required_for_pass=True,
                        )
                    )
            except Exception as exc:
                logger.warning("Targeted claim audit encountered exception: %s", exc)
                checks.append(CheckRecord(
                    check_id="claim_targeted_warrant", title="科学声明定向审计",
                    status=CheckStatus.PARSE_FAILED, required_for_pass=True,
                    summary="声明审阅失败，无法判定证据是否支持该声明；必须复核，不能按通过处理。",
                ))

        condition_report = None
        if claim_contract is not None:
            from bionexus.de.conditions import CONFLICT, SAT, UNKNOWN, verify_de_claim_conditions

            try:
                condition_report = verify_de_claim_conditions(
                    claim_contract, de_table=de_table,
                    sample_metadata=obs_df if adata is not None else sample_metadata,
                )
                for claim in condition_report["claims"]:
                    status = claim["status"]
                    checks.append(CheckRecord(
                        check_id=f"claim_conditions:{claim['claim']['claim_id']}",
                        title="声明成立条件的可执行验证",
                        status=(CheckStatus.ASSESSED if status == SAT else
                                CheckStatus.MISSING_EVIDENCE if status == UNKNOWN else CheckStatus.ISSUE_FOUND),
                        summary=f"{claim['canonical_statement']} [{status}]", required_for_pass=True,
                    ))
                    if status not in (SAT, UNKNOWN):
                        findings.append(DEFinding(
                            rule_id="BFA-009", severity=FindingSeverity.HIGH_IMPACT,
                            category=FindingCategory.CLAIM_BOUNDARY,
                            title="声明前提冲突" if status == CONFLICT else "声明必要前提不满足",
                            impact_on_conclusion=claim["canonical_statement"],
                            claim_affected=claim["claim"]["claim_id"],
                            minimal_fix="查看逐项条件及修复要求；仍可保留已验证的较窄表述。",
                            evidence_data=claim,
                        ))
            except (OSError, ValueError, TypeError) as exc:
                checks.append(CheckRecord(
                    check_id="claim_conditions", title="声明成立条件的可执行验证",
                    status=CheckStatus.PARSE_FAILED, required_for_pass=True,
                    summary=f"无法读取或验证声明合同：{exc}",
                ))

        alternative_report = None
        if alternative_plan is not None or alternative_runs is not None:
            from bionexus.de.alternatives import evaluate_alternative_plan

            try:
                if alternative_plan is None:
                    raise ValueError("Alternative results require a frozen plan")
                alternative_report = evaluate_alternative_plan(
                    alternative_plan, alternative_runs, claim_contract=claim_contract, de_table=de_table,
                    sample_metadata=obs_df if adata is not None else sample_metadata,
                )
                checks.append(CheckRecord(
                    check_id="alternative_analysis_coverage", title="合理替代分析覆盖",
                    status=CheckStatus.ASSESSED if alternative_report["complete"] else CheckStatus.MISSING_EVIDENCE,
                    summary="所有分支均完成可比检查；稳健性请看逐项变化。" if alternative_report["complete"]
                    else "部分计划分支缺失、无效或不可估计；不可宣称完整稳健性。", required_for_pass=True,
                ))
                for item in alternative_report["claims"]:
                    if item["dependencies"]:
                        findings.append(DEFinding(
                            rule_id="BFA-010", severity=FindingSeverity.ADVISORY,
                            category=FindingCategory.CLAIM_BOUNDARY, title="结论对替代分析的依赖",
                            impact_on_conclusion=f"{item['claim_id']}: {item['status']}。原始结果与稳健性分别保留。",
                            claim_affected=item["claim_id"], evidence_data=item,
                            minimal_fix="按具体供体或分析选择报告变化；失去显著性不等于效应不存在。",
                        ))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                checks.append(CheckRecord(
                    check_id="alternative_analysis_coverage", title="合理替代分析覆盖",
                    status=CheckStatus.PARSE_FAILED, required_for_pass=True, summary=str(exc),
                ))

        from bionexus.de.selection import evaluate_selection_history
        selection_report = evaluate_selection_history()
        if selection_history is not None or selection_expected_head is not None:
            try:
                selection_report = evaluate_selection_history(
                    selection_history, expected_head=selection_expected_head, claim_contract=claim_contract,
                    alternative_plan=alternative_plan, de_table=de_table,
                    sample_metadata=obs_df if adata is not None else sample_metadata,
                )
                checks.append(CheckRecord(
                    check_id="selection_history", title="分析选择历史",
                    status=CheckStatus.ISSUE_FOUND if selection_report["status"] == "SELECTION_DEPENDENCE_RECORDED"
                    else CheckStatus.ASSESSED if selection_report["status"] == "PRE_RESULT_PLAN_RECORDED"
                    else CheckStatus.MISSING_EVIDENCE,
                    summary=f"{selection_report['status']}；确认性用途：{selection_report['confirmatory_use']}。",
                    required_for_pass=True,
                ))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                selection_report.update(status="INVALID_HISTORY", error=str(exc))
                checks.append(CheckRecord(
                    check_id="selection_history", title="分析选择历史", status=CheckStatus.PARSE_FAILED,
                    required_for_pass=True, summary=str(exc),
                ))

        claim_boundary = self._determine_claim_boundary(
            findings, cohort_summary, claim_text, [c for c in checks if c.check_id != "selection_history"], execution
        )
        if selection_history is not None or selection_expected_head is not None:
            claim_boundary.prohibited_scope += " 不得把选择历史一致性写成已证实的预注册或确认性验证。"
            if selection_report["status"] == "SELECTION_DEPENDENCE_RECORDED":
                claim_boundary.allowed_scope += " 选择历史显示结果依赖的选择；在原有证据范围内按探索性结果披露。"
            else:
                claim_boundary.allowed_scope += " 确认性用途尚未由选择历史建立。"
        overall_status = self._compute_overall_status(findings, checks, execution, supplied)

        return DEAuditResult(
            overall_status=overall_status,
            findings=findings,
            checks=checks,
            execution_record=execution,
            claim_boundary=claim_boundary,
            pi_decisions=pi_decisions,
            cohort_summary=cohort_summary,
            metadata_columns_used=cols_used,
            claim_conditions=condition_report,
            alternative_analysis=alternative_report,
            selection_history=selection_report,
        )

    # --------------------------------------------------------------------------
    # Backward compatibility delegate methods
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
        checks: List[CheckRecord],
    ) -> None:
        _audit_metadata(
            obs_df=obs_df,
            d_col=d_col,
            c_col=c_col,
            ct_col=ct_col,
            b_col=b_col,
            findings=findings,
            pi_decisions=pi_decisions,
            cohort_summary=cohort_summary,
            checks=checks,
            dominance_threshold=self.dominance_threshold,
            min_donors_required=self.min_donors_required,
            min_cells_per_donor=self.min_cells_per_donor,
        )

    def _record_metadata_checks(
        self,
        checks: List[CheckRecord],
        findings: List[DEFinding],
        d_col: Optional[str],
        c_col: Optional[str],
        ct_col: Optional[str],
        b_col: Optional[str],
        cond_donor_counts: Dict[str, int],
    ) -> None:
        _record_metadata_checks(
            checks=checks,
            findings=findings,
            d_col=d_col,
            c_col=c_col,
            ct_col=ct_col,
            b_col=b_col,
            cond_donor_counts=cond_donor_counts,
        )

    def _audit_expression_matrix(
        self,
        adata: Any,
        findings: List[DEFinding],
        checks: List[CheckRecord],
    ) -> None:
        _audit_expression_matrix(adata, findings, checks)

    def _audit_de_table(
        self,
        de_df: pd.DataFrame,
        findings: List[DEFinding],
        pi_decisions: List[PIDecisionItem],
        checks: List[CheckRecord],
        claim_text: Optional[str] = None,
    ) -> None:
        _audit_de_table(
            de_df=de_df,
            findings=findings,
            pi_decisions=pi_decisions,
            checks=checks,
            fdr_threshold=self.fdr_threshold,
            claim_text=claim_text,
        )

    def _audit_code(
        self,
        code_path: Union[str, Path],
        findings: List[DEFinding],
        checks: List[CheckRecord],
    ) -> None:
        _audit_code(code_path, findings, checks)

    @staticmethod
    def _set_check_status(
        checks: List[CheckRecord],
        check_id: str,
        status: CheckStatus,
        summary: str,
    ) -> None:
        _set_check_status(checks, check_id, status, summary)

    def _collect_execution_record(
        self,
        de_df: Optional[pd.DataFrame],
        de_source: str,
        rgg_params: Dict[str, Any],
        code_path: Optional[Union[str, Path]],
        findings: List[DEFinding],
        supplied_execution: Optional[Union[Dict[str, Any], ExecutionRecord, str, Path]] = None,
    ) -> ExecutionRecord:
        return _collect_execution_record(
            de_df=de_df,
            de_source=de_source,
            rgg_params=rgg_params,
            code_path=code_path,
            findings=findings,
            supplied_execution=supplied_execution,
        )

    @staticmethod
    def _execution_json_object(pairs: List[tuple[str, Any]]) -> Dict[str, Any]:
        return _execution_json_object(pairs)

    def _verify_execution_binding(
        self,
        execution: ExecutionRecord,
        supplied_execution: Optional[Union[Dict[str, Any], ExecutionRecord, str, Path]],
        de_table: Optional[Union[pd.DataFrame, str, Path]],
        de_df: Optional[pd.DataFrame],
        obs_df: Optional[pd.DataFrame],
        cohort_summary: Dict[str, Any],
        findings: List[DEFinding],
        checks: List[CheckRecord],
        sample_metadata_source: Optional[Union[pd.DataFrame, str, Path]] = None,
    ) -> bool:
        return _verify_execution_binding(
            execution=execution,
            supplied_execution=supplied_execution,
            de_table=de_table,
            de_df=de_df,
            obs_df=obs_df,
            cohort_summary=cohort_summary,
            findings=findings,
            checks=checks,
            sample_metadata_source=sample_metadata_source,
        )

    def _audit_claim_vs_table_facts(
        self,
        claim_text: str,
        de_df: Optional[pd.DataFrame],
        findings: List[DEFinding],
        checks: List[CheckRecord],
    ) -> bool:
        return _audit_claim_vs_table_facts(
            claim_text=claim_text,
            de_df=de_df,
            findings=findings,
            checks=checks,
            fdr_threshold=self.fdr_threshold,
        )

    def _compute_overall_status(
        self,
        findings: List[DEFinding],
        checks: List[CheckRecord],
        execution: ExecutionRecord,
        supplied: bool,
    ) -> str:
        return _compute_overall_status(findings, checks, execution, supplied)

    def _determine_claim_boundary(
        self,
        findings: List[DEFinding],
        cohort_summary: Dict[str, Any],
        claim_text: Optional[str],
        checks: List[CheckRecord],
        execution: ExecutionRecord,
    ) -> ClaimScopeBoundary:
        return _determine_claim_boundary(
            findings=findings,
            cohort_summary=cohort_summary,
            claim_text=claim_text,
            checks=checks,
            execution=execution,
            fdr_threshold=self.fdr_threshold,
        )

    def _load_anndata(self, path: Union[str, Path]) -> Any:
        return _load_anndata(path)

    def _load_dataframe(self, obj: Union[pd.DataFrame, str, Path]) -> pd.DataFrame:
        return _load_dataframe(obj)

    def _extract_de_from_anndata_uns(self, adata: Any) -> pd.DataFrame:
        return _extract_de_from_anndata_uns(adata)


def audit_differential_expression(
    adata: Any = None,
    adata_path: Optional[Union[str, Path]] = None,
    de_table: Optional[Union[pd.DataFrame, str, Path]] = None,
    sample_metadata: Optional[Union[pd.DataFrame, str, Path]] = None,
    code_path: Optional[Union[str, Path]] = None,
    execution_record: Optional[Union[Dict[str, Any], ExecutionRecord, str, Path]] = None,
    claim_text: Optional[str] = None,
    donor_col: Optional[str] = None,
    condition_col: Optional[str] = None,
    cell_type_col: Optional[str] = None,
    batch_col: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    claim_contract: Optional[Union[str, Path]] = None,
    alternative_plan: Optional[Union[str, Path]] = None,
    alternative_runs: Optional[Union[str, Path]] = None,
    selection_history: Optional[Union[str, Path]] = None,
    selection_expected_head: Optional[str] = None,
) -> DEAuditResult:
    """
    Audit multi-donor single-cell differential expression for lab meeting, submission, or sharing.

    Parameters:
        adata: AnnData object in memory.
        adata_path: Path to .h5ad file.
        de_table: DataFrame or path to CSV/TSV containing DEG results.
        sample_metadata: DataFrame or path to sample sheet CSV/TSV.
        code_path: Path to analysis script (.py/.R) or Jupyter notebook (.ipynb).
        execution_record: Optional execution record dict, ExecutionRecord, or JSON path.
        claim_text: Free-text scientific claim statement to verify.
        donor_col: Column name identifying biological donors.
        condition_col: Column name identifying experimental conditions.
        cell_type_col: Column name identifying cell types / clusters.
        batch_col: Column name identifying technical batches.
        config: Custom audit parameters.
        claim_contract: Optional artifact-bound structured DE claim contract JSON.
        alternative_plan: Frozen alternative analysis plan.
        alternative_runs: Result-slot manifest bound to that plan.
        selection_history: Scoped host export of analysis choices and exposures.
        selection_expected_head: Optional independently retained history head.

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
        execution_record=execution_record,
        claim_text=claim_text,
        donor_col=donor_col,
        condition_col=condition_col,
        cell_type_col=cell_type_col,
        batch_col=batch_col,
        claim_contract=claim_contract,
        alternative_plan=alternative_plan,
        alternative_runs=alternative_runs,
        selection_history=selection_history,
        selection_expected_head=selection_expected_head,
    )


# Alias
audit_de = audit_differential_expression
