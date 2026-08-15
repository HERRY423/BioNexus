"""
Unit tests for BioNexus Scientific Intent & Invariant Router.

Validates the 6-stage Scientific Intent Routing Pipeline:
1. Intent recognition from scientific query strings.
2. Missing experimental metadata detection (NEEDS_DATA).
3. Scientific violation and pseudoreplication refusal (ABSTAIN).
4. Precondition validation and gold-backend clearance (PERMITTED).
5. Explicit heuristic fallback routing (DEGRADED_ADVISORY).
6. CLI route subcommand behavior.
"""

import sys
from pathlib import Path

# Ensure src is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.agent_routing import (
    RoutingStatus,
    extract_scientific_capability,
    route_scientific_intent,
)
from bionexus.cli import main as cli_main


def test_extract_scientific_capability_patterns():
    """Verify natural language queries map to canonical capabilities."""
    cap1 = extract_scientific_capability("Compare tumor vs normal cells in single cell RNA seq")
    assert cap1 is not None
    assert cap1.id == "scrna.pseudobulk_de"

    cap2 = extract_scientific_capability("Identify marker genes with Leiden clustering in scanpy")
    assert cap2 is not None
    assert cap2.id == "scrna.exploratory_clustering"

    cap3 = extract_scientific_capability("Detect spatially variable genes using Moran's I on Visium spots")
    assert cap3 is not None
    assert cap3.id == "spatial.morans_svg"

    cap4 = extract_scientific_capability("Fit Kaplan-Meier survival curve for treatment cohort")
    assert cap4 is not None
    assert cap4.id == "survival.kaplan_meier"

    cap5 = extract_scientific_capability("Train scVI deep generative latent embedding")
    assert cap5 is not None
    assert cap5.id == "scvi.probabilistic_vae"


def test_route_pseudobulk_de_lifecycle():
    """Verify full decision lifecycle for condition differential expression."""
    # 1. NEEDS_DATA: Query without replicates or data path
    dec_needs = route_scientific_intent("Compare drug treated vs control in scRNA")
    assert dec_needs.status == RoutingStatus.NEEDS_DATA
    assert dec_needs.matched_capability is not None
    assert dec_needs.matched_capability.id == "scrna.pseudobulk_de"
    assert len(dec_needs.missing_data_requests) >= 1

    # 2. ABSTAIN: Single replicate provided (Pseudoreplication violation)
    dec_abstain = route_scientific_intent(
        "Compare drug treated vs control in scRNA",
        data_metadata={"min_replicates_per_condition": 1, "is_integer_like": True},
    )
    assert dec_abstain.status == RoutingStatus.ABSTAIN
    assert any("replicates" in v.lower() for v in dec_abstain.violations)
    assert len(dec_abstain.remedies) >= 1

    # 3. ABSTAIN: Continuous normalized floats provided
    dec_norm = route_scientific_intent(
        "Compare drug treated vs control in scRNA",
        data_metadata={
            "min_replicates_per_condition": 3,
            "is_normalized": True,
            "is_integer_like": False,
        },
    )
    assert dec_norm.status == RoutingStatus.ABSTAIN
    assert any("normalized" in v.lower() for v in dec_norm.violations)

    # 4. PERMITTED (if pydeseq2 backend available)
    from bionexus.backends import is_available

    dec_perm = route_scientific_intent(
        "Compare drug treated vs control in scRNA",
        data_metadata={"min_replicates_per_condition": 3, "is_integer_like": True},
    )
    if is_available("pydeseq2"):
        assert dec_perm.status == RoutingStatus.PERMITTED
        assert dec_perm.recommended_script is not None
    else:
        assert dec_perm.status == RoutingStatus.ABSTAIN


def test_route_spatial_moran_svg():
    """Verify spatial transcriptomics routing."""
    dec = route_scientific_intent(
        "Find spatially variable genes in 10x Visium tissue",
        data_metadata={"n_spatial_spots": 500},
    )
    from bionexus.backends import is_available

    if is_available("squidpy"):
        assert dec.status == RoutingStatus.PERMITTED
        assert dec.target_skill == "spatial-transcriptomics"
    else:
        assert dec.status == RoutingStatus.ABSTAIN


def test_route_legacy_degraded_advisory():
    """Verify legacy skill routing with and without explicit degradation permission."""
    from bionexus.backends import is_available

    if not is_available("lifelines"):
        # Without allow_degraded: ABSTAIN
        dec_abstain = route_scientific_intent(
            "Kaplan-Meier survival estimation for clinical cohort",
            allow_degraded=False,
        )
        assert dec_abstain.status == RoutingStatus.ABSTAIN

        # With allow_degraded: DEGRADED_ADVISORY
        dec_degraded = route_scientific_intent(
            "Kaplan-Meier survival estimation for clinical cohort",
            allow_degraded=True,
        )
        assert dec_degraded.status == RoutingStatus.DEGRADED_ADVISORY
        assert dec_degraded.target_skill == "clinical-cohort-analysis"


def test_cli_route_subcommand(capsys):
    """Verify CLI 'bionexus route' output formatting."""
    # 1. NEEDS_DATA
    rc = cli_main(["route", "compare treated vs control in scRNA"])
    assert rc == 2
    captured = capsys.readouterr()
    assert "[NEEDS DATA]" in captured.out

    # 2. ABSTAIN
    rc = cli_main(["route", "compare treated vs control in scRNA", "--min-replicates", "1"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "[ABSTAIN / REFUSED]" in captured.out

    # 3. JSON output
    rc = cli_main(["route", "compare treated vs control in scRNA", "--min-replicates", "1", "--json"])
    assert rc == 1
    captured = capsys.readouterr()
    assert '"status": "ABSTAIN"' in captured.out
