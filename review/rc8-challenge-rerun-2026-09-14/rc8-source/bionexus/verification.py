"""
BioNexus Result Verification (BNS-013, firewall entry point 3).

    bionexus verify results/

Runs at the END of the analysis, over the final results:

    CLAIM
    CXCL13+ T cells are enriched in tumor

    Evidence:
    [OK] differential abundance (method_run, SUPPORTED)
    [~] parameter sensitivity (statistical_result, FRAGILE)
    [X] orthogonal validation — absent

    Warrant: SUPPORTED
    Not warranted: "CXCL13+ T cells drive tumor progression"

Input is a Claim–Evidence Ledger (BNS-012) — a `bionexus.ledger.json` file or
a directory containing one. Verification re-resolves every claim fail-closed,
cross-checks the resolved status against the capability's evidence ceiling and
forbidden-claim catalog, and flags causal/mechanistic language that the
evidence class cannot warrant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from bionexus.abi import FORBIDDEN_CLAIM_CATALOG, get_capability_abi
from bionexus.claim_semantics import detect_assertive_causal_language
from bionexus.ledger import MATURITY_RANKS, ClaimLedger, ClaimRecord, EvidenceRef

_LEDGER_NAMES = ("bionexus.ledger.json", "ledger.json")
# Legacy pattern retained for reference/compat; active detection is the shared,
# negation-aware `detect_assertive_causal_language` (claim_semantics).
_CAUSAL_LANGUAGE = re.compile(
    r"\b(?:drives?|causes?|caused|induces?|induced|proves?|proven|mechanism of action|is causal)\b",
    re.IGNORECASE,
)


def locate_ledger(path: str | Path) -> Path:
    """Resolve a ledger file from an explicit path or a results directory."""
    p = Path(path)
    if p.is_file():
        return p
    if p.is_dir():
        for name in _LEDGER_NAMES:
            candidate = p / name
            if candidate.is_file():
                return candidate
        hits = sorted(p.glob("*.ledger.json"))
        if hits:
            return hits[0]
        recursive = sorted(p.rglob("bionexus.ledger.json"))
        if recursive:
            return recursive[0]
    raise FileNotFoundError(
        f"No Claim–Evidence Ledger found at '{p}'. Expected a ledger JSON file, or a directory "
        "containing bionexus.ledger.json / *.ledger.json."
    )


@dataclass
class ClaimVerification:
    """Verification outcome for one claim in the ledger."""

    claim_id: str
    statement: str
    capability_id: Optional[str]
    evidence_status: str
    evidence_lines: List[Dict[str, Any]] = field(default_factory=list)
    not_warranted: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)
    ok: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "statement": self.statement,
            "capability_id": self.capability_id,
            "evidence_status": self.evidence_status,
            "evidence": self.evidence_lines,
            "not_warranted": self.not_warranted,
            "flags": self.flags,
            "ok": self.ok,
        }


@dataclass
class VerificationReport:
    """Aggregate verification outcome for a results ledger."""

    ledger_path: str
    claims: List[ClaimVerification] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.claims) and all(c.ok for c in self.claims)

    @property
    def exit_code(self) -> int:
        if not self.claims:
            return 1
        return 0 if self.passed else 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ledger_path": self.ledger_path,
            "passed": self.passed,
            "claims": [c.to_dict() for c in self.claims],
        }


def _evidence_symbol(maturity: str) -> str:
    m = str(maturity).upper()
    if m in ("SUPPORTED", "ROBUST", "REPLICATED"):
        return "[OK]"
    if m in ("PRELIMINARY", "FRAGILE", "CONFLICTED"):
        return "[~]"
    return "[X]"


def verify_ledger(ledger: ClaimLedger, ledger_path: str = "<ledger>") -> VerificationReport:
    """
    Verify every claim in a Claim–Evidence ledger (fail-closed re-resolution).

    A claim fails verification when it resolves ABSTAIN or CONFLICTED, when it
    carries causal/mechanistic language its evidence class cannot warrant, or
    when its statement matches the capability's forbidden-claim catalog.
    """
    report = VerificationReport(ledger_path=ledger_path)

    for claim_id, claim in ledger.claims.items():
        status = ledger.resolve_status(claim_id)
        lines: List[Dict[str, Any]] = []
        for ref_id in claim.supported_by:
            ref: Optional[EvidenceRef] = ledger.evidence.get(ref_id)
            if ref is None:
                lines.append({"symbol": "[X]", "ref_id": ref_id, "kind": "unresolved", "maturity": "UNASSESSED", "summary": "referenced but not defined in the ledger"})
                continue
            lines.append(
                {
                    "symbol": _evidence_symbol(ref.maturity),
                    "ref_id": ref_id,
                    "kind": ref.kind,
                    "maturity": ref.maturity,
                    "summary": ref.summary or ref.kind,
                }
            )
        for ref_id in claim.contradicted_by:
            ref = ledger.evidence.get(ref_id)
            lines.append(
                {
                    "symbol": "[X]",
                    "ref_id": ref_id,
                    "kind": (ref.kind if ref else "unresolved"),
                    "maturity": (ref.maturity if ref else "UNASSESSED"),
                    "summary": f"CONTRADICTS: {ref.summary if ref else 'referenced but not defined'}",
                }
            )
        if not claim.supported_by and not claim.contradicted_by and not claim.depends_on:
            lines.append({"symbol": "[X]", "ref_id": None, "kind": "absent", "maturity": "ABSTAIN", "summary": "no supporting evidence recorded"})
        for ref_id in claim.depends_on:
            ref = ledger.evidence.get(ref_id)
            if ref is None:
                continue
            lines.append(
                {
                    "symbol": _evidence_symbol(ref.maturity),
                    "ref_id": ref_id,
                    "kind": ref.kind,
                    "maturity": ref.maturity,
                    "summary": f"context: {ref.summary or ref.kind}",
                }
            )

        not_warranted: List[str] = []
        flags: List[str] = []
        ok = True

        if status in ("ABSTAIN",):
            flags.append("claim resolves ABSTAIN: no supporting evidence (BNS-CL-005)")
            ok = False
        if status == "CONFLICTED":
            flags.append("claim resolves CONFLICTED: contradicting evidence present (BNS-CL-005)")
            ok = False

        if claim.capability_id:
            try:
                abi = get_capability_abi(claim.capability_id)
                ceiling = abi.evidence_ceiling.without_external_validation
                has_ext = any(
                    (ledger.evidence[r].kind in ("database", "cross_method"))
                    for r in claim.supported_by
                    if r in ledger.evidence
                )
                rank = MATURITY_RANKS.get(status, 0)
                if rank > MATURITY_RANKS.get(ceiling, 3) and not has_ext:
                    flags.append(f"status '{status}' exceeds ceiling '{ceiling}' without external validation")
                for fcid in abi.forbidden_claims:
                    entry = FORBIDDEN_CLAIM_CATALOG[fcid]
                    not_warranted.append(f'"{entry.description}" (forbidden: {fcid})')
            except KeyError:
                flags.append(f"unknown capability_id '{claim.capability_id}'")

        causal_hit = detect_assertive_causal_language(claim.statement)
        if causal_hit:
            not_warranted.append(
                f'"{claim.statement.strip()}" — assertive causal language ("{causal_hit}"); this evidence class '
                "supports association/enrichment language only"
            )
            ok = False

        report.claims.append(
            ClaimVerification(
                claim_id=claim_id,
                statement=claim.statement,
                capability_id=claim.capability_id,
                evidence_status=status,
                evidence_lines=lines,
                not_warranted=not_warranted,
                flags=flags,
                ok=ok,
            )
        )
    return report


def verify_results(path: str | Path) -> VerificationReport:
    """Locate and verify the ledger behind a results file or directory."""
    ledger_path = locate_ledger(path)
    ledger = ClaimLedger.load(ledger_path)
    return verify_ledger(ledger, ledger_path=str(ledger_path))


def render_verification(report: VerificationReport) -> str:
    """Render the verification block in the BNS-013 output contract."""
    lines: List[str] = []
    lines.append(f"=== BioNexus Result Verification: {report.ledger_path} ===")
    lines.append("")
    if not report.claims:
        lines.append("No claims recorded in the ledger.")
        lines.append("")
        return "\n".join(lines)
    for c in report.claims:
        lines.append(f"CLAIM [{c.claim_id}]")
        lines.append(f"  {c.statement}")
        lines.append("")
        lines.append("  Evidence:")
        for e in c.evidence_lines:
            ref = f"{e['ref_id']}: " if e.get("ref_id") else ""
            lines.append(f"  {e['symbol']} {ref}{e['summary']} ({e['kind']}, {e['maturity']})")
        lines.append("")
        lines.append(f"  Warrant: {c.evidence_status}")
        for flag in c.flags:
            lines.append(f"  [!!] {flag}")
        if c.not_warranted:
            lines.append("  Not warranted:")
            for nw in c.not_warranted:
                lines.append(f"  - {nw}")
        lines.append("")
    verdict = "VERIFIED" if report.passed else "VERIFICATION FAILED"
    n_ok = sum(1 for c in report.claims if c.ok)
    lines.append(f"OVERALL: {verdict} ({n_ok}/{len(report.claims)} claims clean)")
    return "\n".join(lines)


def write_example_ledger(path: str | Path) -> Path:
    """
    Write the reference example ledger used in docs/tests (CLAIM-DEMO-017).

    The CXCL13+ T-cell enrichment scenario from the BNS-013 contract.
    """
    from bionexus.contracts import ConclusionMaturity

    p = Path(path)
    ledger = ClaimLedger()
    ledger.add_evidence(EvidenceRef("EVID-DA", "method_run", "differential abundance test on independent donors", ConclusionMaturity.SUPPORTED.value))
    ledger.add_evidence(EvidenceRef("EVID-DONOR", "dataset", "8 independent donors, balanced conditions", ConclusionMaturity.SUPPORTED.value))
    ledger.add_evidence(EvidenceRef("EVID-FDR", "statistical_result", "BH FDR q < 0.05 across tested genes", ConclusionMaturity.SUPPORTED.value))
    ledger.add_evidence(EvidenceRef("EVID-REPL", "cross_method", "second cohort replication", ConclusionMaturity.SUPPORTED.value))
    ledger.add_evidence(EvidenceRef("EVID-SENS", "statistical_result", "parameter sensitivity: borderline at k=30", ConclusionMaturity.FRAGILE.value))
    ledger.add_claim(
        ClaimRecord(
            claim_id="CLAIM-DEMO-017",
            statement="CXCL13+ T cells are enriched in tumor",
            capability_id="scrna.pseudobulk_de",
            supported_by=["EVID-DA", "EVID-DONOR", "EVID-FDR", "EVID-REPL"],
            depends_on=["EVID-SENS"],
        )
    )
    p.parent.mkdir(parents=True, exist_ok=True)
    ledger.save(p)
    return p
