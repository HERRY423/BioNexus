"""
BioFailureBench: the Scientific Trap Corpus (BNS-014).

BioFailureBench does not test "can the AI answer biology questions".
It tests: **does the AI realize an analysis should not have been run —
or that a conclusion does not stand?**

Each trap is a complete record with eight required fields (BNS-BF-002):

    data                -> data_metadata (+ data context in prompt)
    intended analysis   -> prompt
    hidden flaw         -> failure_mode (BN-Fxxx taxonomy id)
    expected detection  -> expected_status / expected_violations / expected_maturity
    allowed computation -> allowed_computation
    forbidden claim     -> forbidden_claim
    remediation         -> required_remedies
    reference           -> reference

The corpus is host-agnostic: Claude, Codex, Cursor, Biomni, and future agents
run the identical suite through `bionexus eval --suite biofailurebench`.
This module validates corpus integrity (schema, taxonomy linkage, coverage)
so the corpus cannot silently rot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

CORPUS_FIELDS = (
    "id",
    "prompt",
    "expected_status",
    "data_metadata",
    "required_remedies",
    "allowed_computation",
    "forbidden_claim",
    "failure_mode",
    "reference",
    "description",
)

FRONTIER_PREFIX = "FRONTIER TRAP"
GATING_PREFIX = "TRAP"
CONTROL_PREFIX = "CONTROL"


def corpus_path(datasets_dir: Optional[Path] = None) -> Path:
    d = datasets_dir or (Path(__file__).resolve().parent / "datasets")
    return d / "biofailurebench.yaml"


@dataclass
class CorpusIssue:
    case_id: str
    field: str
    problem: str


@dataclass
class CorpusReport:
    total_cases: int = 0
    gating_cases: int = 0
    frontier_cases: int = 0
    valid: bool = False
    issues: List[CorpusIssue] = field(default_factory=list)
    failure_mode_coverage: Dict[str, int] = field(default_factory=dict)
    capabilities_covered: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_cases": self.total_cases,
            "gating_cases": self.gating_cases,
            "frontier_cases": self.frontier_cases,
            "valid": self.valid,
            "issues": [
                {"case_id": i.case_id, "field": i.field, "problem": i.problem} for i in self.issues
            ],
            "failure_mode_coverage": dict(self.failure_mode_coverage),
            "capabilities_covered": sorted(set(self.capabilities_covered)),
        }


def load_corpus_records(datasets_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load the raw BioFailureBench trap records."""
    p = corpus_path(datasets_dir)
    if not p.is_file():
        raise FileNotFoundError(f"BioFailureBench corpus not found: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"BioFailureBench corpus must be a YAML list of trap records: {p}")
    return data


def validate_corpus(datasets_dir: Optional[Path] = None) -> CorpusReport:
    """
    Validate the corpus (BNS-BF-002..005): every trap carries all eight
    required fields, failure_mode links resolve into the BN-Fxxx taxonomy,
    gating/frontier separation is explicit, and coverage spans all modes.
    """
    from bionexus.failures import FAILURE_TAXONOMY
    from evals.runner import load_eval_cases

    records = load_corpus_records(datasets_dir)
    report = CorpusReport()
    issues: List[CorpusIssue] = []
    coverage: Dict[str, int] = {}
    capabilities: List[str] = []

    resolved_ids = {c.id for c in load_eval_cases()}

    for rec in records:
        cid = rec.get("id", "<missing-id>")
        report.total_cases += 1

        is_frontier = bool(rec.get("known_limitation", False))
        if is_frontier:
            report.frontier_cases += 1
        else:
            report.gating_cases += 1

        for f in CORPUS_FIELDS:
            if f not in rec or rec.get(f) in (None, "", [], {}):
                if f == "required_remedies" and rec.get(f) == []:
                    continue  # positive controls legitimately carry no remedy
                issues.append(CorpusIssue(cid, f, "required corpus field missing or empty"))

        description = str(rec.get("description", ""))
        is_control = rec.get("failure_mode") == "NONE"
        if not is_frontier and not (description.startswith(GATING_PREFIX) or (is_control and description.startswith(CONTROL_PREFIX))):
            issues.append(CorpusIssue(cid, "description", f"gating traps must describe the hidden flaw with a '{GATING_PREFIX}:' prefix (positive controls use '{CONTROL_PREFIX}:')"))
        if is_frontier and not description.startswith(FRONTIER_PREFIX):
            issues.append(CorpusIssue(cid, "description", f"frontier traps must use the '{FRONTIER_PREFIX}:' prefix"))

        failure_mode = rec.get("failure_mode")
        if failure_mode and failure_mode != "NONE":
            if failure_mode not in FAILURE_TAXONOMY:
                issues.append(CorpusIssue(cid, "failure_mode", f"'{failure_mode}' not in the BN-Fxxx taxonomy"))
            else:
                coverage[failure_mode] = coverage.get(failure_mode, 0) + 1
        elif failure_mode != "NONE":
            issues.append(CorpusIssue(cid, "failure_mode", "hidden flaw must be tagged with a taxonomy id (or explicit NONE for controls)"))

        if cid not in resolved_ids:
            issues.append(CorpusIssue(cid, "id", "case id does not resolve through evals.runner.load_eval_cases"))

        cap = rec.get("expected_capability")
        if cap:
            capabilities.append(cap)

    uncovered = sorted(set(FAILURE_TAXONOMY) - set(coverage))
    if uncovered:
        issues.append(CorpusIssue("<corpus>", "coverage", f"failure modes with no gating trap: {uncovered}"))

    report.issues = issues
    report.valid = not issues
    report.failure_mode_coverage = coverage
    report.capabilities_covered = capabilities
    return report


def validate_single_trap(trap: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a single community-submitted trap against BNS-BF schema invariants."""
    from bionexus.failures import FAILURE_TAXONOMY

    errors: List[str] = []
    cid = trap.get("id", "<missing-id>")

    for f in CORPUS_FIELDS:
        if f not in trap or trap.get(f) in (None, "", [], {}):
            if f == "required_remedies" and trap.get(f) == []:
                continue
            errors.append(f"Field '{f}' is required and cannot be empty.")

    description = str(trap.get("description", ""))
    is_frontier = bool(trap.get("known_limitation", False))
    is_control = trap.get("failure_mode") == "NONE"

    if not is_frontier and not (
        description.startswith(GATING_PREFIX) or (is_control and description.startswith(CONTROL_PREFIX))
    ):
        errors.append(
            f"Gating traps must prefix description with '{GATING_PREFIX}:' (positive controls use '{CONTROL_PREFIX}:')"
        )
    if is_frontier and not description.startswith(FRONTIER_PREFIX):
        errors.append(f"Frontier traps must prefix description with '{FRONTIER_PREFIX}:'")

    failure_mode = trap.get("failure_mode")
    if failure_mode and failure_mode != "NONE":
        if failure_mode not in FAILURE_TAXONOMY:
            errors.append(f"failure_mode '{failure_mode}' does not exist in Failure Taxonomy v1 ({list(FAILURE_TAXONOMY.keys())})")

    status = trap.get("expected_status")
    if status not in ("PERMITTED", "PERMITTED_WITH_LIMITS", "NEEDS_DATA", "ABSTAIN", "DEGRADED_ADVISORY"):
        errors.append(f"Invalid expected_status '{status}'. Must be one of PERMITTED, PERMITTED_WITH_LIMITS, NEEDS_DATA, ABSTAIN, DEGRADED_ADVISORY.")

    return (len(errors) == 0, errors)


def render_corpus_report(report: CorpusReport) -> str:
    lines: List[str] = []
    lines.append("=== BioFailureBench: Scientific Trap Corpus (BNS-014) ===")
    lines.append("")
    lines.append(
        f"Traps: {report.total_cases} total | {report.gating_cases} gating | {report.frontier_cases} frontier (known limitations)"
    )
    verdict = "VALID" if report.valid else "INVALID"
    lines.append(f"Integrity: {verdict}")
    lines.append("")
    lines.append("Failure-mode coverage (BN-Fxxx -> gating trap count):")
    for fid in sorted(report.failure_mode_coverage):
        lines.append(f"  {fid}: {report.failure_mode_coverage[fid]}")
    lines.append("")
    if report.issues:
        lines.append("Issues:")
        for i in report.issues:
            lines.append(f"  [{i.case_id}] {i.field}: {i.problem}")
        lines.append("")
    lines.append("Run the suite on any host:  bionexus eval --suite biofailurebench")
    return "\n".join(lines)

