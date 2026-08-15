#!/usr/bin/env python3
"""
Scientific Hypothesis Tracking and Evidence Weighting Engine.
Applies Bayesian evidence synthesis and multi-criteria decision models
to rank target feasibility, disease associations, and experimental hypotheses.

Usage:
    from hypothesis_tracker import HypothesisTracker

    tracker = HypothesisTracker("Inhibition of KRAS G12D suppresses pancreatic adenocarcinoma progression")
    tracker.add_evidence("Genetic Support (ClinVar)", score=0.9, weight=0.35, source="ClinVar")
    tracker.add_evidence("Bioactive Inhibitor Available (ChEMBL MRTX1133)", score=0.85, weight=0.25, source="ChEMBL")
    report = tracker.evaluate()
"""

from datetime import datetime, timezone
from typing import Any, Dict, List


class HypothesisTracker:
    def __init__(self, hypothesis_statement: str, prior_probability: float = 0.5):
        self.statement = hypothesis_statement
        self.prior = min(max(0.01, float(prior_probability)), 0.99)
        self.evidence_list: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "UNDER_EVALUATION",
        }

    def add_evidence(
        self,
        name: str,
        score: float,
        weight: float = 1.0,
        direction: str = "support",
        source: str = "unspecified",
        notes: str = "",
    ):
        """
        Add a piece of scientific evidence.

        Parameters
        ----------
        name : str
            Description of the evidence (e.g. 'GWAS p-value < 5e-8')
        score : float
            Strength score between 0.0 (weak/inconclusive) and 1.0 (definitive)
        weight : float
            Relative importance weight (default: 1.0)
        direction : str
            'support' (positive evidence) or 'refute' (negative/counter evidence)
        source : str
            Data source (e.g. 'PubMed', 'Open Targets', 'In Vitro Assay')
        notes : str
            Optional experimental observations
        """
        score = min(max(0.0, float(score)), 1.0)
        weight = max(0.1, float(weight))
        direction = direction.lower() if direction.lower() in ("support", "refute") else "support"

        self.evidence_list.append(
            {
                "name": name,
                "score": score,
                "weight": weight,
                "direction": direction,
                "source": source,
                "notes": notes,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def calculate_weighted_evidence_score(self) -> float:
        """Calculate aggregate evidence score (-1.0 to +1.0)."""
        if not self.evidence_list:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for ev in self.evidence_list:
            sign = 1.0 if ev["direction"] == "support" else -1.0
            weighted_sum += sign * ev["score"] * ev["weight"]
            total_weight += ev["weight"]

        return weighted_sum / max(1e-6, total_weight)

    def calculate_bayesian_posterior(self) -> float:
        """
        Compute posterior probability P(H | E) given accumulated independent evidence pieces.
        Odds(H | E) = Odds(H) * Product(Likelihood_Ratio_i)
        """
        if not self.evidence_list:
            return self.prior

        # Convert prior probability to odds
        prior_odds = self.prior / (1.0 - self.prior)
        curr_odds = prior_odds

        for ev in self.evidence_list:
            score = ev["score"]
            if ev["direction"] == "support":
                # Likelihood ratio LR+ = P(E|H) / P(E|not H) scaled by weight
                lr = 1.0 + (score * 4.0 * (ev["weight"] / 1.0))
            else:
                # Likelihood ratio LR- for refuting evidence
                lr = 1.0 / (1.0 + (score * 4.0 * (ev["weight"] / 1.0)))

            curr_odds *= lr

        # Convert posterior odds back to probability
        posterior_prob = curr_odds / (1.0 + curr_odds)
        return min(max(0.01, posterior_prob), 0.99)

    def evaluate(self) -> Dict[str, Any]:
        """Generate comprehensive hypothesis evaluation report."""
        posterior = self.calculate_bayesian_posterior()
        weighted_score = self.calculate_weighted_evidence_score()

        if posterior >= 0.80:
            recommendation = "STRONG_SUPPORT - Proceed to validation assays and protocol design"
            status = "SUPPORTED"
        elif posterior >= 0.60:
            recommendation = "MODERATE_SUPPORT - Gather additional orthogonal experimental evidence"
            status = "TENTATIVE"
        elif posterior <= 0.30:
            recommendation = "REFUTED - Re-evaluate target or explore alternate pathways"
            status = "REFUTED"
        else:
            recommendation = "INCONCLUSIVE - Equivocal evidence; requires exploratory screening"
            status = "INCONCLUSIVE"

        self.metadata["status"] = status

        report = {
            "hypothesis": self.statement,
            "prior_probability": round(self.prior, 4),
            "posterior_probability": round(posterior, 4),
            "aggregate_evidence_score": round(weighted_score, 4),
            "status": status,
            "recommendation": recommendation,
            "num_evidence_items": len(self.evidence_list),
            "evidence_details": self.evidence_list,
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return report

    def to_markdown(self) -> str:
        """Export report to GitHub-flavored Markdown format."""
        eval_res = self.evaluate()
        md = [
            f"# Hypothesis Evaluation: {self.statement}\n",
            f"- **Status**: `{eval_res['status']}`",
            f"- **Prior Probability**: {eval_res['prior_probability']:.2f}",
            f"- **Posterior Probability**: **{eval_res['posterior_probability']:.2f}**",
            f"- **Recommendation**: {eval_res['recommendation']}\n",
            "## Evidence Log\n",
            "| Direction | Source | Evidence | Strength | Weight | Notes |",
            "|---|---|---|---|---|---|",
        ]
        for ev in self.evidence_list:
            dir_icon = "🟢 Support" if ev["direction"] == "support" else "🔴 Refute"
            md.append(
                f"| {dir_icon} | {ev['source']} | {ev['name']} | {ev['score']:.2f} | {ev['weight']:.1f} | {ev['notes']} |"
            )

        return "\n".join(md)
