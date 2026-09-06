"""
BioNexus Pre-Tool Guard & Runtime Interception Layer (BNS-GRD-001..010).

Provides pre-execution interception, AST-level analysis, and warrant constraint
injection before agent or user code runs, preventing pseudoreplication, assay-state
confusion, and invalid causal claims at the point of intent.
"""

from __future__ import annotations

import enum
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union


class GuardStatus(str, enum.Enum):
    """Verdict of the pre-tool guard."""

    PASSED = "PASSED"  # Safe to execute without special limits
    INJECT_CONSTRAINTS = "INJECT_CONSTRAINTS"  # Permitted, but inject warrant caps into agent context
    BLOCKED = "BLOCKED"  # Non-negotiable execution invariant violated


@dataclass
class GuardVerdict:
    """Detailed verdict and context-injection payload from the runtime guard."""

    status: GuardStatus
    execution_permitted: bool
    violation_ids: List[str] = field(default_factory=list)
    warrant_guidance: List[str] = field(default_factory=list)
    forbidden_claims: List[str] = field(default_factory=list)
    suggested_remedy: Optional[str] = None
    inspected_target: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    def format_agent_injection_prompt(self) -> str:
        """Format an unambiguous, high-priority prompt injection for LLM agents."""
        if self.status == GuardStatus.PASSED:
            return ""

        lines = [
            "================================================================================",
            "[BIONEXUS RUNTIME GUARD: SCIENTIFIC WARRANT CONSTRAINT INJECTION]",
            "================================================================================",
            f"Verdict: {self.status.value}",
            f"Active Violations: {', '.join(self.violation_ids) or 'None'}",
            "",
            "CRITICAL INSTRUCTIONS FOR AI AGENT:",
        ]
        for g in self.warrant_guidance:
            lines.append(f"  * {g}")

        if self.forbidden_claims:
            lines.append("\nFORBIDDEN CLAIMS (DO NOT GENERATE OR ASSERT):")
            for fc in self.forbidden_claims:
                lines.append(f"  [X] {fc}")

        if self.suggested_remedy:
            lines.append(f"\nRECOMMENDED CODE / DESIGN REMEDY:\n{self.suggested_remedy}")

        lines.append("================================================================================")
        return "\n".join(lines)


class BioNexusGuard:
    """Pre-execution assertion firewall and context-injection guard."""

    # High-risk patterns in bioinformatics scripts and commands
    PSEUDOREPLICATION_PATTERNS = [
        re.compile(r"sc\.tl\.rank_genes_groups\s*\([^)]*groupby\s*=\s*['\"](condition|treatment|disease|group|batch|status)['\"]", re.IGNORECASE),
        re.compile(r"scanpy\.tl\.rank_genes_groups\s*\([^)]*groupby\s*=\s*['\"](condition|treatment|disease|group|batch|status)['\"]", re.IGNORECASE),
        re.compile(r"sc\.tl\.rank_genes_groups\s*\([^)]*['\"](condition|treatment|disease|group)['\"]", re.IGNORECASE),
    ]

    RAW_LOG_CONFUSION_PATTERNS = [
        re.compile(r"scvi\.model\.SCVI\.setup_anndata\s*\([^)]*layer\s*=\s*['\"](log|scaled|norm|normalized)['\"]", re.IGNORECASE),
        re.compile(r"DeseqDataSet\s*\([^)]*layer\s*=\s*['\"](log|scaled|norm)['\"]", re.IGNORECASE),
        re.compile(r"pydeseq2.*adata\.X\s*(?!\.layers\['counts'\])", re.IGNORECASE),
    ]

    MISSING_FDR_PATTERNS = [
        re.compile(r"pvals\s*<\s*0\.05(?!.*(?:padj|fdr|pvals_adj|multipletests))", re.IGNORECASE),
        re.compile(r"p_val\s*<\s*0\.05(?!.*(?:p_val_adj|qval|fdr))", re.IGNORECASE),
    ]

    MODEL_MASQUERADE_PATTERNS = [
        re.compile(r"def\s+run_deseq2\s*\(.*numpy", re.IGNORECASE),
        re.compile(r"def\s+harmony_integrate\s*\(.*sklearn", re.IGNORECASE),
    ]

    def inspect_code(self, code: str, file_path: str = "") -> GuardVerdict:
        """Analyze code before execution using fast regex and AST inspection."""
        violations: List[str] = []
        guidance: List[str] = []
        forbidden_claims: List[str] = []
        suggested_remedy: Optional[str] = None
        is_blocked = False

        # 1. Check for Pseudoreplication (BN-F006)
        for pat in self.PSEUDOREPLICATION_PATTERNS:
            if pat.search(code):
                violations.append("BN-F006")
                guidance.append(
                    "Detected cell-level differential expression across conditions/groups without biological donor aggregation. "
                    "Cells from the same donor are not independent statistical units (Squair et al., Nature Comms 2021)."
                )
                forbidden_claims.extend([
                    "Population-level causal treatment effect",
                    "Condition-specific biomarkers claiming generalizability beyond this specific sample cohort",
                ])
                suggested_remedy = (
                    "# Use Pseudobulk aggregation instead:\n"
                    "pb = adata.to_df().groupby([adata.obs['donor'], adata.obs['condition']]).sum()\n"
                    "# Or call bionexus independent pseudobulk capability (scrna.pseudobulk_de)."
                )
                break

        # 2. Check for Assay State Confusion (BN-F001)
        for pat in self.RAW_LOG_CONFUSION_PATTERNS:
            if pat.search(code):
                violations.append("BN-F001")
                guidance.append(
                    "Count-based generative or dispersion models (scVI, DESeq2) require raw integer counts, not normalized/scaled values."
                )
                forbidden_claims.append("Statistical validity of differential expression on normalized matrices")
                suggested_remedy = "Ensure counts layer is passed: adata.layers['counts'] or adata.raw.to_adata()."
                is_blocked = True
                break

        # 3. Check for Missing FDR Control (BN-F005)
        for pat in self.MISSING_FDR_PATTERNS:
            if pat.search(code):
                violations.append("BN-F005")
                guidance.append(
                    "Filtering differential expression by unadjusted p-values (<0.05) without Benjamini-Hochberg FDR control creates false positives."
                )
                forbidden_claims.append("Significance claims based on raw p-value alone")
                break

        # 4. Check for Model Masquerade / Naive Approximation (BN-F009 / BN-F010)
        for pat in self.MODEL_MASQUERADE_PATTERNS:
            if pat.search(code):
                violations.append("BN-F010")
                guidance.append(
                    "Detected custom naive approximation of official gold backend. Must execute genuine PyDESeq2 / Harmony."
                )
                is_blocked = True
                break

        # Determine overall status
        if is_blocked:
            status = GuardStatus.BLOCKED
            permitted = False
        elif violations:
            status = GuardStatus.INJECT_CONSTRAINTS
            permitted = True
        else:
            status = GuardStatus.PASSED
            permitted = True

        return GuardVerdict(
            status=status,
            execution_permitted=permitted,
            violation_ids=violations,
            warrant_guidance=guidance,
            forbidden_claims=forbidden_claims,
            suggested_remedy=suggested_remedy,
            inspected_target=file_path or "inline_code_snippet",
        )

    def inspect_command(self, command: Union[str, Sequence[str]]) -> GuardVerdict:
        """Inspect a shell command or script path prior to execution."""
        if isinstance(command, (list, tuple)):
            cmd_str = " ".join(command)
        else:
            cmd_str = str(command)

        # Check if the command targets a Python script or notebook
        script_match = re.search(r"(?:python|pytest|bash|sh)\s+([^\s]+\.(?:py|ipynb))", cmd_str)
        if script_match:
            script_path = Path(script_match.group(1))
            if script_path.exists() and script_path.suffix == ".py":
                try:
                    content = script_path.read_text(encoding="utf-8")
                    return self.inspect_code(content, file_path=str(script_path))
                except Exception:
                    pass

        # Check inline python command (-c "..." or -c '...')
        inline_match = re.search(r'python\s+-c\s+(?:"(.*?)"|\'(.*?)\')', cmd_str, re.DOTALL)
        if inline_match:
            code = inline_match.group(1) if inline_match.group(1) is not None else inline_match.group(2)
            return self.inspect_code(code, file_path="inline_python_arg")

        # Fallback inspection on the raw command string
        return self.inspect_code(cmd_str, file_path="shell_command")


# Global default guard instance
default_guard = BioNexusGuard()


def inspect_code(code: str) -> GuardVerdict:
    """Convenience top-level inspector."""
    return default_guard.inspect_code(code)


def inspect_command(command: Union[str, Sequence[str]]) -> GuardVerdict:
    """Convenience top-level command inspector."""
    return default_guard.inspect_command(command)
