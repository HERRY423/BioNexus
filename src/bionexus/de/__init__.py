"""
BioNexus Multi-Donor Single-Cell Differential Expression Evidence Audit Package.

Decoupled modular architecture separating rules, parsers, execution binding,
governing policy, rendering, and engine orchestration.
"""

from bionexus.de.binding import (
    _audit_claim_vs_table_facts,
    _collect_execution_record,
    _execution_json_object,
    _verify_execution_binding,
)
from bionexus.de.engine import (
    DEAuditEngine,
    audit_de,
    audit_differential_expression,
)
from bionexus.de.models import (
    CELL_LEVEL_DE_METHODS,
    CHECK_STATUS_ZH,
    DE_EXECUTION_RECEIPT_COMPATIBILITY_SCHEMA,
    DE_SUCCESS_FIT_STATUSES,
    DONOR_LEVEL_TABLE_MARKERS,
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
from bionexus.de.renderer import (
    render_markdown,
    render_summary_text,
)
from bionexus.de.rules import (
    _audit_code,
    _audit_de_table,
    _audit_expression_matrix,
    _audit_metadata,
    _record_metadata_checks,
)

__all__ = [
    "BATCH_KEYWORDS",
    "CELLTYPE_KEYWORDS",
    "CELL_LEVEL_DE_METHODS",
    "CHECK_STATUS_ZH",
    "CONDITION_KEYWORDS",
    "CheckRecord",
    "CheckStatus",
    "ClaimScopeBoundary",
    "DEAuditEngine",
    "DEAuditResult",
    "DEFinding",
    "DE_EXECUTION_RECEIPT_COMPATIBILITY_SCHEMA",
    "DE_SUCCESS_FIT_STATUSES",
    "DONOR_KEYWORDS",
    "DONOR_LEVEL_TABLE_MARKERS",
    "ExecutionRecord",
    "FindingCategory",
    "FindingSeverity",
    "PIDecisionItem",
    "_audit_code",
    "_audit_claim_vs_table_facts",
    "_audit_de_table",
    "_audit_expression_matrix",
    "_audit_metadata",
    "_collect_execution_record",
    "_compute_overall_status",
    "_determine_claim_boundary",
    "_execution_json_object",
    "_extract_de_from_anndata_uns",
    "_load_anndata",
    "_load_dataframe",
    "_match_column",
    "_record_metadata_checks",
    "_set_check_status",
    "_verify_execution_binding",
    "audit_de",
    "audit_differential_expression",
    "render_markdown",
    "render_summary_text",
]
