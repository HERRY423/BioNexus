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
    """A simple computation request carries no claim of population power."""
    decision = route_scientific_intent(
        "Run pseudobulk differential expression between conditions",
        data_metadata={"min_replicates_per_condition": 3, "is_integer_like": True},
    )
    assert decision.status.value != "DEGRADED_ADVISORY"


def test_population_discovery_request_exposes_fdr_adjusted_mde_at_five_donors():
    decision = route_scientific_intent(
        "Run pseudobulk DE and claim robust population-level discovery power.",
        data_metadata={"min_replicates_per_condition": 5, "is_integer_like": True,
                       "n_tests": 15000, "n_true_effects": 300, "observed_log2fc": 8},
    )
    assert decision.status.value == "DEGRADED_ADVISORY"
    power = decision.evidence_card_template.to_dict()["details"]["statistical_power"]
    assert power["alpha_basis"] == "jung2005"
    assert power["observed_effect_regime"] is None


def test_named_unequal_arms_use_contrast_specific_power(canonical_backends_available):
    request = "Run pseudobulk DE and assess population-level power for the claimed effect."
    options = {"donors_per_condition": {"case": 4, "control": 12}, "dispersion": 0.5,
               "shrunk_log2fc": 1.8, "base_mean": 100, "is_integer_like": True}
    # At this effect: MDE = 1.67 with the measured arm sizes, but 2.04 at 4 + 4.
    assert route_scientific_intent(request, data_metadata=options).status.value == "PERMITTED"
    options["shrunk_log2fc"] = 1
    limited = route_scientific_intent(request, data_metadata=options)
    assert limited.status.value == "DEGRADED_ADVISORY"
    power = limited.evidence_card_template.details["statistical_power"]
    assert power["n_by_group"] == options["donors_per_condition"]
    assert 1 < power["mde_log2fc"] < 1.8
    options["donors_per_condition"] = {"case": 1, "control": 12}
    assert route_scientific_intent(request, data_metadata=options).status.value == "ABSTAIN"


def test_invalid_power_and_doublet_inputs_request_data():
    power = route_scientific_intent(
        "Run pseudobulk DE and claim robust population-level discovery power.",
        data_metadata={"min_replicates_per_condition": 5, "is_integer_like": True, "target_power": 1.1},
    )
    doublet = route_scientific_intent(
        "Leiden cluster my data and name the populations.",
        data_metadata={"doublet_rate": 1.1},
    )
    assert power.status.value == doublet.status.value == "NEEDS_DATA"


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
