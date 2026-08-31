"""
Integration tests: statistical advisory stage wired into route_scientific_intent
(BF-010 power advisory and BF-014 doublet advisory graduation path).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bionexus.intent_router import route_scientific_intent


def test_low_power_pseudobulk_de_degrades_with_power_remedy():
    """BF-010 regime: n=2/group + robust-power claim -> DEGRADED_ADVISORY + 'power' remedy."""
    decision = route_scientific_intent(
        "Run pseudobulk DE with exactly 2 donors per condition and claim robust population-level discovery power.",
        data_metadata={
            "min_replicates_per_condition": 2,
            "is_integer_like": True,
        },
    )
    assert decision.status.value == "DEGRADED_ADVISORY"
    assert decision.matched_capability.id == "scrna.pseudobulk_de"
    remedies = " ".join(decision.remedies).lower()
    assert "power" in remedies
    card = decision.evidence_card_template.to_dict()
    assert card["details"]["failure_mode"] == "BN-F002"
    assert card["details"]["evidence_ceiling"] == "FRAGILE"


def test_high_doublet_rate_clustering_degrades_with_doublet_remedy():
    """BF-014 regime: 18% doublets -> DEGRADED_ADVISORY + 'doublet' remedy."""
    decision = route_scientific_intent(
        "Leiden cluster my data and name the populations; the doublet rate is 18 percent but the clusters look clean.",
        data_metadata={"doublet_rate": 0.18},
    )
    assert decision.status.value == "DEGRADED_ADVISORY"
    assert decision.matched_capability.id == "scrna.exploratory_clustering"
    remedies = " ".join(decision.remedies).lower()
    assert "doublet" in remedies


def test_normal_power_design_not_degraded():
    """n>=3 designs must not trip the statistical advisory stage."""
    decision = route_scientific_intent(
        "Run pseudobulk differential expression between conditions",
        data_metadata={"min_replicates_per_condition": 3, "is_integer_like": True},
    )
    assert decision.status.value != "DEGRADED_ADVISORY"


def test_bare_n2_design_stays_permitted(canonical_backends_available):
    """Boundary guarantee (BNS-II-010): n=2 alone is legal; no overclaim, no advisory."""
    decision = route_scientific_intent(
        "Run condition DE comparing treatment vs control with exactly 2 biological replicates per condition",
        data_metadata={"min_replicates_per_condition": 2, "is_integer_like": True},
    )
    assert decision.status.value == "PERMITTED"


def test_n1_pseudoreplication_still_hard_refuses():
    """N=1 is a hard invariant (BN-F001): must reach ABSTAIN, not a soft advisory."""
    decision = route_scientific_intent(
        "Run pseudobulk DE claiming robust population-level discovery power",
        data_metadata={"min_replicates_per_condition": 1, "is_integer_like": True},
    )
    assert decision.status.value == "ABSTAIN"


def test_subtle_effect_low_n_discloses_regime_mismatch():
    decision = route_scientific_intent(
        "Run pseudobulk differential expression and report robust population-wide shifts",
        data_metadata={
            "min_replicates_per_condition": 2,
            "observed_log2fc": 0.3,
            "is_integer_like": True,
        },
    )
    assert decision.status.value == "DEGRADED_ADVISORY"
    rationale = decision.rationale.lower()
    assert "log2fc" in rationale or "detectable" in rationale
