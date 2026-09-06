"""
BioNexus Static Scientific Analysis Audit (BNS-013, firewall entry point 2).

    bionexus audit analysis.ipynb

You keep using Scanpy, Seurat, Bioconductor, Claude, Codex. BioNexus audits
whether the scientific analysis they produced stands up.

This is a **deterministic static-analysis rule engine** over notebooks
(.ipynb) and scripts (.py / .R / .Rmd / .qmd). It screens the canonical
scientific failure patterns of agentic computational biology:

    pseudoreplication              raw/log matrix confusion
    missing FDR                    batch/condition confounding
    inappropriate statistical unit annotation without evidence
    circular marker selection      missing negative controls
    spatial coordinate substitution parameter instability
    overclaimed causality          backend substitution
    unexecuted code claims

Every finding cites its rule id, taxonomy failure id (BN-Fxxx), the evidence
line, and a remedy. Honest scope: static rules have false negatives by
construction — **the absence of findings is NOT proof of validity** (that
disclaimer is normative, BNS-FW-011).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from bionexus.claim_checker import audit_prohibited_claims

CODE_SUFFIXES = {".py", ".r", ".R", ".Rmd", ".qmd", ".jl", ".txt"}
_NOTEBOOK_SUFFIX = ".ipynb"

DISCLAIMER = (
    "Static-analysis heuristics: findings are evidence of scientific flaws, but absence of "
    "findings is NOT proof of validity."
)

# Backends whose claimed use must be visible in code (BN-F010).
_BACKEND_MARKERS = {
    "scanpy": re.compile(r"\bscanpy\b|\bsc\.", re.I),
    "pydeseq2": re.compile(r"\bpydeseq2\b|DESeqDataSet", re.I),
    "deseq2": re.compile(r"\bdeseq2\b|DESeq\(", re.I),
    "squidpy": re.compile(r"\bsquidpy\b|\bsq\.", re.I),
    "scvi": re.compile(r"\bscvi\b|SCVI\(|scANVI|totalVI", re.I),
    "lifelines": re.compile(r"\blifelines\b|KaplanMeierFitter|CoxPHFitter", re.I),
}
_BACKEND_CLAIMED = re.compile(
    r"\b(scanpy|pydeseq2|deseq2|squidpy|scvi|lifelines)\b[^.\n]{0,40}\b(?:was|were|has been)\s+run\b",
    re.IGNORECASE,
)
_WE_RAN = re.compile(
    r"\bwe\s+(?:ran|performed|executed|applied|used)\s+([a-zA-Z0-9\-\+ ]{3,60})", re.IGNORECASE
)
_RUNNABLE_METHODS = (
    "leiden", "umap", "pca", "deseq", "pseudobulk", "moran", "survival", "kaplan",
    "clustering", "batch correction", "integration", "differential expression",
    "spatial", "annotation", "imputation", "harmony",
)

_DE_CALL = re.compile(r"rank_genes_groups|DESeqDataSet|pydeseq2|DESeq\(|edgeR|glm\s*\(", re.IGNORECASE)
_CONDITION_GROUPBY = re.compile(
    r"groupby\s*=\s*['\"](?:condition|treatment|group|genotype|stim|disease)", re.IGNORECASE
)
_PSEUDOBULK_MARKER = re.compile(
    r"pseudobulk|pb_|aggregate|groupby\s*=\s*['\"](?:donor|sample_id|donor_id|sample)['\"]", re.IGNORECASE
)
_DONOR_COLUMN_REF = re.compile(r"['\"](?:donor_id|donor|sample_id|sample|patient_id)['\"]", re.IGNORECASE)
_LOG_NORM = re.compile(r"normalize_total|log1p|sc\.pp\.scale|CPM|counts_per_million", re.IGNORECASE)
_COUNT_MODEL = re.compile(r"DESeqDataSet|pydeseq2|deseq2|NegativeBinomial|scvi\.model|SCVI\(", re.IGNORECASE)
_RAW_LAYER_REF = re.compile(r"layer\s*=\s*['\"]counts['\"]|\.raw\.X|adata\.raw", re.IGNORECASE)
_STAT_TEST = re.compile(
    r"ttest_ind|ttest_1samp|mannwhitneyu|wilcoxon|rank_genes_groups|kruskal|anova|pairwise_|\.test\(",
    re.IGNORECASE,
)
_FDR_REF = re.compile(r"multipletests|fdr|benjamini|\bbh\b|qvals|p_adj|padj|p\.adjusted|corr_method", re.IGNORECASE)
_BATCH_REF = re.compile(r"\bbatch\b|batch_key", re.IGNORECASE)
_LABEL_MAP_DEF = re.compile(r"(?:cell_type|annotation|label)[_a-zA-Z]*\s*(?::|=)\s*\{", re.IGNORECASE)
_CELLTYPE_LITERAL = re.compile(
    r"\b(?:T cells|B cells|macrophages?|monocytes?|NK cells|dendritic cells?|fibroblasts?|endothelial cells?|epithelial cells?|cytotoxic T|helper T|plasma cells?)\b",
    re.IGNORECASE,
)
_REFERENCE_TOOL = re.compile(
    r"celltypist|azimuth|singler|scmap|sc\.tl\.score_genes|label_transfer|reference mapping|query_reference", re.IGNORECASE
)
_MARKER_VAR_DEF = re.compile(r"(markers?|marker_genes|gene_list|signature)\s*=\s*[\[\(]", re.IGNORECASE)
_SCORE_USE = re.compile(r"score_genes\w*\(", re.IGNORECASE)
_VALIDATE_USE = re.compile(r"rank_genes_groups|enrichr|gseapy|enrich\w*\(", re.IGNORECASE)
_NEGATIVE_MARKER = re.compile(r"negative|exclude|ding", re.IGNORECASE)
_SPATIAL_GRAPH = re.compile(r"spatial_neighbors|sq\.gr\.|n_neighs\s*=", re.IGNORECASE)
_EMBEDDING_COORD = re.compile(r"X_umap|X_pca|X_tsne|obsm\[[\"']X_", re.IGNORECASE)
_SPATIAL_COORD = re.compile(r"obsm\[[\"']spatial[\"']|spatial coordinates", re.IGNORECASE)
_SPATIAL_SUBSTITUTE_ASSIGN = re.compile(
    r"obsm\[[\"']spatial[\"']\]\s*(?:=|<-)\s*[^#\n]*obsm\[[\"']X_(?:umap|pca|tsne)[\"']\]", re.IGNORECASE
)
_RESOLUTION_PARAM = re.compile(r"resolution\s*=\s*([0-9.]+)", re.IGNORECASE)
_SWEEP_LOOP = re.compile(r"for\s+\w+\s+in\s+[^:\n]*(?:resolution|n_neighs|k\s*=)|resolutions\s*=|sweep", re.IGNORECASE)


@dataclass
class CodeCell:
    """One code unit (notebook cell or whole-script segment)."""

    index: int
    source: str
    execution_count: Optional[int] = None

    @property
    def lines(self) -> List[str]:
        return self.source.splitlines()


@dataclass
class AnalysisDocument:
    """A parsed notebook or script, split into code cells and prose."""

    path: str
    language: str  # "python" | "r" | "unknown"
    code_cells: List[CodeCell] = field(default_factory=list)
    markdown_blocks: List[str] = field(default_factory=list)

    @property
    def code_text(self) -> str:
        return "\n\n".join(c.source for c in self.code_cells)

    @property
    def markdown_text(self) -> str:
        return "\n\n".join(self.markdown_blocks)


@dataclass
class AuditFinding:
    """One detected scientific flaw in the analysis code or prose."""

    rule_id: str
    rule_name: str
    failure_id: str
    severity: str  # "FATAL" | "ADVISORY"
    location: str
    evidence: str
    message: str
    remedy: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            k: getattr(self, k)
            for k in ("rule_id", "rule_name", "failure_id", "severity", "location", "evidence", "message", "remedy")
        }


@dataclass
class AnalysisAuditResult:
    """Aggregate result of the static scientific audit."""

    path: str
    findings: List[AuditFinding] = field(default_factory=list)
    disclaimer: str = DISCLAIMER

    @property
    def fatal_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "FATAL")

    @property
    def advisory_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "ADVISORY")

    @property
    def passed(self) -> bool:
        return self.fatal_count == 0

    @property
    def failure_mode_ids(self) -> List[str]:
        return sorted({f.failure_id for f in self.findings})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "passed": self.passed,
            "fatal_count": self.fatal_count,
            "advisory_count": self.advisory_count,
            "failure_mode_ids": self.failure_mode_ids,
            "disclaimer": self.disclaimer,
            "findings": [f.to_dict() for f in self.findings],
        }


def load_analysis_document(path: str | Path) -> AnalysisDocument:
    """Parse a notebook (.ipynb) or script file into code cells + prose."""
    p = Path(path)
    if p.suffix.lower() == _NOTEBOOK_SUFFIX:
        nb = json.loads(p.read_text(encoding="utf-8"))
        cells: List[CodeCell] = []
        markdown: List[str] = []
        idx = 0
        for cell in nb.get("cells", []):
            src = cell.get("source", "")
            if isinstance(src, list):
                src = "".join(src)
            if cell.get("cell_type") == "code":
                cells.append(CodeCell(index=idx, source=src, execution_count=cell.get("execution_count")))
                idx += 1
            elif cell.get("cell_type") == "markdown":
                markdown.append(src)
        lang = "python"
        if any(re.search(r"\blibrary\(|%R|BiocManager", c.source) for c in cells):
            lang = "r"
        return AnalysisDocument(path=str(p), language=lang, code_cells=cells, markdown_blocks=markdown)

    text = p.read_text(encoding="utf-8", errors="replace")
    code_lines: List[str] = []
    prose_lines: List[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            prose_lines.append(stripped.lstrip("#/ ").strip())
        else:
            code_lines.append(line)
    language = "r" if p.suffix.lower() in (".r", ".rmd") else "python"
    return AnalysisDocument(
        path=str(p),
        language=language,
        code_cells=[CodeCell(index=0, source="\n".join(code_lines))],
        markdown_blocks=["\n".join(prose_lines)] if prose_lines else [],
    )


def _finding(
    rule_id: str,
    rule_name: str,
    failure_id: str,
    severity: str,
    location: str,
    evidence: str,
    message: str,
    remedy: str,
) -> AuditFinding:
    return AuditFinding(
        rule_id=rule_id,
        rule_name=rule_name,
        failure_id=failure_id,
        severity=severity,
        location=location,
        evidence=evidence.strip()[:160],
        message=message,
        remedy=remedy,
    )


def _strip_code_comments(source: str) -> str:
    """
    Strip comments from source code so text annotations and TODO comments
    cannot spoof or suppress static audit findings.
    """
    cleaned_lines = []
    for line in source.splitlines():
        in_single = False
        in_double = False
        out_chars = []
        for i, ch in enumerate(line):
            if ch == "'" and not in_double:
                if i == 0 or line[i - 1] != "\\":
                    in_single = not in_single
            elif ch == '"' and not in_single:
                if i == 0 or line[i - 1] != "\\":
                    in_double = not in_double
            elif ch == "#" and not in_single and not in_double:
                break
            out_chars.append(ch)
        cleaned_lines.append("".join(out_chars))
    return "\n".join(cleaned_lines)


def audit_analysis(path: str | Path) -> AnalysisAuditResult:
    """
    Run the full static scientific audit over a notebook or script.

    Rule families BFA-001..BFA-013 map one-to-one onto the canonical trap
    classes (see module docstring); each finding carries its taxonomy id.
    """
    doc = load_analysis_document(path)
    findings: List[AuditFinding] = []
    code = doc.code_text
    executable_code = _strip_code_comments(code)
    cells = doc.code_cells
    prose = doc.markdown_text

    def cell_of(pattern: re.Pattern) -> Optional[CodeCell]:
        for c in cells:
            if pattern.search(c.source):
                return c
        return None

    def line_of(cell: Optional[CodeCell], pattern: re.Pattern) -> str:
        if cell is None:
            return ""
        for ln in cell.lines:
            if pattern.search(ln):
                return ln.strip()
        return cell.lines[0].strip() if cell.lines else ""

    # BFA-001 cell-level pseudoreplication (BN-F002)
    de_cell = cell_of(_DE_CALL)
    if de_cell is not None:
        cond_groupby = _CONDITION_GROUPBY.search(de_cell.source)
        if cond_groupby and not _PSEUDOBULK_MARKER.search(executable_code):
            findings.append(
                _finding(
                    "BFA-001", "cell-level pseudoreplication", "BN-F002", "FATAL",
                    f"cell {de_cell.index}", line_of(de_cell, _CONDITION_GROUPBY),
                    "Condition-level differential testing is invoked at cell level with no pseudobulk "
                    "aggregation or donor-level grouping: thousands of cells from one sample are being "
                    "treated as independent biological replicates.",
                    "Aggregate raw counts per (donor, cell_type, condition) into pseudobulk, then test "
                    "donors (n >= 2 per condition) with a NB GLM; or relabel as exploratory within-sample ranking.",
                )
            )
        # BFA-005 inappropriate statistical unit (donor column exists but unused)
        elif _DONOR_COLUMN_REF.search(code) and cond_groupby and not _PSEUDOBULK_MARKER.search(executable_code):
            findings.append(
                _finding(
                    "BFA-005", "inappropriate statistical unit", "BN-F002", "FATAL",
                    f"cell {de_cell.index}", line_of(de_cell, _CONDITION_GROUPBY),
                    "A donor/sample column exists in the metadata but the statistical unit is the cell; "
                    "variance is attributed to the wrong level of the design.",
                    "Set the biological replicate (donor/sample) as the statistical unit via pseudobulk "
                    "aggregation or a mixed model with donor as the random effect.",
                )
            )

    # BFA-002 raw/log matrix confusion (BN-F001)
    if _COUNT_MODEL.search(code) and _LOG_NORM.search(code) and not _RAW_LAYER_REF.search(executable_code):
        cell = cell_of(_COUNT_MODEL) or cells[0]
        findings.append(
            _finding(
                "BFA-002", "raw/log matrix confusion", "BN-F001", "FATAL",
                f"cell {cell.index}", line_of(cell, _COUNT_MODEL),
                "A count-model (NB GLM / scVI) is fitted on data that the same document normalizes or "
                "log-transforms, without routing raw counts via layer='counts' or adata.raw.",
                "Keep raw integer counts in a dedicated layer and pass those to the count model; "
                "normalize only for visualization and scale-insensitive steps.",
            )
        )

    # BFA-003 missing multiple-testing correction (BN-F005)
    if _STAT_TEST.search(code) and not _FDR_REF.search(code):
        cell = cell_of(_STAT_TEST)
        if cell is not None:
            findings.append(
                _finding(
                    "BFA-003", "missing FDR correction", "BN-F005", "ADVISORY",
                    f"cell {cell.index}", line_of(cell, _STAT_TEST),
                    "Genome-scale test statistics are reported with no false-discovery control anywhere "
                    "in the analysis; uncorrected p-values across thousands of genes will be read as findings.",
                    "Report BH/FDR-corrected values alongside every finding; until then cap conclusions "
                    "at PRELIMINARY (exploratory ranking language only).",
                )
            )

    # BFA-004 batch/condition confounding left unadjusted (BN-F006)
    if _BATCH_REF.search(code) and de_cell is not None:
        if not _BATCH_REF.search(de_cell.source):
            findings.append(
                _finding(
                    "BFA-004", "batch/condition confounding unadjusted", "BN-F006", "ADVISORY",
                    f"cell {de_cell.index}", line_of(de_cell, _DE_CALL),
                    "A batch covariate is present in the data but is not part of the condition-level test; "
                    "batch structure can fully or partly explain the 'condition' effect.",
                    "Include batch in the design (pseudobulk design formula) or integrate first, then test "
                    "condition; report the adjusted and unadjusted results side by side.",
                )
            )

    # BFA-006 annotation without evidence (BN-F003)
    if _LABEL_MAP_DEF.search(code) and _CELLTYPE_LITERAL.search(code) and not _REFERENCE_TOOL.search(executable_code):
        cell = cell_of(_LABEL_MAP_DEF) or cells[0]
        findings.append(
            _finding(
                "BFA-006", "annotation without evidence", "BN-F003", "FATAL",
                f"cell {cell.index}", line_of(cell, _LABEL_MAP_DEF),
                "Cluster-to-cell-type labels are hand-assigned in code with no reference mapping, marker-panel "
                "scoring, or transfer-learning evidence anywhere in the analysis.",
                "Attach a reference atlas (CellTypist/Azimuth/SingleR) or a curated panel with positive AND "
                "negative markers; until then keep labels numeric/putative.",
            )
        )

    # BFA-007 circular marker validation (BN-F003)
    marker_cells = [c for c in cells if _MARKER_VAR_DEF.search(c.source)]
    if marker_cells:
        var_names = set()
        for c in marker_cells:
            for m in _MARKER_VAR_DEF.finditer(c.source):
                var_names.add(m.group(1))
        scoring_cells = [c for c in cells if _SCORE_USE.search(c.source)]
        validating_cells = [c for c in cells if _VALIDATE_USE.search(c.source)]
        if scoring_cells and validating_cells:
            shared = [v for v in var_names if any(re.search(rf"\b{re.escape(v)}\b", c.source) for c in validating_cells)]
            if shared:
                findings.append(
                    _finding(
                        "BFA-007", "circular marker validation", "BN-F003", "FATAL",
                        f"cells {[c.index for c in marker_cells + validating_cells]}",
                        f"marker variable(s): {', '.join(sorted(shared))}",
                        "The same marker list is used to define/annotate populations and then to validate them: "
                        "the validation cannot fail by construction.",
                        "Validate with markers excluded from the defining set, negative markers, or an "
                        "independent reference; report the validation as circular otherwise.",
                    )
                )

    # BFA-008 missing negative controls (BN-F011)
    if (_SCORE_USE.search(code) or _LABEL_MAP_DEF.search(code)) and not _NEGATIVE_MARKER.search(code):
        cell = cell_of(_SCORE_USE) or cell_of(_LABEL_MAP_DEF) or cells[0]
        findings.append(
            _finding(
                "BFA-008", "missing negative controls", "BN-F011", "ADVISORY",
                f"cell {cell.index}", line_of(cell, _SCORE_USE or _LABEL_MAP_DEF),
                "Population annotation/validation uses only positive evidence; no negative markers or "
                "control genes are evaluated anywhere.",
                "Score lineage-exclusive negative markers (and control genes) alongside positives; "
                "labels passing only positive markers stay TENTATIVE.",
            )
        )

    # BFA-009 spatial coordinate substitution (BN-F009)
    substitute_cell = cell_of(_SPATIAL_SUBSTITUTE_ASSIGN)
    if substitute_cell is not None:
        findings.append(
            _finding(
                "BFA-009", "spatial coordinate substitution", "BN-F009", "FATAL",
                f"cell {substitute_cell.index}", line_of(substitute_cell, _SPATIAL_SUBSTITUTE_ASSIGN),
                "A UMAP/PCA embedding is assigned into obsm['spatial']: every downstream spatial "
                "statistic is an artifact of the embedding, not of tissue geometry.",
                "Use physical coordinates in obsm['spatial']; if only an embedding exists, record the "
                "spatial justification and cap conclusions at FRAGILE.",
            )
        )
    else:
        for c in cells:
            if _SPATIAL_GRAPH.search(c.source) and _EMBEDDING_COORD.search(c.source) and not _SPATIAL_COORD.search(c.source):
                findings.append(
                    _finding(
                        "BFA-009", "spatial coordinate substitution", "BN-F009", "FATAL",
                        f"cell {c.index}", line_of(c, _EMBEDDING_COORD),
                        "Spatial neighborhood/statistics are computed over a UMAP/PCA embedding instead of "
                        "physical tissue coordinates: every spatial result is an artifact of the embedding.",
                        "Use obsm['spatial'] physical coordinates; if only an embedding exists, record the "
                        "spatial justification and cap conclusions at FRAGILE.",
                    )
                )
                break

    # BFA-010 parameter instability (BN-F007)
    resolutions = _RESOLUTION_PARAM.findall(code)
    if resolutions and not _SWEEP_LOOP.search(code):
        cell = cell_of(_RESOLUTION_PARAM)
        findings.append(
            _finding(
                "BFA-010", "parameter instability", "BN-F007", "ADVISORY",
                f"cell {cell.index if cell else 0}", line_of(cell, _RESOLUTION_PARAM),
                f"Results depend on a single parameter choice (resolution={resolutions[0]}) with no sweep: "
                "reported populations may not survive a defensible perturbation.",
                "Sweep the sensitive parameter (resolution / n_neighs / k) and report stability "
                "(e.g. ARI across the sweep); unstable findings stay FRAGILE.",
            )
        )

    # BFA-011 overclaimed causality / prohibited claims in prose (BN-F011)
    if prose:
        claim_audit = audit_prohibited_claims(prose)
        for v in claim_audit.violations:
            findings.append(
                _finding(
                    "BFA-011", "overclaimed causality", "BN-F011", "FATAL",
                    "prose", v.matched_text,
                    f"Prohibited scientific claim in narrative text: {v.rule_description}",
                    v.remedy,
                )
            )

    # BFA-012 backend substitution (BN-F010)
    for m in _BACKEND_CLAIMED.finditer(prose):
        backend = m.group(1).lower()
        marker = _BACKEND_MARKERS.get(backend)
        if marker is not None and not marker.search(code):
            findings.append(
                _finding(
                    "BFA-012", "backend substitution", "BN-F010", "FATAL",
                    "prose", m.group(0),
                    f"Prose claims '{backend}' was run, but no {backend} code exists in the document: "
                    "heuristic or substituted output is being presented under a gold-standard name.",
                    "Either run the canonical backend or describe the actual method used, labeled Grade C, "
                    "with the canonical backend named as unavailable.",
                )
            )

    # BFA-013 unexecuted code claims (BN-F012)
    for m in _WE_RAN.finditer(prose):
        claimed = m.group(1).lower()
        if any(k in claimed for k in _RUNNABLE_METHODS):
            key = claimed.split()[0].split("-")[0]
            if key and key not in code.lower():
                findings.append(
                    _finding(
                        "BFA-013", "unexecuted code claim", "BN-F012", "FATAL",
                        "prose", m.group(0),
                        f"Prose claims an executed step ('{m.group(1).strip()}') that has no corresponding "
                        "code anywhere in the document.",
                        "Add the code for the claimed step or remove the claim; narrative methods must "
                        "match executed cells.",
                    )
                )
    unexecuted = [c for c in cells if c.execution_count is None and c.source.strip()]
    if unexecuted and any(k in prose.lower() for k in ("result", "finding", "significant", "we observed")):
        findings.append(
            _finding(
                "BFA-013", "unexecuted code claim", "BN-F012", "ADVISORY",
                f"cells {[c.index for c in unexecuted]}", f"{len(unexecuted)} code cell(s) with execution_count = null",
                "Result claims coexist with unexecuted code cells: the narrative may describe outputs "
                "this notebook never produced in this version.",
                "Re-execute the notebook top-to-bottom before citing its results (clear evidence of "
                "staleness otherwise).",
            )
        )

    return AnalysisAuditResult(path=str(path), findings=findings)


def render_analysis_audit(result: AnalysisAuditResult) -> str:
    """Render the audit block in the BNS-013 output contract (ASCII markers)."""
    lines: List[str] = []
    lines.append(f"=== BioNexus Analysis Audit: {result.path} ===")
    lines.append("")
    verdict = "PASSED (no FATAL findings)" if result.passed else f"FAILED: {result.fatal_count} FATAL finding(s)"
    lines.append(f"VERDICT: {verdict} | ADVISORY: {result.advisory_count} | failure modes: {', '.join(result.failure_mode_ids) or 'none'}")
    lines.append("")
    if result.findings:
        for f in result.findings:
            sev = "FATAL" if f.severity == "FATAL" else "ADVISORY"
            lines.append(f"[{sev}] {f.rule_id} {f.rule_name} ({f.failure_id}) @ {f.location}")
            lines.append(f"        evidence: {f.evidence}")
            lines.append(f"        {f.message}")
            lines.append(f"        remedy:   {f.remedy}")
            lines.append("")
    else:
        lines.append("(no findings matched the deterministic rule set)")
        lines.append("")
    lines.append(f"DISCLAIMER: {result.disclaimer}")
    return "\n".join(lines)
