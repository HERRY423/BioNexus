"""
Execution artifact binding and claim-fact concordance verification for DE audits.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from bionexus.de.models import (
    CELL_LEVEL_DE_METHODS,
    DE_SUCCESS_FIT_STATUSES,
    DONOR_LEVEL_TABLE_MARKERS,
    CheckRecord,
    CheckStatus,
    DEFinding,
    ExecutionRecord,
    FindingCategory,
    FindingSeverity,
)

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd
else:
    try:
        import numpy as np
    except ImportError:
        np = None
    try:
        import pandas as pd
    except ImportError:
        pd = None

logger = logging.getLogger(__name__)


def _execution_json_object(pairs: List[tuple[str, Any]]) -> Dict[str, Any]:
    """Parse JSON object preserving order while rejecting duplicate keys."""
    record: Dict[str, Any] = {}
    for key, value in pairs:
        if key in record:
            raise ValueError(f"Duplicate execution record key: {key}")
        record[key] = value
    return record


def _collect_execution_record(
    de_df: Optional[pd.DataFrame],
    de_source: str,
    rgg_params: Dict[str, Any],
    code_path: Optional[Union[str, Path]],
    findings: List[DEFinding],
    supplied_execution: Optional[Union[Dict[str, Any], ExecutionRecord, str, Path]] = None,
) -> ExecutionRecord:
    """Collect facts that may be stated in past tense, taken only from supplied artifacts."""
    facts: List[str] = []
    method = None
    fdr_method = None
    aggregation = None
    source = "none"
    cell_level = False

    if isinstance(supplied_execution, ExecutionRecord):
        return supplied_execution

    exec_dict: Dict[str, Any] = {}
    if isinstance(supplied_execution, dict):
        exec_dict = supplied_execution
    elif isinstance(supplied_execution, (str, Path)):
        p = Path(supplied_execution)
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    exec_dict = json.load(f, object_pairs_hook=_execution_json_object)
            except Exception as exc:
                logger.warning("Failed to parse execution record JSON from %s: %s", p, exc)

    if isinstance(exec_dict, dict) and exec_dict:
        source = "execution_record"
        method = exec_dict.get("method")
        fdr_method = exec_dict.get("fdr_method") or exec_dict.get("corr_method")
        stat_unit = str(exec_dict.get("statistical_unit") or exec_dict.get("unit") or "").lower()
        agg = str(exec_dict.get("aggregation") or "").lower()
        if stat_unit in ("donor", "sample", "biological_replicate"):
            aggregation = "donor_pseudobulk"
        elif agg:
            aggregation = agg

        if exec_dict.get("cell_level_condition_test"):
            cell_level = True
            aggregation = "cell"

        design = exec_dict.get("design") or exec_dict.get("design_matrix_columns") or exec_dict.get("formula")
        facts.append(
            f"Supplied execution metadata (not authenticated): method={method!r}, statistical_unit={stat_unit or aggregation!r}, "
            f"design={design!r}."
        )

    if rgg_params:
        source = source if source != "none" else "rank_genes_groups"
        method = method or rgg_params.get("method")
        fdr_method = fdr_method or rgg_params.get("corr_method")
        groupby = str(rgg_params.get("groupby") or "")
        facts.append(
            f"adata.uns['rank_genes_groups']['params'] records method={method!r}, "
            f"groupby={groupby!r}, corr_method={fdr_method!r}."
        )
        method_key = str(method or "").lower().replace("-", "_")
        condition_like = any(
            token in groupby.lower()
            for token in ("condition", "treatment", "group", "genotype", "stim", "disease")
        )
        if method_key.replace("_", "-") in CELL_LEVEL_DE_METHODS or method_key in {
            m.replace("-", "_") for m in CELL_LEVEL_DE_METHODS
        }:
            if condition_like:
                cell_level = True
                aggregation = "cell"
                facts.append(
                    "This is a cell-level ranking method; donor-level count-model testing was not recorded."
                )

    if de_df is not None and pd is not None and not de_df.empty:
        cols = {str(c).lower().replace("_", "") for c in de_df.columns}
        if DONOR_LEVEL_TABLE_MARKERS.intersection(cols):
            source = source if source != "none" else "de_table"
            format_markers = sorted(DONOR_LEVEL_TABLE_MARKERS.intersection(cols))
            facts.append(
                f"DE table columns match count-model format markers ({format_markers}); "
                "format recognized, but table headers alone do not verify execution binding."
            )
        if "padj" in cols or "pvalsadj" in cols or "fdr" in cols or "qval" in cols:
            fdr_method = fdr_method or "adjusted_p_present"
            facts.append("An adjusted p-value / FDR column is present in the supplied DE table.")
        if de_source == "de_table" and source == "none":
            source = "de_table"
            facts.append(f"A DE table with {len(de_df)} rows was supplied and inspected.")

    if code_path is not None and any(f.step_or_location and "code" in (f.step_or_location or "").lower() for f in findings):
        source = source if source != "none" else "code"

    if not facts:
        facts.append("No analysis execution record was supplied; no completed differential-expression method is confirmed.")

    return ExecutionRecord(
        source=source,
        method=method,
        fdr_method=fdr_method,
        aggregation=aggregation,
        cell_level_condition_test=cell_level,
        facts=facts,
    )


def _verify_execution_binding(
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
    """Verify execution record binding and input integrity."""
    if supplied_execution is None:
        checks.append(
            CheckRecord(
                check_id="analysis_execution_binding",
                title="分析事实与执行记录绑定",
                status=CheckStatus.MISSING_EVIDENCE,
                summary="未提供经核查的供体级执行记录（统计单位、设计矩阵、拟合状态未绑定）。",
                required_for_pass=True,
            )
        )
        return False

    exec_dict: Dict[str, Any] = {}
    if isinstance(supplied_execution, dict):
        exec_dict = supplied_execution
    elif isinstance(supplied_execution, ExecutionRecord):
        exec_dict = {
            "statistical_unit": "donor" if execution.aggregation == "donor_pseudobulk" else execution.aggregation,
            "method": execution.method,
            "cell_level_condition_test": execution.cell_level_condition_test,
        }
    elif isinstance(supplied_execution, (str, Path)):
        p = Path(supplied_execution)
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    exec_dict = json.load(f, object_pairs_hook=_execution_json_object)
            except Exception as exc:
                logger.warning("Failed to parse execution record JSON from %s: %s", p, exc)
                checks.append(
                    CheckRecord(
                        check_id="analysis_execution_binding",
                        title="分析事实与执行记录绑定",
                        status=CheckStatus.PARSE_FAILED,
                        summary=f"执行记录 JSON 解析失败: {exc}",
                        required_for_pass=True,
                    )
                )
                return False

    if not isinstance(exec_dict, dict):
        checks.append(CheckRecord(
            check_id="analysis_execution_binding", title="分析事实与执行记录绑定",
            status=CheckStatus.PARSE_FAILED, summary="执行记录必须是 JSON object。",
            required_for_pass=True,
        ))
        return False

    if not exec_dict:
        checks.append(
            CheckRecord(
                check_id="analysis_execution_binding",
                title="分析事实与执行记录绑定",
                status=CheckStatus.MISSING_EVIDENCE,
                summary="执行记录为空或未提供有效内容。",
                required_for_pass=True,
            )
        )
        return False

    binding_issues: List[str] = []
    missing: List[str] = []
    for primary, alias in (("statistical_unit", "unit"), ("design", "formula"), ("result_sha256", "receipt_result_sha256")):
        if primary in exec_dict and alias in exec_dict and exec_dict[primary] != exec_dict[alias]:
            binding_issues.append(f"执行记录别名冲突: {primary}/{alias}")

    # 1. Statistical unit check
    stat_unit = str(exec_dict.get("statistical_unit") or exec_dict.get("unit") or "").lower()
    agg = str(exec_dict.get("aggregation") or "").lower()
    if not stat_unit:
        missing.append("statistical_unit")
    elif stat_unit not in ("donor", "sample", "biological_replicate"):
        binding_issues.append("统计单位未明确为生物学重复单位")
    if agg and agg not in ("donor_pseudobulk", "pseudobulk", "donor", "sample", "biological_replicate"):
        binding_issues.append("aggregation 与供体级统计单位不一致或不受支持")
    cell_flag = exec_dict.get("cell_level_condition_test", False)
    if not isinstance(cell_flag, bool):
        binding_issues.append("cell_level_condition_test 必须为布尔值")
    if cell_flag or execution.cell_level_condition_test:
        binding_issues.append("执行记录包含细胞级条件检验")
    method = exec_dict.get("method")
    if not isinstance(method, str) or not method.strip():
        missing.append("method")
    elif method.lower().replace("_", "-") in {m.replace("_", "-") for m in CELL_LEVEL_DE_METHODS}:
        binding_issues.append("method 是细胞级排名方法，不能凭 donor 标签认证为供体模型")

    # 2. Fit status check
    fit_status = str(exec_dict.get("fit_status") or "").upper().strip()
    if not fit_status:
        missing.append("fit_status")
    elif fit_status not in DE_SUCCESS_FIT_STATUSES:
        binding_issues.append(f"未确认成功拟合状态 ({fit_status})")
    if fit_status:
        if fit_status in ("FAILED", "ERROR", "DIVERGED", "NON_CONVERGED", "FAIL"):
            findings.append(
                DEFinding(
                    rule_id="BFA-013b",
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.INPUT_COUNT_TYPE,
                    title="差异表达模型拟合失败 (Model Fitting Failed/Diverged)",
                    impact_on_conclusion=(
                        f"执行记录显示模型拟合状态为 {fit_status}。模型未成功收敛，"
                        "输出的统计检验量与 p 值为无效或不可信计算结果。"
                    ),
                    step_or_location="execution_record.fit_status",
                    minimal_fix="检查输入 counts 质量、离散度拟合参数或样本分组设计，确保模型成功收敛后重新导出执行记录。",
                    evidence_data={"fit_status": fit_status},
                )
            )
            binding_issues.append(f"模型拟合状态失败 ({fit_status})")

    # 3. Result Table SHA-256 Hash Verification
    expected_hash = str(
        exec_dict.get("result_sha256")
        or exec_dict.get("receipt_result_sha256")
        or ""
    ).strip().lower()
    if not expected_hash:
        missing.append("result_sha256")
    if expected_hash:
        if set(expected_hash) == {"0"} or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            findings.append(
                DEFinding(
                    rule_id="BFA-013a",
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.FDR_AND_TESTING,
                    title="执行记录哈希无效或篡改 (Execution Record SHA-256 Tampered/Invalid)",
                    impact_on_conclusion=(
                        f"执行记录中的结果表 SHA-256 哈希全为零或格式无效 ('{expected_hash[:16]}...')，属于不可信或被篡改凭证。"
                    ),
                    step_or_location="execution_record.result_sha256",
                    minimal_fix="生成并绑定包含真实数据文件 SHA-256 签名的有效执行记录。",
                    evidence_data={"expected_hash": expected_hash},
                )
            )
            binding_issues.append("结果表哈希全为零或无效")
        else:
            actual_file_hash = None
            if isinstance(de_table, (str, Path)) and Path(de_table).is_file():
                try:
                    result_bytes = Path(de_table).read_bytes()
                    actual_file_hash = hashlib.sha256(result_bytes).hexdigest().lower()
                    if pd is not None:
                        sep = "\t" if Path(de_table).suffix.lower() in (".tsv", ".txt") else ","
                        bound_frame = pd.read_csv(io.BytesIO(result_bytes), sep=sep)
                        if de_df is None or not bound_frame.equals(de_df):
                            binding_issues.append("哈希对应结果内容与本次已读取的表格不一致")
                except Exception as exc:
                    logger.warning("Failed to compute hash for %s: %s", de_table, exc)

            if actual_file_hash is None:
                missing.append("可读取的原始结果文件（DataFrame 不保留原始文件字节）")
            if actual_file_hash and actual_file_hash != expected_hash:
                findings.append(
                    DEFinding(
                        rule_id="BFA-013a",
                        severity=FindingSeverity.BLOCKER,
                        category=FindingCategory.FDR_AND_TESTING,
                        title="结果表内容与执行记录哈希不匹配 (Result Table Hash Mismatch)",
                        impact_on_conclusion=(
                            f"结果表实际 SHA-256 ({actual_file_hash[:16]}...) 与执行记录预期哈希 ({expected_hash[:16]}...) 不一致，"
                            "存在产物篡改、未记录变更或版本脱节。"
                        ),
                        step_or_location="execution_record.result_sha256 vs de_table",
                        minimal_fix="核验结果表版本并重新绑定与实际检验产物一致的执行记录。",
                        evidence_data={"observed_sha256": actual_file_hash, "expected_sha256": expected_hash},
                    )
                )
                binding_issues.append(f"结果表哈希不匹配 (预期 {expected_hash[:8]}..., 实际 {actual_file_hash[:8]}...)")

    # 4. Design Formula vs Design Matrix Columns
    design_formula = str(exec_dict.get("design") or exec_dict.get("formula") or "").strip()
    matrix_cols = exec_dict.get("design_matrix_columns")
    if not design_formula:
        missing.append("design")
    valid_columns = (
        isinstance(matrix_cols, list) and bool(matrix_cols)
        and all(isinstance(c, str) and c.strip() for c in matrix_cols)
    )
    if not valid_columns:
        missing.append("design_matrix_columns (非空字符串列表)")
    if design_formula and valid_columns and isinstance(matrix_cols, list):
        if len(set(matrix_cols)) != len(matrix_cols):
            binding_issues.append("设计矩阵列重复")
        rhs = design_formula.removeprefix("~").strip()
        terms = [t.strip() for t in rhs.split("+")]
        if not design_formula.startswith("~") or any(not re.fullmatch(r"[A-Za-z_]\w*|[01]", t) for t in terms):
            missing.append("支持的加法设计公式（复杂设计需外部审阅）")
        else:
            factors = set(terms) - {"0", "1"}
            column_factors = {re.split(r"[\[.]", c)[0] for c in matrix_cols if c != "Intercept"}
            if not factors or factors != column_factors:
                binding_issues.append("设计公式项与设计矩阵列不一致")
            condition_col = cohort_summary.get("condition_key")
            if condition_col and condition_col not in factors:
                binding_issues.append("设计公式未包含所审核条件")
        formula_has_donor = any(
            k in design_formula.lower()
            for k in ("donor", "replicate", "patient", "subject", "individual")
        )
        matrix_has_donor = any(
            ("donor" in c.lower() or "replicate" in c.lower() or "subject" in c.lower() or "patient" in c.lower())
            for c in matrix_cols
        )
        if formula_has_donor != matrix_has_donor:
            findings.append(
                DEFinding(
                    rule_id="BFA-013c",
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.PSEUDOREPLICATION,
                    title="模型设计公式与设计矩阵列冲突 (Formula Conflicts with Design Matrix Columns)",
                    impact_on_conclusion=(
                        f"声明的模型公式 '{design_formula}'（供体控制: {formula_has_donor}）"
                        f"与拟合设计矩阵列（包含供体列: {matrix_has_donor}）存在冲突。"
                        "无法证实实际拟合的模型是否对供体效应进行了控制。"
                    ),
                    step_or_location="execution_record.design vs design_matrix_columns",
                    minimal_fix="核对拟合脚本中的模型公式，确保公式与实际输入模型的设计矩阵保持一致（如 ~ donor + condition）。",
                    evidence_data={"formula": design_formula, "matrix_columns": matrix_cols},
                )
            )
            binding_issues.append("设计公式与设计矩阵列冲突")

    # 5. Cohort Sample / Donor Count Consistency
    rec_donors = exec_dict.get("n_donors")
    obs_donors = cohort_summary.get("n_donors")
    valid_donors = isinstance(rec_donors, int) and not isinstance(rec_donors, bool) and rec_donors > 0
    if not valid_donors:
        missing.append("n_donors (正整数)")
    if obs_df is None or obs_donors is None:
        missing.append("可核查的供体元数据")
    donor_ids = exec_dict.get("donor_ids")
    donor_ids_bound_from_metadata = False
    if "donor_ids" not in exec_dict:
        expected_metadata_hash = str(exec_dict.get("sample_metadata_sha256") or "").strip().lower()
        metadata_path = None
        if isinstance(sample_metadata_source, (str, Path)):
            candidate = Path(sample_metadata_source)
            if candidate.is_file():
                metadata_path = candidate
        if not expected_metadata_hash:
            missing.append("donor_ids 或 sample_metadata_sha256 绑定的原始样本表")
        elif set(expected_metadata_hash) == {"0"} or not re.fullmatch(r"[0-9a-f]{64}", expected_metadata_hash):
            findings.append(
                DEFinding(
                    rule_id="BFA-013e",
                    severity=FindingSeverity.BLOCKER,
                    category=FindingCategory.DONOR_IMBALANCE,
                    title="样本元数据哈希无效 (Invalid Sample Metadata SHA-256)",
                    impact_on_conclusion=(
                        "旧版收据缺少 donor_ids，且 sample_metadata_sha256 不是有效的非零小写 SHA-256。"
                        "不能从未绑定的样本表恢复供体标识。"
                    ),
                    step_or_location="execution_record.sample_metadata_sha256",
                    minimal_fix="提供有效且与原始样本表文件完全匹配的 SHA-256，或提供明确的 donor_ids。",
                    evidence_data={"expected_sha256": expected_metadata_hash},
                )
            )
            binding_issues.append("样本元数据 SHA-256 无效")
        elif metadata_path is None:
            missing.append("donor_ids（仅有样本表哈希时必须提供可读取的原始样本表文件）")
        else:
            try:
                metadata_bytes = metadata_path.read_bytes()
                actual_metadata_hash = hashlib.sha256(metadata_bytes).hexdigest().lower()
                if pd is not None:
                    sep = "\t" if metadata_path.suffix.lower() in (".tsv", ".txt") else ","
                    bound_metadata = pd.read_csv(io.BytesIO(metadata_bytes), sep=sep)
                    if actual_metadata_hash != expected_metadata_hash:
                        findings.append(
                            DEFinding(
                                rule_id="BFA-013e",
                                severity=FindingSeverity.BLOCKER,
                                category=FindingCategory.DONOR_IMBALANCE,
                                title="样本元数据与执行记录哈希不匹配 (Sample Metadata Hash Mismatch)",
                                impact_on_conclusion=(
                                    f"样本表实际 SHA-256 ({actual_metadata_hash[:16]}...) 与执行记录预期哈希 "
                                    f"({expected_metadata_hash[:16]}...) 不一致，不能从该文件恢复供体绑定。"
                                ),
                                step_or_location="execution_record.sample_metadata_sha256 vs sample_metadata",
                                minimal_fix="提供执行时使用且 SHA-256 与收据一致的原始样本元数据文件，或提供明确的 donor_ids。",
                                evidence_data={
                                    "observed_sha256": actual_metadata_hash,
                                    "expected_sha256": expected_metadata_hash,
                                },
                            )
                        )
                        binding_issues.append("样本元数据哈希不匹配")
                    elif obs_df is None or not bound_metadata.equals(obs_df):
                        binding_issues.append("哈希对应样本元数据与本次已读取的表格不一致")
                    elif not cohort_summary.get("donors"):
                        missing.append("可从绑定样本表解析的供体标识")
                    else:
                        donor_ids_bound_from_metadata = True
            except Exception as exc:
                logger.warning("Failed to bind sample metadata from %s: %s", metadata_path, exc)
                missing.append("可读取并解析的原始样本表文件")
    elif not isinstance(donor_ids, list) or not donor_ids or not all(isinstance(d, str) and d.strip() for d in donor_ids):
        binding_issues.append("donor_ids 必须为非空且仅含非空字符串的列表")
    elif (len(set(donor_ids)) != len(donor_ids)
          or set(donor_ids) != {str(d) for d in cohort_summary.get("donors", [])}):
        binding_issues.append("执行记录供体标识与元数据不一致或重复")
    if valid_donors and obs_donors is not None and rec_donors != obs_donors:
        findings.append(
            DEFinding(
                rule_id="BFA-013d",
                severity=FindingSeverity.BLOCKER,
                category=FindingCategory.DONOR_IMBALANCE,
                title="执行记录供体数与元数据样本表不一致 (Cohort Donor Count Mismatch)",
                impact_on_conclusion=f"执行记录记录了 {rec_donors} 个供体，但提供的样本表仅包含 {obs_donors} 个供体。",
                step_or_location="execution_record.n_donors vs sample_metadata",
                minimal_fix="提供与执行记录严格对应的样本元数据表。",
                evidence_data={"recorded_donors": rec_donors, "observed_donors": obs_donors},
            )
        )
        binding_issues.append(f"供体数不一致 (记录: {rec_donors}, 样本表: {obs_donors})")

    if binding_issues:
        issue_summary = "；".join(binding_issues)
        checks.append(
            CheckRecord(
                check_id="analysis_execution_binding",
                title="分析事实与执行记录绑定",
                status=CheckStatus.ISSUE_FOUND,
                summary=f"已核查执行记录：发现破坏或矛盾（{issue_summary}）。",
                required_for_pass=True,
            )
        )
        return False

    if missing:
        checks.append(CheckRecord(
            check_id="analysis_execution_binding", title="分析事实与执行记录绑定",
            status=CheckStatus.MISSING_EVIDENCE,
            summary="执行绑定未完成，缺失或无法核查：" + "；".join(missing),
            required_for_pass=True,
        ))
        return False

    checks.append(
        CheckRecord(
            check_id="analysis_execution_binding",
            title="分析事实与执行记录绑定",
            status=CheckStatus.ASSESSED,
            summary=(
                "记录声明供体级成功拟合；设计公式/列名及供体数量一致，结果文件 SHA-256 匹配。"
                + (
                    "旧版收据未重复列出 donor_ids；供体标识来自与 sample_metadata_sha256 完全匹配的原始样本表文件。"
                    if donor_ids_bound_from_metadata else "执行记录 donor_ids 与样本表一致。"
                )
                + "此为输入一致性核查，不证明真实模型执行、生产者身份或科学有效性。"
            ),
            required_for_pass=True,
        )
    )
    return True


def _audit_claim_vs_table_facts(
    claim_text: str,
    de_df: Optional[pd.DataFrame],
    findings: List[DEFinding],
    checks: List[CheckRecord],
    fdr_threshold: float = 0.05,
) -> bool:
    """Verify natural language statements against the exact differential expression table facts."""
    if de_df is None or (pd is not None and de_df.empty) or not claim_text or not str(claim_text).strip():
        return False

    text = str(claim_text).strip()
    from bionexus.claim_semantics import DeterministicClaimParser
    text = DeterministicClaimParser.strip_reporting_preamble(text)

    clauses = [part.strip() for part in re.split(
        r"[;；。]|\.(?=\s+[A-Za-z])|(?:,\s*|，\s*)(?=[A-Za-z0-9_.-]+\s*(?:(?:is|are|was|were)\b|显著|不显著|未|非|上调|下调|表达|是|为)|在|该|其)|\b(?:and|but|whereas|while)\s+(?=[A-Za-z0-9_.-]+\s+(?:is|are|was|were)\b)",
        text, flags=re.I,
    ) if part.strip()]
    if len(clauses) > 1:
        outcomes = [_audit_claim_vs_table_facts(part, de_df, findings, checks, fdr_threshold) for part in clauses]
        return all(outcomes)

    statistic = r"\bsignifican(?:t|tly)\b|显著"
    direction = r"\b(?:up-?regulated|down-?regulated)\b|上调|下调|高表达|低表达"
    negated_direction = re.search(
        r"\b(?:not|never|no|neither)\b[^.;]{0,40}\b(?:up-?regulated|down-?regulated)\b|(?:不|未|无|非)[^，。；]{0,12}(?:上调|下调|高表达|低表达)",
        text, re.I,
    )
    repeated_predicate = len(re.findall(statistic, text, re.I)) > 1 or len(re.findall(direction, text, re.I)) > 1
    conjunctions = list(re.finditer(r"[,，]|\b(?:and|but|whereas|while|or)\b|[且并]", text, re.I))
    unbound_conjunction = any(
        not re.match(r"(?:and|且|并且)\s*(?:is\s+)?(?:significant\b|up-?regulated\b|down-?regulated\b|显著|上调|下调)", text[m.start():], re.I)
        for m in conjunctions
    )
    if negated_direction or repeated_predicate or (unbound_conjunction and re.search(f"{statistic}|{direction}", text, re.I)):
        checks.append(CheckRecord(
            check_id="claim_fact_concordance", title="声明微观事实核查",
            status=CheckStatus.MISSING_EVIDENCE, required_for_pass=True,
            summary="否定方向、矛盾断言或未解析的复合声明无法唯一绑定检验；需要拆分声明并复核，不得按通过处理。",
        ))
        return False
    stopwords = {
        "this", "the", "these", "those", "our", "for", "in", "no", "none", "all", "each",
        "both", "result", "results", "analysis", "data", "table", "method", "genes", "degs",
        "supplied", "conclusion", "reported", "tested", "control", "treated"
    }

    # Resolve gene column
    gene_col = None
    for cand in ["gene", "symbol", "names", "gene_name", "id"]:
        if cand in de_df.columns:
            gene_col = cand
            break

    table_genes = {}
    if gene_col:
        table_genes = {str(g).upper(): str(g) for g in de_df[gene_col].dropna()}
    elif de_df.index.name in ("gene", "symbol", "gene_name") or (not de_df.empty and isinstance(de_df.index[0], str)):
        table_genes = {str(g).upper(): str(g) for g in de_df.index}

    # Resolve padj and lfc columns
    padj_col = None
    for cand in ["padj", "pvals_adj", "pvalsadj", "adj_p", "fdr", "qval"]:
        if cand in de_df.columns:
            padj_col = cand
            break

    lfc_col = None
    for cand in ["log2FoldChange", "log2foldchange", "logfoldchanges", "logfc", "lfc"]:
        if cand in de_df.columns:
            lfc_col = cand
            break

    # 1. Global null check
    has_global_null_claim = bool(
        re.search(r"\b(?:no\s+genes\s+were\s+significant|zero\s+significant\s+genes?|none\s+of\s+the\s+genes\s+were\s+significant)\b", text, re.I)
        or re.search(r"无显著基因|未见显著基因|没有显著基因|fdr\s*后无显著|校正后无显著|全表无显著", text, re.I)
    )
    if has_global_null_claim:
        adjusted = pd.to_numeric(de_df[padj_col], errors="coerce") if (pd is not None and padj_col) else None
        if adjusted is None or (np is not None and not np.isfinite(adjusted).all()):
            checks.append(CheckRecord(
                check_id="claim_fact_concordance", title="声明微观事实核查",
                status=CheckStatus.MISSING_EVIDENCE,
                summary="全表无显著声明需要所有所述检验的有效调整 p 值；缺失值不等于不显著。",
                required_for_pass=True,
            ))
            return False
        sig_count = (adjusted < fdr_threshold).sum()
        if sig_count > 0:
            findings.append(
                DEFinding(
                    rule_id="BFA-015c",
                    severity=FindingSeverity.HIGH_IMPACT,
                    category=FindingCategory.CLAIM_BOUNDARY,
                    title="虚假声称全局无显著差异基因 (False Global Null Assertion)",
                    impact_on_conclusion=(
                        f"声明声称在 FDR 校正后无任何显著基因，但结果表中实际检测到 {sig_count} 个显著基因 (padj < {fdr_threshold})。"
                    ),
                    step_or_location="claim_text vs de_table",
                    minimal_fix="更正文稿声明，结果表中存在已达到统计显著的基因，不应声称为全表无显著。",
                    evidence_data={"significant_gene_count": int(sig_count)},
                )
            )
            checks.append(
                CheckRecord(
                    check_id="claim_fact_concordance",
                    title="声明微观事实核查",
                    status=CheckStatus.ISSUE_FOUND,
                    summary=f"全局无显著声明与表格矛盾：表中有 {sig_count} 个显著基因。",
                    required_for_pass=True,
                )
            )
            return False

    # 2. Extract focal gene
    mentioned = [gene for gene in table_genes if re.search(r"(?<![\w.-])" + re.escape(gene) + r"(?![\w.-])", text, re.I)]
    focal_gene = None
    if len(mentioned) == 1:
        focal_gene = table_genes[mentioned[0]]
    elif len(mentioned) > 1:
        checks.append(CheckRecord(
            check_id="claim_fact_concordance", title="声明微观事实核查",
            status=CheckStatus.MISSING_EVIDENCE, required_for_pass=True,
            summary="声明包含多个基因或基因对应多行检验，无法唯一绑定；请按基因和比较组拆分审阅。",
        ))
        return False
    else:
        gene_patterns = [
            r"\b(?:contains\s+a\s+result\s+for|result\s+for)\s+([A-Za-z0-9_.-]+)",
            r"\bprove\s+that\s+([A-Za-z0-9_.-]+)\b",
            r"\b([A-Za-z0-9_.-]+)\s*(?:基因)?\s*(?:表达)?\s*(?:显著)?\s*(?:上调|下调|高表达|低表达)",
            r"\b([A-Za-z0-9_.-]+)\s*(?:基因)?\s*(?:表达)?\s*(?:是|为)?\s*(?:不显著|显著)",
            r"\b([A-Za-z0-9_.-]+)\s+(?:is|are|was|were)\s+(?:significantly\s+)?(up-?regulated|down-?regulated)\b",
            r"\b([A-Za-z0-9_.-]+)\s+(?:is|are|was|were)\s+(not\s+significant|significant)\b",
            r"\b([A-Za-z0-9_.-]+)\s+(?:causes|drives|is\s+a\s+clinically\s+validated)\b",
        ]
        for pat in gene_patterns:
            m = re.search(pat, text, re.I)
            if m:
                cand = m.group(1).strip().rstrip(". ,;:")
                if cand.lower() not in stopwords and len(cand) >= 2:
                    focal_gene = cand
                    break

        if not focal_gene:
            tokens = [t.strip(". ,;:") for t in text.split()]
            for t in tokens:
                if t.upper() in table_genes and t.lower() not in stopwords:
                    focal_gene = t
                    break

    if not focal_gene:
        if not has_global_null_claim and re.search(r"\bsignifican(?:t|tly)\b|up-?regulated|down-?regulated|显著|上调|下调", text, re.I):
            checks.append(CheckRecord(
                check_id="claim_fact_concordance", title="声明微观事实核查",
                status=CheckStatus.MISSING_EVIDENCE, required_for_pass=True,
                summary="无法把该统计或方向声明唯一绑定到结果表；请提供独立、明确的单基因声明。",
            ))
            return False
        return True

    focal_upper = focal_gene.upper()
    if table_genes and focal_upper not in table_genes:
        findings.append(
            DEFinding(
                rule_id="BFA-014",
                severity=FindingSeverity.HIGH_IMPACT,
                category=FindingCategory.CLAIM_BOUNDARY,
                title=f"声称的基因在结果表中不存在 (Asserted Gene Not in DE Table: {focal_gene})",
                impact_on_conclusion=f"声明中提及的基因 '{focal_gene}' 未在提供的差异表达结果表中找到，无法支持针对该基因的具体推断。",
                step_or_location="claim_text vs de_table",
                minimal_fix=f"核对基因标识符 '{focal_gene}' 是否存在于当前分析的基因集或输入数据中。",
                evidence_data={"missing_gene": focal_gene},
            )
        )
        checks.append(
            CheckRecord(
                check_id="claim_fact_concordance",
                title="声明微观事实核查",
                status=CheckStatus.ISSUE_FOUND,
                summary=f"声明提及的基因 '{focal_gene}' 在结果表中不存在。",
                required_for_pass=True,
            )
        )
        return False

    actual_gene = table_genes.get(focal_upper, focal_gene)
    if gene_col:
        rows = de_df[de_df[gene_col].astype(str) == actual_gene]
    else:
        rows = de_df[de_df.index.astype(str) == actual_gene]

    if len(rows) != 1:
        checks.append(CheckRecord(
            check_id="claim_fact_concordance", title="声明微观事实核查",
            status=CheckStatus.MISSING_EVIDENCE, required_for_pass=True,
            summary="声明包含多个基因或基因对应多行检验，无法唯一绑定；请按基因和比较组拆分审阅。",
        ))
        return False

    row = rows.iloc[0]
    has_issue = False

    # Direction check
    lfc_val = pd.to_numeric(row.get(lfc_col), errors="coerce") if (pd is not None and lfc_col) else None
    directional = bool(re.search(r"\b(?:up-?regulated|down-?regulated)\b|上调|下调|高表达|低表达", text, re.I))
    if directional and (lfc_val is None or (np is not None and not np.isfinite(lfc_val))):
        checks.append(CheckRecord(
            check_id="claim_fact_concordance", title="声明微观事实核查",
            status=CheckStatus.MISSING_EVIDENCE, required_for_pass=True,
            summary="方向声明缺少有限的效应值，不能验证上调或下调。",
        ))
        return False
    if lfc_val is not None:
        if re.search(r"\bup-?regulated\b|上调|高表达", text, re.I) and lfc_val <= 0:
            has_issue = True
            findings.append(
                DEFinding(
                    rule_id="BFA-015d",
                    severity=FindingSeverity.HIGH_IMPACT,
                    category=FindingCategory.CLAIM_BOUNDARY,
                    title=f"基因表达差异方向与声明相反 (Wrong Direction Assertion: {actual_gene})",
                    impact_on_conclusion=f"声明声称基因 '{actual_gene}' 上调表达 (upregulated)，但结果表中估计的 log2FC 非正 ({lfc_val:.4f})，不支持上调。",
                    step_or_location=f"claim_text vs de_table.{lfc_col}",
                    minimal_fix=f"核对组别对比方向及效应值，修正基因 '{actual_gene}' 的上调声明；零效应不支持任一方向。",
                    evidence_data={"gene": actual_gene, "log2FoldChange": lfc_val},
                )
            )
        elif re.search(r"\bdown-?regulated\b|下调|低表达", text, re.I) and lfc_val >= 0:
            has_issue = True
            findings.append(
                DEFinding(
                    rule_id="BFA-015d",
                    severity=FindingSeverity.HIGH_IMPACT,
                    category=FindingCategory.CLAIM_BOUNDARY,
                    title=f"基因表达差异方向与声明相反 (Wrong Direction Assertion: {actual_gene})",
                    impact_on_conclusion=f"声明声称基因 '{actual_gene}' 下调表达 (downregulated)，但结果表中估计的 log2FC 非负 ({lfc_val:.4f})，不支持下调。",
                    step_or_location=f"claim_text vs de_table.{lfc_col}",
                    minimal_fix=f"核对组别对比方向及效应值，修正基因 '{actual_gene}' 的下调声明；零效应不支持任一方向。",
                    evidence_data={"gene": actual_gene, "log2FoldChange": lfc_val},
                )
            )

    # Significance check
    is_negated_sig = bool(re.search(
        r"\b(?:not\s+(?:statistically\s+)?significant|no\s+(?:statistically\s+)?significant|non[- ]significant)\b|不显著|未达显著|无显著|未见显著|未发现显著",
        text, re.I,
    ))
    is_positive_sig = bool(re.search(r"\b(?:significant|significantly)\b|显著", text, re.I)) and not is_negated_sig
    padj_val = pd.to_numeric(row.get(padj_col), errors="coerce") if (pd is not None and padj_col) else None
    if (is_negated_sig or is_positive_sig) and (padj_val is None or (np is not None and not np.isfinite(padj_val))):
        checks.append(CheckRecord(
            check_id="claim_fact_concordance", title="声明微观事实核查",
            status=CheckStatus.MISSING_EVIDENCE,
            summary=f"{actual_gene} 的显著性声明缺少有效调整 p 值；缺失检验不等于阴性结果。",
            required_for_pass=True,
        ))
        return False
    if padj_val is not None:
        if is_negated_sig and padj_val < fdr_threshold:
            has_issue = True
            findings.append(
                DEFinding(
                    rule_id="BFA-015b",
                    severity=FindingSeverity.HIGH_IMPACT,
                    category=FindingCategory.CLAIM_BOUNDARY,
                    title=f"错误否定真实显著基因 (False Negative Assertion: {actual_gene})",
                    impact_on_conclusion=f"声明声称基因 '{actual_gene}' 不显著，但结果表中实际 padj={padj_val:.4e} < {fdr_threshold}，已达到统计显著标准。",
                    step_or_location=f"claim_text vs de_table.{padj_col}",
                    minimal_fix=f"核对分析结果，基因 '{actual_gene}' 已达到显著标准，避免陈述为不显著。",
                    evidence_data={"gene": actual_gene, "padj": padj_val},
                )
            )
        elif is_positive_sig and padj_val >= fdr_threshold:
            has_issue = True
            findings.append(
                DEFinding(
                    rule_id="BFA-015a",
                    severity=FindingSeverity.HIGH_IMPACT,
                    category=FindingCategory.CLAIM_BOUNDARY,
                    title=f"虚假声称基因统计显著 (False Significance Assertion: {actual_gene})",
                    impact_on_conclusion=f"声明声称基因 '{actual_gene}' 在 FDR 校正后显著，但实际结果表中该基因 padj={padj_val:.4f} >= {fdr_threshold}，未达到显著阈值。",
                    step_or_location=f"claim_text vs de_table.{padj_col}",
                    minimal_fix=f"修正文稿声明，不得将未达到 FDR < {fdr_threshold} 阈值的基因 '{actual_gene}' 声称为显著差异基因。",
                    evidence_data={"gene": actual_gene, "padj": padj_val},
                )
            )

    if has_issue:
        checks.append(
            CheckRecord(
                check_id="claim_fact_concordance",
                title="声明微观事实核查",
                status=CheckStatus.ISSUE_FOUND,
                summary=f"声明中对基因 '{actual_gene}' 的方向或显著性断言与结果表矛盾。",
                required_for_pass=True,
            )
        )
        return False

    checks.append(
        CheckRecord(
            check_id="claim_fact_concordance",
            title="声明微观事实核查",
            status=CheckStatus.ASSESSED,
            summary=f"已核查声明对基因 '{actual_gene}' 的断言：方向与显著性与结果表一致。",
            required_for_pass=False,
        )
    )
    return True
