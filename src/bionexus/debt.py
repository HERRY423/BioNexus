"""
BioNexus Evidence Debt Engine (BNS-021).

Defines the formal taxonomy, dependency propagation, and repayment optimization
for Scientific Evidence Debt.

Scientific projects do not have a single "reliability score" (e.g. 83%).
They carry concrete, structured Evidence Debt items that degrade claim maturity
ceilings across the epistemic dependency DAG.

Key concepts:
1. EvidenceDebtItem: A concrete scientific shortcut or unverified assumption.
2. DebtKind: Strict taxonomy of epistemic liabilities.
3. PayoffLeverage: Number and severity of downstream claims upgraded per remediation.
4. OptimalRepaymentSchedule: Actionable priority queue for scientific validation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from bionexus.contracts import ConclusionMaturity
from bionexus.ledger import MATURITY_RANKS, ClaimLedger, ClaimRecord, EvidenceRef


class DebtKind(str, Enum):
    """Taxonomy of scientific evidence debt items (BNS-021 §2)."""

    UNRESOLVED_ALTERNATIVE_EXPLANATION = "UNRESOLVED_ALTERNATIVE_EXPLANATION"
    HEURISTIC_DEPENDENCY = "HEURISTIC_DEPENDENCY"
    MISSING_INDEPENDENT_REPLICATION = "MISSING_INDEPENDENT_REPLICATION"
    PARAMETER_SENSITIVITY = "PARAMETER_SENSITIVITY"
    UNREVIEWED_CALIBRATION_THRESHOLD = "UNREVIEWED_CALIBRATION_THRESHOLD"
    DOMAIN_MISMATCH = "DOMAIN_MISMATCH"
    UNACCOUNTED_CONFOUNDER = "UNACCOUNTED_CONFOUNDER"
    CAUSAL_IDENTIFICATION_GAP = "CAUSAL_IDENTIFICATION_GAP"
    UNVALIDATED_BATCH_CORRECTION = "UNVALIDATED_BATCH_CORRECTION"
    AMBIENT_SIGNAL_CONTAMINATION = "AMBIENT_SIGNAL_CONTAMINATION"


class DebtSeverity(str, Enum):
    """Severity of epistemic debt impact."""

    CRITICAL = "CRITICAL"  # Forces ABSTAIN / FRAGILE on downstream claims
    HIGH = "HIGH"          # Caps claims at SUPPORTED / PRELIMINARY
    MEDIUM = "MEDIUM"      # Prevents graduation from SUPPORTED to ROBUST
    LOW = "LOW"            # Advisory / minor provenance gap


SEVERITY_WEIGHTS = {
    DebtSeverity.CRITICAL.value: 10.0,
    DebtSeverity.HIGH.value: 5.0,
    DebtSeverity.MEDIUM.value: 2.0,
    DebtSeverity.LOW.value: 1.0,
}


@dataclass
class RemediationRecipe:
    """Actionable recipe for repaying a specific evidence debt item."""

    action_title: str
    description: str
    target_backend_or_method: Optional[str] = None
    verification_metric: Optional[str] = None
    estimated_effort: str = "MODERATE"  # LOW | MODERATE | HIGH | EXPERIMENTAL

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EvidenceDebtItem:
    """A concrete scientific evidence debt record (BNS-021 §3)."""

    debt_id: str
    debt_kind: DebtKind
    severity: DebtSeverity
    title: str
    description: str
    root_node_id: str  # ID of the evidence or transformation node in ClaimLedger
    affected_claim_ids: List[str] = field(default_factory=list)
    remediation: Optional[RemediationRecipe] = None
    literature_citations: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def downstream_impact_count(self) -> int:
        return len(self.affected_claim_ids)

    @property
    def severity_weight(self) -> float:
        return SEVERITY_WEIGHTS.get(self.severity.value, 1.0)

    @property
    def leverage_score(self) -> float:
        """Payoff leverage score = downstream_impact * severity_weight."""
        return self.downstream_impact_count * self.severity_weight

    def to_dict(self) -> Dict[str, Any]:
        return {
            "debt_id": self.debt_id,
            "debt_kind": self.debt_kind.value,
            "severity": self.severity.value,
            "title": self.title,
            "description": self.description,
            "root_node_id": self.root_node_id,
            "affected_claim_ids": list(self.affected_claim_ids),
            "downstream_impact_count": self.downstream_impact_count,
            "leverage_score": self.leverage_score,
            "remediation": self.remediation.to_dict() if self.remediation else None,
            "literature_citations": self.literature_citations,
            "metadata": self.metadata,
        }


@dataclass
class RemediationPriority:
    """An item in the optimal scientific repayment schedule."""

    rank: int
    debt_item: EvidenceDebtItem
    claims_unblocked: List[str]
    potential_maturity_upgrade: str
    payoff_multiplier: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rank": self.rank,
            "debt_id": self.debt_item.debt_id,
            "debt_kind": self.debt_item.debt_kind.value,
            "severity": self.debt_item.severity.value,
            "title": self.debt_item.title,
            "root_node_id": self.debt_item.root_node_id,
            "claims_unblocked": self.claims_unblocked,
            "claims_unblocked_count": len(self.claims_unblocked),
            "potential_maturity_upgrade": self.potential_maturity_upgrade,
            "payoff_multiplier": self.payoff_multiplier,
            "remediation_action": self.debt_item.remediation.action_title if self.debt_item.remediation else "",
            "estimated_effort": self.debt_item.remediation.estimated_effort if self.debt_item.remediation else "MODERATE",
        }


@dataclass
class EvidenceDebtAuditReport:
    """Comprehensive Evidence Debt summary report across a scientific project."""

    total_claims: int
    total_debt_items: int
    debt_items: List[EvidenceDebtItem]
    debt_by_kind: Dict[str, int]
    debt_by_severity: Dict[str, int]
    claim_maturity_distribution: Dict[str, int]
    epistemic_keystones: List[Dict[str, Any]]  # High-impact root nodes
    optimal_repayment_schedule: List[RemediationPriority]
    project_maturity_floor: str
    project_potential_maturity: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_claims": self.total_claims,
            "total_debt_items": self.total_debt_items,
            "project_maturity_floor": self.project_maturity_floor,
            "project_potential_maturity": self.project_potential_maturity,
            "debt_by_kind": self.debt_by_kind,
            "debt_by_severity": self.debt_by_severity,
            "claim_maturity_distribution": self.claim_maturity_distribution,
            "debt_items": [d.to_dict() for d in self.debt_items],
            "epistemic_keystones": self.epistemic_keystones,
            "optimal_repayment_schedule": [p.to_dict() for p in self.optimal_repayment_schedule],
        }


class EvidenceDebtEngine:
    """
    Analyzes claim dependency DAGs and calculates Evidence Debt & Payoff Schedules (BNS-021).
    """

    @classmethod
    def audit_ledger(cls, ledger: ClaimLedger) -> EvidenceDebtAuditReport:
        """
        Perform a full Evidence Debt audit across a ClaimLedger.
        """
        # 1. Build DAG adjacency maps (forward and reverse)
        # evidence_node -> list of claims that depend on it
        ev_to_claims: Dict[str, Set[str]] = {}
        claim_to_ev: Dict[str, Set[str]] = {}

        for cid, claim in ledger.claims.items():
            claim_to_ev[cid] = set(claim.supported_by + claim.depends_on)
            for ref in claim_to_ev[cid]:
                ev_to_claims.setdefault(ref, set()).add(cid)

        # 2. Detect evidence debt items
        debt_items: List[EvidenceDebtItem] = []
        debt_idx = 1

        for rid, ref in ledger.evidence.items():
            detected_debts = cls._detect_evidence_debts(rid, ref, ev_to_claims.get(rid, set()), ledger)
            for d in detected_debts:
                d.debt_id = f"DEBT-{debt_idx:03d}"
                debt_idx += 1
                debt_items.append(d)

        # 3. Detect claim-level debts (e.g. unassessed causal claims, missing replication)
        for cid, claim in ledger.claims.items():
            claim_debts = cls._detect_claim_debts(cid, claim, ledger)
            for d in claim_debts:
                d.debt_id = f"DEBT-{debt_idx:03d}"
                debt_idx += 1
                debt_items.append(d)

        # 4. Aggregate counts and distributions
        debt_by_kind: Dict[str, int] = {}
        debt_by_severity: Dict[str, int] = {}
        for d in debt_items:
            k = d.debt_kind.value
            debt_by_kind[k] = debt_by_kind.get(k, 0) + 1
            s = d.severity.value
            debt_by_severity[s] = debt_by_severity.get(s, 0) + 1

        maturity_dist: Dict[str, int] = {}
        for claim in ledger.claims.values():
            m = claim.evidence_status
            maturity_dist[m] = maturity_dist.get(m, 0) + 1

        # 5. Compute Epistemic Keystones (Nodes that affect the most claims)
        keystones: List[Dict[str, Any]] = []
        root_node_impact: Dict[str, Set[str]] = {}
        for d in debt_items:
            root_node_impact.setdefault(d.root_node_id, set()).update(d.affected_claim_ids)

        for r_id, aff_claims in sorted(root_node_impact.items(), key=lambda x: len(x[1]), reverse=True):
            if not aff_claims:
                continue
            ref_obj = ledger.evidence.get(r_id)
            summary = ref_obj.summary if ref_obj else f"Node {r_id}"
            keystones.append({
                "root_node_id": r_id,
                "summary": summary,
                "affected_claims_count": len(aff_claims),
                "affected_claim_ids": list(aff_claims),
            })

        # 6. Generate Optimal Repayment Schedule
        # Rank debt items by leverage score (impact * severity)
        sorted_debts = sorted(debt_items, key=lambda d: d.leverage_score, reverse=True)
        repayment_schedule: List[RemediationPriority] = []

        for rank, d in enumerate(sorted_debts, start=1):
            upgrade_target = ConclusionMaturity.ROBUST.value if d.severity in (DebtSeverity.CRITICAL, DebtSeverity.HIGH) else ConclusionMaturity.SUPPORTED.value
            repayment_schedule.append(
                RemediationPriority(
                    rank=rank,
                    debt_item=d,
                    claims_unblocked=list(d.affected_claim_ids),
                    potential_maturity_upgrade=upgrade_target,
                    payoff_multiplier=d.leverage_score,
                )
            )

        # 7. Project overall maturity floors
        if not ledger.claims:
            p_floor = ConclusionMaturity.UNASSESSED.value
            p_potential = ConclusionMaturity.UNASSESSED.value
        else:
            ranks = [MATURITY_RANKS.get(c.evidence_status, 0) for c in ledger.claims.values()]
            min_rank = min(ranks)
            max_rank = max(ranks)
            p_floor = next(m for m, r in MATURITY_RANKS.items() if r == min_rank)
            p_potential = next(m for m, r in MATURITY_RANKS.items() if r == max(max_rank, 4))

        return EvidenceDebtAuditReport(
            total_claims=len(ledger.claims),
            total_debt_items=len(debt_items),
            debt_items=debt_items,
            debt_by_kind=debt_by_kind,
            debt_by_severity=debt_by_severity,
            claim_maturity_distribution=maturity_dist,
            epistemic_keystones=keystones[:5],
            optimal_repayment_schedule=repayment_schedule,
            project_maturity_floor=p_floor,
            project_potential_maturity=p_potential,
        )

    @classmethod
    def _detect_evidence_debts(
        cls,
        node_id: str,
        ref: EvidenceRef,
        affected_claims: Set[str],
        ledger: ClaimLedger,
    ) -> List[EvidenceDebtItem]:
        """Detect debts rooted in a specific evidence node."""
        debts: List[EvidenceDebtItem] = []
        prov = ref.provenance or {}
        aff_list = sorted(list(affected_claims))

        # Check 1: Heuristic cell-type annotation / reference mapping
        if ref.kind == "transformation" or "annotation" in ref.summary.lower():
            if prov.get("heuristic_marker_gating") or "heuristic" in ref.summary.lower() or ref.maturity == ConclusionMaturity.FRAGILE.value:
                debts.append(
                    EvidenceDebtItem(
                        debt_id="",
                        debt_kind=DebtKind.HEURISTIC_DEPENDENCY,
                        severity=DebtSeverity.CRITICAL if len(aff_list) >= 3 else DebtSeverity.HIGH,
                        title=f"Heuristic Annotation Dependency on {node_id}",
                        description=f"Cell annotation node '{node_id}' relies on manual or uncalibrated marker gating without reference concordance validation.",
                        root_node_id=node_id,
                        affected_claim_ids=aff_list,
                        remediation=RemediationRecipe(
                            action_title=f"Validate {node_id} against Reference Atlas",
                            description="Cross-evaluate cell annotations using CellTypist or Azimuth reference mapping, verifying F1 > 0.85.",
                            target_backend_or_method="reference_mapping_concordance",
                            verification_metric="macro_F1 >= 0.85",
                            estimated_effort="LOW",
                        ),
                        literature_citations=["Abdelaal et al. 2019 Genome Biology (Single-cell cell-type annotation benchmark)"],
                    )
                )

        # Check 2: Domain mismatch across atlas transfer
        if prov.get("domain_mismatch") or "domain_mismatch" in ref.summary.lower():
            debts.append(
                EvidenceDebtItem(
                    debt_id="",
                    debt_kind=DebtKind.DOMAIN_MISMATCH,
                    severity=DebtSeverity.CRITICAL,
                    title=f"Reference Atlas Domain Mismatch in {node_id}",
                    description="Reference atlas dataset differs in condition, tissue compartment, or disease state from target cohort (e.g. PBMC vs Tumor Microenvironment).",
                    root_node_id=node_id,
                    affected_claim_ids=aff_list,
                    remediation=RemediationRecipe(
                        action_title=f"Execute Domain-Adapted Transfer on {node_id}",
                        description="Retrain latent projection with scANVI/scVI cell-type fine-tuning or use disease-matched atlas.",
                        target_backend_or_method="scvi-tools:scANVI",
                        verification_metric="latent_silhouette_batch < 0.15",
                        estimated_effort="MODERATE",
                    ),
                    literature_citations=["Luecken et al. 2022 Nature Methods (scIB benchmark)"],
                )
            )

        # Check 3: Ambient RNA contamination uncorrected
        if prov.get("ambient_uncorrected") or "ambient" in ref.summary.lower():
            debts.append(
                EvidenceDebtItem(
                    debt_id="",
                    debt_kind=DebtKind.AMBIENT_SIGNAL_CONTAMINATION,
                    severity=DebtSeverity.HIGH,
                    title=f"Ambient RNA Contamination in {node_id}",
                    description="Count matrix contains uncorrected ambient cell-free mRNA, risking false marker discovery.",
                    root_node_id=node_id,
                    affected_claim_ids=aff_list,
                    remediation=RemediationRecipe(
                        action_title=f"Run Ambient RNA Decontamination on {node_id}",
                        description="Apply CellBender or DecontX background subtraction to purge droplet ambient soup.",
                        target_backend_or_method="cellbender.remove_background",
                        verification_metric="ambient_fraction_reduction >= 80%",
                        estimated_effort="LOW",
                    ),
                    literature_citations=["Fleming et al. 2023 Nature Methods (CellBender)"],
                )
            )

        # Check 4: Parameter instability / unreviewed clustering resolution
        if prov.get("unstable_resolution") or prov.get("parameter_sensitivity") or ref.maturity == ConclusionMaturity.CONFLICTED.value:
            debts.append(
                EvidenceDebtItem(
                    debt_id="",
                    debt_kind=DebtKind.PARAMETER_SENSITIVITY,
                    severity=DebtSeverity.HIGH,
                    title=f"Clustering Parameter Sensitivity on {node_id}",
                    description="Cluster partitions or marker sets shift significantly under resolution sweep (0.4 to 1.2).",
                    root_node_id=node_id,
                    affected_claim_ids=aff_list,
                    remediation=RemediationRecipe(
                        action_title=f"Run Multi-Resolution Stability Audit on {node_id}",
                        description="Evaluate Adjusted Rand Index (ARI) and Silhouette across resolutions 0.4, 0.6, 0.8, 1.0.",
                        target_backend_or_method="bionexus.integrity.audit_cluster_stability",
                        verification_metric="mean_ARI > 0.80",
                        estimated_effort="LOW",
                    ),
                )
            )

        return debts

    @classmethod
    def _detect_claim_debts(
        cls,
        claim_id: str,
        claim: ClaimRecord,
        ledger: ClaimLedger,
    ) -> List[EvidenceDebtItem]:
        """Detect debts directly associated with a specific claim."""
        debts: List[EvidenceDebtItem] = []
        w_eval = claim.warrant_evaluation or {}
        reasons = w_eval.get("reasons", [])

        # Check 1: Missing Independent Replication
        if claim.evidence_status in (ConclusionMaturity.PRELIMINARY.value, ConclusionMaturity.FRAGILE.value):
            has_ext = any(
                ledger.evidence[r].kind in ("database", "cross_method")
                for r in claim.supported_by
                if r in ledger.evidence
            )
            if not has_ext:
                debts.append(
                    EvidenceDebtItem(
                        debt_id="",
                        debt_kind=DebtKind.MISSING_INDEPENDENT_REPLICATION,
                        severity=DebtSeverity.HIGH if "causal" in claim.statement.lower() else DebtSeverity.MEDIUM,
                        title=f"Missing Independent Cohort Replication for {claim_id}",
                        description=f"Claim '{claim.statement}' is derived from a single cohort without cross-dataset validation.",
                        root_node_id=claim_id,
                        affected_claim_ids=[claim_id],
                        remediation=RemediationRecipe(
                            action_title=f"Cross-Validate {claim_id} on Independent Cohort",
                            description="Test effect size replication across an independent public dataset (GEO/SRA).",
                            target_backend_or_method="pydeseq2_cross_cohort",
                            verification_metric="concordant_log2fc_sign_and_fdr < 0.05",
                            estimated_effort="MODERATE",
                        ),
                        literature_citations=["Squair et al. 2021 Nature Communications"],
                    )
                )

        # Check 2: Causal Identification Gap
        if "causes" in claim.statement.lower() or "drives" in claim.statement.lower():
            has_causal_dag = any(
                ledger.evidence[r].kind in ("causal_dag", "perturbation")
                for r in claim.supported_by
                if r in ledger.evidence
            )
            if not has_causal_dag:
                debts.append(
                    EvidenceDebtItem(
                        debt_id="",
                        debt_kind=DebtKind.CAUSAL_IDENTIFICATION_GAP,
                        severity=DebtSeverity.CRITICAL,
                        title=f"Unwarranted Causal Inference in {claim_id}",
                        description=f"Claim asserts causal mechanism '{claim.statement}' from observational correlation without perturbation proof or DAG backdoor adjustment.",
                        root_node_id=claim_id,
                        affected_claim_ids=[claim_id],
                        remediation=RemediationRecipe(
                            action_title=f"Formulate Causal DAG & Sensitivity for {claim_id}",
                            description="Specify structural causal model, test d-separation, and evaluate E-value robustness.",
                            target_backend_or_method="bionexus.causal.evaluate_dag",
                            verification_metric="E_value > 2.5",
                            estimated_effort="HIGH",
                        ),
                        literature_citations=["Pearl 2009 Causality; VanderWeele & Ding 2017 Ann Intern Med"],
                    )
                )

        # Check 3: Alternative Explanations Unresolved (Confounders)
        unresolved_alts = [r for r in reasons if "alternative explanation" in r.lower() or "confound" in r.lower()]
        if unresolved_alts:
            debts.append(
                EvidenceDebtItem(
                    debt_id="",
                    debt_kind=DebtKind.UNRESOLVED_ALTERNATIVE_EXPLANATION,
                    severity=DebtSeverity.HIGH,
                    title=f"Unresolved Alternative Explanations in {claim_id}",
                    description="; ".join(unresolved_alts),
                    root_node_id=claim_id,
                    affected_claim_ids=[claim_id],
                    remediation=RemediationRecipe(
                        action_title=f"Run Alternative Explanation Battery for {claim_id}",
                        description="Audit candidate confounders: donor batch, cell cycle score, sequencing depth, and spatial cell density.",
                        target_backend_or_method="bionexus.integrity.audit_alternative_explanations",
                        verification_metric="confounder_R2 < 0.05",
                        estimated_effort="LOW",
                    ),
                )
            )

        return debts


# ==============================================================================
# Rendering & Presentation
# ==============================================================================


def render_terminal_debt_report(report: EvidenceDebtAuditReport, verbose: bool = False) -> str:
    """Render a visual, high-signal Evidence Debt terminal report."""
    lines: List[str] = []
    w = 80
    lines.append("=" * w)
    lines.append("                 BioNexus Scientific Evidence Debt Report".center(w))
    lines.append("=" * w)
    lines.append(f"Total Claims Analyzed:     {report.total_claims}")
    lines.append(f"Total Evidence Debt Items: {report.total_debt_items}")
    lines.append(f"Project Maturity Floor:    [{report.project_maturity_floor}]")
    lines.append(f"Potential Project Ceiling: [{report.project_potential_maturity}] (Upon Debt Amortization)")
    lines.append("-" * w)

    # Debt Breakdown by Kind
    lines.append("EVIDENCE DEBT BY CATEGORY:")
    for kind, count in sorted(report.debt_by_kind.items(), key=lambda x: x[1], reverse=True):
        bar = "#" * min(count * 2, 30)
        lines.append(f"  {kind:<36} {count:>3}  {bar}")
    lines.append("-" * w)

    # Epistemic Keystones (High-Leverage Root Bottlenecks)
    if report.epistemic_keystones:
        lines.append("EPISTEMIC KEYSTONES (High-Leverage Verification Bottlenecks):")
        for k in report.epistemic_keystones:
            lines.append(
                f"  [*] Node: {k['root_node_id']} ({k['summary']}) -> Affects {k['affected_claims_count']} claims"
            )
            lines.append(f"      Downstream: {', '.join(k['affected_claim_ids'][:6])}")
        lines.append("-" * w)

    # Optimal Repayment Schedule
    lines.append("OPTIMAL EVIDENCE REPAYMENT SCHEDULE (Ranked by Scientific Payoff):")
    lines.append(f"{'RANK':<5} {'DEBT ID':<10} {'SEVERITY':<10} {'CLAIMS':<8} {'PAYOFF':<8} {'ACTION'}")
    lines.append("-" * w)

    for p in report.optimal_repayment_schedule[:8]:
        d = p.debt_item
        act = d.remediation.action_title if d.remediation else d.title
        lines.append(
            f"#{p.rank:<4} {d.debt_id:<10} {d.severity.value:<10} {len(p.claims_unblocked):>2} claims  {p.payoff_multiplier:>5.1f}x  {act[:34]}"
        )

    lines.append("=" * w)
    return "\n".join(lines)


def render_markdown_debt_report(report: EvidenceDebtAuditReport) -> str:
    """Render a comprehensive Markdown Evidence Debt certificate & action plan."""
    md: List[str] = []
    md.append("# 📑 BioNexus Scientific Evidence Debt Report")
    md.append("")
    md.append("> **Scientific reliability is not a vanity score.** It is an auditable accounting of deferred verifications, heuristic shortcuts, and unresolved alternative hypotheses across the project dependency DAG.")
    md.append("")
    md.append("## 1. Project Epistemic Posture")
    md.append("")
    md.append(f"- **Total Scientific Claims**: `{report.total_claims}`")
    md.append(f"- **Active Evidence Debt Items**: `{report.total_debt_items}`")
    md.append(f"- **Current Maturity Floor**: `{report.project_maturity_floor}`")
    md.append(f"- **Project Potential Maturity**: `{report.project_potential_maturity}` *(when debt is amortized)*")
    md.append("")
    md.append("### Claim Maturity Distribution")
    md.append("| Maturity Level | Claim Count | Epistemic Standing |")
    md.append("| :--- | :---: | :--- |")
    for m, count in report.claim_maturity_distribution.items():
        md.append(f"| `{m}` | **{count}** | {m} evidence status |")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 2. Evidence Debt by Kind")
    md.append("")
    md.append("| Debt Category | Count | Primary Epistemic Risk | Remediation Target |")
    md.append("| :--- | :---: | :--- | :--- |")
    for kind, count in report.debt_by_kind.items():
        md.append(f"| `{kind}` | **{count}** | Deferred assumption / shortcut | Targeted verification battery |")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 3. Epistemic Keystones (High-Leverage Bottlenecks)")
    md.append("")
    md.append("Fixing a single foundational upstream node amortizes debt across multiple downstream claims simultaneously:")
    md.append("")
    for k in report.epistemic_keystones:
        md.append(f"### 🎯 Keystone: `{k['root_node_id']}`")
        md.append(f"- **Node Description**: {k['summary']}")
        md.append(f"- **Downstream Claims Blocked**: `{k['affected_claims_count']}` claims (`{', '.join(k['affected_claim_ids'])}`)")
        md.append("")
    md.append("---")
    md.append("")
    md.append("## 4. Optimal Scientific Repayment Schedule")
    md.append("")
    md.append("| Rank | Debt ID | Severity | Claims Unblocked | Payoff Leverage | Prescribed Remediation | Effort |")
    md.append("| :---: | :--- | :---: | :---: | :---: | :--- | :---: |")
    for p in report.optimal_repayment_schedule:
        d = p.debt_item
        act = d.remediation.action_title if d.remediation else d.title
        eff = d.remediation.estimated_effort if d.remediation else "MODERATE"
        md.append(
            f"| **#{p.rank}** | `{d.debt_id}` | `{d.severity.value}` | **{len(p.claims_unblocked)} claims** | **{p.payoff_multiplier:.1f}x** | {act} | `{eff}` |"
        )
    md.append("")
    return "\n".join(md)


def render_mermaid_debt_dag(report: EvidenceDebtAuditReport, ledger: Optional[ClaimLedger] = None) -> str:
    """Render a Mermaid DAG diagram visualizing Evidence Debt propagation."""
    mermaid: List[str] = ["```mermaid", "graph TD"]

    # Add debt items and their affected claims.
    for d in report.debt_items:
        node_label = f'"{d.debt_id}: {d.title[:25]}...<br/>[Severity: {d.severity.value}]"'
        mermaid.append(f"    {d.debt_id}[{node_label}]")

        for cid in d.affected_claim_ids[:5]:
            mermaid.append(f"    {d.debt_id} -->|degrades| {cid}")

    mermaid.append("```")
    return "\n".join(mermaid)


def create_sample_debt_ledger() -> ClaimLedger:
    """
    Generate an exemplary 20-claim research project ledger exhibiting realistic Evidence Debt (BNS-021).

    Demonstrates the exact epistemic keystone phenomenon:
    - Foundational node 'TRANSFORM-ANNOTATION-X' carries heuristic gating & domain mismatch debt.
    - 7 downstream claims (CLAIM-001, CLAIM-004, CLAIM-007, CLAIM-012, CLAIM-017, CLAIM-019, CLAIM-020)
      inherit degraded FRAGILE status from this single keystone.
    - Amortizing TRANSFORM-ANNOTATION-X unblocks all 7 claims simultaneously with 70.0x payoff leverage!
    """
    ledger = ClaimLedger()

    # Evidence & Transformation Nodes
    ledger.add_evidence(
        EvidenceRef(
            ref_id="EVID-DATASET-01",
            kind="dataset",
            summary="Primary single-cell RNA-seq count matrix (10x Genomics, 6 donors)",
            maturity=ConclusionMaturity.ROBUST.value,
        )
    )
    ledger.add_evidence(
        EvidenceRef(
            ref_id="TRANSFORM-QC",
            kind="transformation",
            summary="Standard MAD filter QC and library size normalization",
            maturity=ConclusionMaturity.ROBUST.value,
        )
    )
    ledger.add_evidence(
        EvidenceRef(
            ref_id="TRANSFORM-ANNOTATION-X",
            kind="transformation",
            summary="Heuristic marker-based gating of T-cell subsets (PBMC reference on tumor infiltrate)",
            maturity=ConclusionMaturity.FRAGILE.value,
            provenance={"heuristic_marker_gating": True, "domain_mismatch": True},
        )
    )
    ledger.add_evidence(
        EvidenceRef(
            ref_id="TRANSFORM-SPATIAL-MAPPING",
            kind="transformation",
            summary="Spatial neighbor adjacency mapping (Visium HD, 8-nearest neighbors)",
            maturity=ConclusionMaturity.SUPPORTED.value,
            provenance={"parameter_sensitivity": True},
        )
    )
    ledger.add_evidence(
        EvidenceRef(
            ref_id="EVID-DE-RUN-01",
            kind="method_run",
            summary="DESeq2 pseudobulk differential expression across donor replicates",
            maturity=ConclusionMaturity.SUPPORTED.value,
        )
    )
    ledger.add_evidence(
        EvidenceRef(
            ref_id="EVID-CLINICAL-DB",
            kind="database",
            summary="UniProt & OpenTargets curated oncology drug target annotations",
            maturity=ConclusionMaturity.ROBUST.value,
        )
    )

    # 20 Research Project Claims
    # Subgraph A: 7 Claims dependent on Keystone TRANSFORM-ANNOTATION-X
    keystone_claims = [
        ("CLAIM-001", "CD8+ T cells exhibit exhaustion phenotype under prolonged checkpoint therapy", ["TRANSFORM-ANNOTATION-X", "EVID-DE-RUN-01"]),
        ("CLAIM-004", "LAG3 and HAVCR2 are co-expressed exclusively in exhausted CD8+ subset", ["TRANSFORM-ANNOTATION-X", "TRANSFORM-QC"]),
        ("CLAIM-007", "Exhausted CD8+ T cells show marked downregulation of cytotoxic granzyme B", ["TRANSFORM-ANNOTATION-X", "EVID-DE-RUN-01"]),
        ("CLAIM-012", "Transcription factor TOX expression correlates with CD8+ exhaustion severity", ["TRANSFORM-ANNOTATION-X"]),
        ("CLAIM-017", "Target gene CD274 is specifically upregulated in Exhausted CD8+ T cells under treatment", ["TRANSFORM-ANNOTATION-X", "EVID-DE-RUN-01", "EVID-CLINICAL-DB"]),
        ("CLAIM-019", "Progenitor exhausted T cells transition toward terminal exhaustion in tumor core", ["TRANSFORM-ANNOTATION-X", "TRANSFORM-SPATIAL-MAPPING"]),
        ("CLAIM-020", "CD8+ exhaustion signature predicts non-responsiveness to anti-PD1 monotherapy", ["TRANSFORM-ANNOTATION-X", "EVID-DE-RUN-01"]),
    ]

    for cid, stmt, deps in keystone_claims:
        ledger.add_claim(
            ClaimRecord(
                claim_id=cid,
                statement=stmt,
                capability_id="scrna.pseudobulk_de",
                supported_by=deps,
                depends_on=["EVID-DATASET-01"],
            )
        )

    # Subgraph B: Other 13 Claims
    other_claims = [
        ("CLAIM-002", "Tumor endothelial cells upregulate angiogenic markers VEGFA and KDR", ["TRANSFORM-QC", "EVID-DE-RUN-01"]),
        ("CLAIM-003", "B-cell infiltration density is highest in tertiary lymphoid structures", ["TRANSFORM-SPATIAL-MAPPING"]),
        ("CLAIM-005", "Macrophage M2 polarization score correlates with spatial distance to hypoxia zone", ["TRANSFORM-SPATIAL-MAPPING"]),
        ("CLAIM-006", "Fibroblast subset FAP+ represents primary source of extracellular collagen matrix", ["TRANSFORM-QC", "EVID-CLINICAL-DB"]),
        ("CLAIM-008", "Plasma cells demonstrate clonotype expansion within TLS microdomains", ["TRANSFORM-SPATIAL-MAPPING"]),
        ("CLAIM-009", "NK cell cytotoxicity signature remains invariant across treatment arms", ["TRANSFORM-QC", "EVID-DE-RUN-01"]),
        ("CLAIM-010", "Dendritic cell cross-presentation module is suppressed in central tumor core", ["TRANSFORM-SPATIAL-MAPPING"]),
        ("CLAIM-011", "Hypoxic stress drives glycolytic switch in tumor-infiltrating myeloid cells", ["TRANSFORM-QC"]),
        ("CLAIM-013", "Ligand-receptor pair CXCL12-CXCR4 mediates spatial retention of regulatory T cells", ["TRANSFORM-SPATIAL-MAPPING"]),
        ("CLAIM-014", "TP53 missense mutations correlate with increased chromosomal instability index", ["EVID-CLINICAL-DB"]),
        ("CLAIM-015", "Interferon-gamma signaling signature is elevated in responder pre-treatment biopsies", ["EVID-DE-RUN-01", "EVID-CLINICAL-DB"]),
        ("CLAIM-016", "Spatial colocalization of CD8+ T cells and DC1 correlates with patient progression-free survival", ["TRANSFORM-SPATIAL-MAPPING", "EVID-CLINICAL-DB"]),
        ("CLAIM-018", "Epithelial-to-mesenchymal transition score is highest at invasive tumor margin", ["TRANSFORM-SPATIAL-MAPPING"]),
    ]

    for cid, stmt, deps in other_claims:
        ledger.add_claim(
            ClaimRecord(
                claim_id=cid,
                statement=stmt,
                capability_id="scrna.pseudobulk_de",
                supported_by=deps,
                depends_on=["EVID-DATASET-01"],
            )
        )

    return ledger
