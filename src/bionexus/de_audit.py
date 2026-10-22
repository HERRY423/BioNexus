"""
BioNexus Multi-Donor Single-Cell Differential Expression Evidence Audit Engine.

Compatibility Facade:
Implementation has been modularized into `bionexus.de`:
- `bionexus.de.models`: Domain dataclasses, enums, schemas, and results
- `bionexus.de.parsers`: File loaders, uns extractors, and column heuristics
- `bionexus.de.rules`: Modular audit rules (metadata, matrix, table, code)
- `bionexus.de.binding`: Execution record verification and claim-fact concordance
- `bionexus.de.policy`: Claim boundary determination and status calculation
- `bionexus.de.renderer`: Terminal summary and Markdown report rendering
- `bionexus.de.engine`: Engine orchestrator and top-level execution interface

All public symbols and module attributes are re-exported here for 100% backward compatibility.
"""

from bionexus.de import (
    BATCH_KEYWORDS,
    CELL_LEVEL_DE_METHODS,
    CELLTYPE_KEYWORDS,
    CHECK_STATUS_ZH,
    CONDITION_KEYWORDS,
    DE_EXECUTION_RECEIPT_COMPATIBILITY_SCHEMA,
    DE_SUCCESS_FIT_STATUSES,
    DONOR_KEYWORDS,
    DONOR_LEVEL_TABLE_MARKERS,
    CheckRecord,
    CheckStatus,
    ClaimScopeBoundary,
    DEAuditEngine,
    DEAuditResult,
    DEFinding,
    ExecutionRecord,
    FindingCategory,
    FindingSeverity,
    PIDecisionItem,
    _audit_claim_vs_table_facts,
    _audit_code,
    _audit_de_table,
    _audit_expression_matrix,
    _audit_metadata,
    _collect_execution_record,
    _compute_overall_status,
    _determine_claim_boundary,
    _execution_json_object,
    _extract_de_from_anndata_uns,
    _load_anndata,
    _load_dataframe,
    _match_column,
    _record_metadata_checks,
    _set_check_status,
    _verify_execution_binding,
    audit_de,
    audit_differential_expression,
    render_markdown,
    render_summary_text,
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
