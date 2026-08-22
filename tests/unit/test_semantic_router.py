"""
Unit tests for the deterministic semantic nomination layer (BNS-013 dual-layer routing).

Invariants under test:
- Pure determinism: same query -> same nomination.
- Fail-closed on ambiguity (margin guard) and low scores.
- Host nominations are validated against the registry, never trusted blindly.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from bionexus.capabilities import ALL_CAPABILITIES
from bionexus.intent_router import extract_scientific_capability, route_scientific_intent
from bionexus.semantic_router import (
    MIN_MARGIN,
    MIN_SEMANTIC_SCORE,
    nominate_semantically,
    score_capabilities,
    validate_nomination,
)


def test_deterministic_same_query_same_nomination():
    q = "Find spatially variable genes across tissue positions on the visium slide"
    a = nominate_semantically(q)
    b = nominate_semantically(q)
    assert a == b
    assert a.nominated_capability == "spatial.morans_svg"


def test_semantic_layer_resolves_unpatterned_spatial_query():
    """A spatial-intent query with no regex hit must reach the spatial capability."""
    q = "Which genes show autocorrelation across neighboring tissue positions?"
    assert extract_scientific_capability(q) is not None
    assert extract_scientific_capability(q).id == "spatial.morans_svg"


def test_ambiguous_query_fails_closed():
    """Queries equidistant between two capabilities must nominate nothing."""
    # Fully hits both tangram deconvolution AND annotation evidence -> tie -> margin guard.
    q = "tangram deconvolution with reference annotation label transfer"
    nom = nominate_semantically(q)
    assert nom.nominated_capability is None
    assert nom.layer == "none"
    assert nom.runner_up is not None  # ambiguity was detected, not absence of signal


def test_low_information_query_fails_closed():
    nom = nominate_semantically("hello what can you do for me today")
    assert nom.nominated_capability is None


def test_scores_are_normalized_and_sorted():
    ranked = score_capabilities("leiden clustering of single cells with marker genes")
    assert ranked[0][0] == "scrna.exploratory_clustering"
    assert 0.0 <= ranked[0][1] <= 1.0
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)


def test_host_nomination_validated_against_registry():
    cap, audit = validate_nomination("scrna.pseudobulk_de", ALL_CAPABILITIES)
    assert cap is not None and cap.id == "scrna.pseudobulk_de"
    assert audit.layer == "nominated"

    cap_bad, audit_bad = validate_nomination("made.up.capability", ALL_CAPABILITIES)
    assert cap_bad is None
    assert audit_bad.layer == "none"


def test_route_records_routing_layer_and_audit():
    decision = route_scientific_intent(
        "Which genes show autocorrelation across neighboring tissue positions?",
        data_metadata={"coordinate_type": "physical"},
    )
    assert decision.matched_capability.id == "spatial.morans_svg"
    assert decision.routing_layer in {"pattern", "semantic"}
    d = decision.to_dict()
    assert d["routing_layer"] == decision.routing_layer
    assert isinstance(d["routing_audit"], dict)


def test_nominated_capability_flows_through_router():
    decision = route_scientific_intent(
        "analyze this dataset",
        nominated_capability="survival.kaplan_meier",
        data_metadata={"n_patients": 50, "event_observed": True},
    )
    assert decision.routing_layer == "nominated"
    assert decision.matched_capability.id == "survival.kaplan_meier"


def test_invalid_nomination_fails_closed_to_needs_data():
    decision = route_scientific_intent(
        "analyze this dataset",
        nominated_capability="nonexistent.capability",
    )
    assert decision.status.value == "NEEDS_DATA"
    assert decision.matched_capability is None
    assert "nomination_rejected" in decision.routing_audit


def test_thresholds_are_importable_constants():
    assert 0 < MIN_MARGIN < 1 and 0 < MIN_SEMANTIC_SCORE < 1
