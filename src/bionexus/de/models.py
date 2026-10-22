"""
Domain models, enums, and data contracts for differential expression evidence audits.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

DE_EXECUTION_RECEIPT_COMPATIBILITY_SCHEMA = "bionexus.de-execution-receipt-compatibility.v1"
DE_SUCCESS_FIT_STATUSES = frozenset(
    {"SUCCESS", "SUCCEEDED", "CONVERGED", "COMPLETE", "COMPLETED", "PASS", "PASSED", "OK"}
)


def _portable_diagnostics(value: Any) -> Any:
    """Retain invalid numeric diagnostics without emitting nonstandard JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"numeric_state": "NONFINITE", "representation": repr(value)}
    if isinstance(value, dict):
        return {key: _portable_diagnostics(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_portable_diagnostics(item) for item in value]
    return value


class FindingSeverity(str, Enum):
    """Severity of an audit finding for biological conclusions."""
    BLOCKER = "BLOCKER"          # 🔴 阻断：结论在数理或统计学上不成立，假阳性极高或无法推断
    HIGH_IMPACT = "HIGH_IMPACT"  # 🟡 高风险：严重扭曲效应量或显著性，必须修正方可投稿
    ADVISORY = "ADVISORY"        # 🔵 建议：方法学规范与鲁棒性提升建议
    PASS = "PASS"                # 🟢 符合规范


class CheckStatus(str, Enum):
    """Explicit per-check outcome. Absence of a finding is not a pass."""
    ASSESSED = "ASSESSED"                    # 已检查，未发现问题
    ISSUE_FOUND = "ISSUE_FOUND"              # 已检查，发现问题
    MISSING_EVIDENCE = "MISSING_EVIDENCE"    # 缺少证据，未评估
    PARSE_FAILED = "PARSE_FAILED"            # 解析失败，显式报告


CHECK_STATUS_ZH = {
    CheckStatus.ASSESSED: "已检查",
    CheckStatus.ISSUE_FOUND: "发现问题",
    CheckStatus.MISSING_EVIDENCE: "缺少证据",
    CheckStatus.PARSE_FAILED: "解析失败",
}

CELL_LEVEL_DE_METHODS = {
    "t-test",
    "t-test_overestim_var",
    "wilcoxon",
    "logreg",
    "t_test",
}

DONOR_LEVEL_TABLE_MARKERS = {
    "basemean",
    "lfcse",
    "logcpm",
    "lr",
}


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
            "evidence_data": _portable_diagnostics(dict(self.evidence_data)),
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
class CheckRecord:
    """One audit check with an explicit assessed / issue / missing-evidence state."""
    check_id: str
    title: str
    status: CheckStatus
    summary: str
    required_for_pass: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "title": self.title,
            "status": self.status.value,
            "status_zh": CHECK_STATUS_ZH[self.status],
            "summary": self.summary,
            "required_for_pass": self.required_for_pass,
        }


@dataclass
class ExecutionRecord:
    """Facts that may be stated in the past tense, taken only from supplied artifacts."""
    source: str = "none"
    method: Optional[str] = None
    fdr_method: Optional[str] = None
    aggregation: Optional[str] = None
    cell_level_condition_test: bool = False
    facts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimScopeBoundary:
    """Explicit scientific claim boundaries and recommended manuscript phrasing."""
    allowed_scope: str
    prohibited_scope: str
    recommended_methods_text: str
    recommended_results_text: str
    overall_maturity: str = "NOT_ASSESSED"
    executed_methods_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DEAuditResult:
    """Bounded artifact audit; a passing status never grants scientific authority."""
    overall_status: str  # BLOCKER_DETECTED / NEEDS_REVISION / NEEDS_DATA / NOT_ASSESSED / ROBUST_PASS
    findings: List[DEFinding] = field(default_factory=list)
    checks: List[CheckRecord] = field(default_factory=list)
    execution_record: Optional[ExecutionRecord] = None
    claim_boundary: Optional[ClaimScopeBoundary] = None
    pi_decisions: List[PIDecisionItem] = field(default_factory=list)
    cohort_summary: Dict[str, Any] = field(default_factory=dict)
    metadata_columns_used: Dict[str, str] = field(default_factory=dict)
    claim_conditions: Optional[Dict[str, Any]] = None
    alternative_analysis: Optional[Dict[str, Any]] = None
    selection_history: Optional[Dict[str, Any]] = None

    @property
    def evidence_contract(self) -> Dict[str, Any]:
        from bionexus.evidence_contract import evidence_contract
        observations = sorted({c.check_id for c in self.checks if c.status in {CheckStatus.ASSESSED, CheckStatus.ISSUE_FOUND}})
        return evidence_contract("ARTIFACT_REVIEW", positive=self.passed and bool(observations),
            scope="Only the supplied artifacts and listed checks; donor identities, real execution and biological interpretation remain unverified.",
            observations=observations, input_integrity="CHECKED" if observations else "UNKNOWN",
            support="CANDIDATE_CORE")

    @property
    def passed(self) -> bool:
        return self.overall_status == "ROBUST_PASS"

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
            "evidence_contract": self.evidence_contract,
            "passed": self.passed,
            "scientific_authorization": "NONE",
            "producer_authentication": "NOT_ESTABLISHED",
            "analysis_execution_verification": "NOT_PERFORMED",
            "summary_counts": {
                "blocker": self.blocker_count,
                "high_impact": self.high_impact_count,
                "advisory": self.advisory_count,
            },
            "cohort_summary": self.cohort_summary,
            "metadata_columns_used": self.metadata_columns_used,
            **({"claim_conditions": self.claim_conditions} if self.claim_conditions is not None else {}),
            **({"alternative_analysis": self.alternative_analysis} if self.alternative_analysis is not None else {}),
            **({"selection_history": self.selection_history} if self.selection_history is not None else {}),
            "checks": [c.to_dict() for c in self.checks],
            "execution_record": self.execution_record.to_dict() if self.execution_record else None,
            "findings": [f.to_dict() for f in self.findings],
            "claim_boundary": self.claim_boundary.to_dict() if self.claim_boundary else None,
            "pi_decisions": [d.to_dict() for d in self.pi_decisions],
        }

    def summary_text(self, use_color: bool = True) -> str:
        """Render a clean, human-readable terminal output."""
        from bionexus.de.renderer import render_summary_text
        return render_summary_text(self, use_color=use_color)

    def to_markdown(self) -> str:
        """Render a publication-ready Markdown report."""
        from bionexus.de.renderer import render_markdown
        return render_markdown(self)
