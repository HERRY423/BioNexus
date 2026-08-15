"""
Unit tests for BioNexus Machine-Readable Scientific Capability Contracts.

Validates:
1. Canonical capability loading, schema validity, and intent resolution.
2. Semantic input validation (counts vs normalized floats).
3. Precondition enforcement and deterministic refusal triggers:
   - scrna.pseudobulk_de (missing replicates, normalized input)
   - spatial.morans_svg (insufficient spatial spots)
   - survival.kaplan_meier (zero events)
   - scvi.probabilistic_vae (raw counts invariant)
4. Capability viability evaluation and EvidenceCard synthesis.
5. Capability CLI commands (list, show, check).
"""

import sys
from pathlib import Path

# Ensure src is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.capabilities import (
    CANONICAL_CAPABILITIES,
    evaluate_capability_preconditions,
    find_capabilities_by_intent,
)
from bionexus.cli import main as cli_main
from bionexus.contracts import ConclusionMaturity


def test_canonical_capabilities_inventory():
    """Verify standard capabilities exist and declare valid fields."""
    assert "scrna.pseudobulk_de" in CANONICAL_CAPABILITIES
    assert "spatial.morans_svg" in CANONICAL_CAPABILITIES
    assert "survival.kaplan_meier" in CANONICAL_CAPABILITIES
    assert "scvi.probabilistic_vae" in CANONICAL_CAPABILITIES
    assert "allotrope.format_conversion" in CANONICAL_CAPABILITIES
    assert "nextflow.pipeline_launch" in CANONICAL_CAPABILITIES
    assert "variant.acmg_classification" in CANONICAL_CAPABILITIES

    for cap_id, cap in CANONICAL_CAPABILITIES.items():
        assert cap.id == cap_id
        assert len(cap.intent) > 0
        assert cap.skill_name != ""
        assert cap.backend.canonical_name != ""
        d = cap.to_dict()
        assert isinstance(d, dict)
        assert d["id"] == cap_id


def test_find_capabilities_by_intent():
    """Verify capabilities can be discovered by user intent."""
    de_caps = find_capabilities_by_intent("differential_expression")
    assert len(de_caps) >= 1
    assert any(c.id == "scrna.pseudobulk_de" for c in de_caps)

    spatial_caps = find_capabilities_by_intent("spatial_transcriptomics")
    assert len(spatial_caps) >= 1
    assert any(c.id == "spatial.morans_svg" for c in spatial_caps)

    survival_caps = find_capabilities_by_intent("survival_analysis")
    assert len(survival_caps) >= 1
    assert any(c.id == "survival.kaplan_meier" for c in survival_caps)


def test_pseudobulk_de_precondition_replicates_refusal():
    """Verify Pseudobulk DE deterministically refuses when replicates < 2."""
    # Invalid: Only 1 replicate
    eval_invalid = evaluate_capability_preconditions(
        "scrna.pseudobulk_de",
        input_metadata={"min_replicates_per_condition": 1, "is_integer_like": True},
    )
    assert eval_invalid.permitted is False
    assert eval_invalid.status == "REFUSED"
    assert eval_invalid.conclusion_maturity == ConclusionMaturity.ABSTAIN.value
    assert any("replicates" in v.lower() for v in eval_invalid.violations)
    assert len(eval_invalid.remedies) >= 1

    # Valid: 3 replicates
    eval_valid = evaluate_capability_preconditions(
        "scrna.pseudobulk_de",
        input_metadata={"min_replicates_per_condition": 3, "is_integer_like": True},
    )
    from bionexus.backends import is_available
    if is_available("pydeseq2"):
        assert eval_valid.permitted is True
        assert eval_valid.status == "PERMITTED"
    else:
        assert any("pydeseq2" in v.lower() for v in eval_valid.violations)


def test_pseudobulk_de_normalized_matrix_refusal():
    """Verify Pseudobulk DE refuses when continuous normalized matrix provided."""
    eval_norm = evaluate_capability_preconditions(
        "scrna.pseudobulk_de",
        input_metadata={
            "min_replicates_per_condition": 3,
            "is_normalized": True,
            "is_integer_like": False,
        },
    )
    assert eval_norm.permitted is False
    assert eval_norm.status == "REFUSED"
    assert any("normalized" in v.lower() for v in eval_norm.violations)
    assert any("raw" in r.lower() for r in eval_norm.remedies)


def test_spatial_moran_insufficient_spots_refusal():
    """Verify Spatial SVG refuses when spatial points < 5."""
    eval_few_spots = evaluate_capability_preconditions(
        "spatial.morans_svg",
        input_metadata={"n_spatial_spots": 2},
    )
    assert eval_few_spots.permitted is False
    assert eval_few_spots.status == "REFUSED"
    assert any("spatial spots" in v.lower() for v in eval_few_spots.violations)


def test_scvi_vae_raw_counts_invariant():
    """Verify scvi-tools requires raw integer counts."""
    eval_norm = evaluate_capability_preconditions(
        "scvi.probabilistic_vae",
        input_metadata={"is_normalized": True, "is_integer_like": False},
    )
    assert eval_norm.permitted is False
    assert any("normalized" in v.lower() for v in eval_norm.violations)


def test_cli_capability_commands(capsys):
    """Verify capability subcommands in BioNexus CLI."""
    # 1. list
    rc = cli_main(["capability", "list"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "scrna.pseudobulk_de" in captured.out
    assert "spatial.morans_svg" in captured.out

    # 2. show
    rc = cli_main(["capability", "show", "scrna.pseudobulk_de"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "Single-Cell Pseudobulk Differential Expression" in captured.out
    assert "Input Semantic Specifications" in captured.out

    # 3. check with refusal
    rc = cli_main(["capability", "check", "scrna.pseudobulk_de", "--min-replicates", "1"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "[REFUSED]" in captured.out
    assert "Fewer than 2 biological replicates" in captured.out


def test_preflight_vs_postexecution_evidence_distinction():
    """Verify EvidenceCard 2.1 preflight evidence remains PRELIMINARY and UNTESTED for statistics."""
    eval_res = evaluate_capability_preconditions(
        "scrna.exploratory_clustering",
        input_metadata={"is_integer_like": True},
    )
    assert eval_res.permitted is True
    assert eval_res.status == "PERMITTED"
    assert eval_res.conclusion_maturity == ConclusionMaturity.PRELIMINARY.value

    card = eval_res.evidence_card
    assert card.statistical_support == "UNTESTED"
    assert card.parameter_robustness == "UNTESTED"
    assert card.external_validation == "UNTESTED"
    assert card.details["evaluation_stage"] == "preflight_viability"

