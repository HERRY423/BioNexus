"""
Semantic-understanding regression battery (routing paraphrases + claim-parse
precision). Quantified upgrade rationale (2026-08-25); see module docstrings of
semantic_router.py / claim_semantics.py and CHANGELOG for the failure modes.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "src"))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bionexus.claim_semantics import (  # noqa: E402
    CausalStrength,
    DeterministicClaimParser,
    GeneralizationScope,
    detect_assertive_causal_language,
)
from bionexus.contracts import ConclusionMaturity  # noqa: E402
from bionexus.evidence_model import ClaimClass  # noqa: E402
from bionexus.intent_router import extract_scientific_capability  # noqa: E402
from bionexus.ledger import ClaimLedger, ClaimRecord, EvidenceRef  # noqa: E402
from bionexus.semantic_router import (  # noqa: E402
    detect_concepts_and_variants,
    nominate_semantically,
    score_capabilities,
)
from bionexus.verification import verify_ledger  # noqa: E402

# ---------------------------------------------------------------------------
# R1. Whole-token boundary matching kills lexical false positives.
# ---------------------------------------------------------------------------


def test_r1_zoom_never_triggers_oom_memory_concept():
    concepts, _ = detect_concepts_and_variants("zoom into the embedding plot")
    assert "memory" not in concepts
    nom = nominate_semantically("zoom into the embedding plot")
    assert nom.nominated_capability is None  # low information -> fail closed


def test_r1_tangram_no_longer_counts_as_ram():
    ranked = dict(score_capabilities("tangram mapping of scRNA clusters onto spots"))
    assert ranked["bigdata.out_of_core_audit"] == 0.0
    top_id, _top_score = max(ranked.items(), key=lambda kv: kv[1])
    assert top_id == "spatial.tangram_deconvolution"


def test_r1_ambiguity_fail_closed_is_now_conceptually_real():
    """The legacy tie was annotation_evidence(1.0) vs out_of_core_audit(1.0 via
    tan(g)ram->ram). Now the tie is two genuinely plausible capabilities."""
    ranked = score_capabilities("tangram deconvolution with reference annotation label transfer")
    top_two = [cap for cap, _ in ranked[:2]]
    assert "scrna.annotation_evidence" in top_two
    assert "spatial.tangram_deconvolution" in top_two
    nom = nominate_semantically("tangram deconvolution with reference annotation label transfer")
    assert nom.nominated_capability is None  # genuine ambiguity -> fail closed


# ---------------------------------------------------------------------------
# R2/R3/R4. Token normalization + expanded curated registry.
# ---------------------------------------------------------------------------


def test_r2_hyphen_and_space_variants_are_equivalent():
    hyph, space = "slide-seq tissue data", "slide seq tissue data"
    c1, c2 = detect_concepts_and_variants(hyph)[0], detect_concepts_and_variants(space)[0]
    assert "spatial" in c1 and "spatial" in c2


def test_r3_plural_inflections_match_via_folding():
    concepts, _ = detect_concepts_and_variants("annotate these clusters and their marker genes")
    assert "clustering" in concepts and "marker_genes" in concepts


def test_r4_new_validity_phrasing_routes_to_inference_validity():
    nom = nominate_semantically(
        "robustness of the tissue coordinate result against negative controls"
    )
    assert nom.nominated_capability == "spatial.inference_validity"


def test_r4_reference_atlas_tooling_routes_to_annotation_evidence():
    q = "How confident is the azimuth reference atlas label on cluster 4?"
    cap = extract_scientific_capability(q)
    assert cap is not None and cap.id == "scrna.annotation_evidence"


# ---------------------------------------------------------------------------
# End-to-end routing paraphrases (pattern OR semantic layer must land correctly).
# ---------------------------------------------------------------------------

_PARAPHRASES = [
    ("Which patients respond differently, plot survival by treatment arm?", "survival.kaplan_meier"),
    ("Estimate whether my RAM can hold a matrix this large", "bigdata.out_of_core_audit"),
    ("Run differential testing on upregulated genes between groups", "scrna.pseudobulk_de"),
    ("Project cell types into physical coordinates with tangram", "spatial.tangram_deconvolution"),
    ("Does the spatial conclusion hold under alternative explanations?", "spatial.inference_validity"),
]


def test_routing_paraphrase_table():
    for query, expected in _PARAPHRASES:
        cap = extract_scientific_capability(query)
        assert cap is not None, f"no route for: {query}"
        assert cap.id == expected, f"{query!r} -> {cap.id}, expected {expected}"


# ---------------------------------------------------------------------------
# P1/P2. Hedge precision: word boundaries + modal windows.
# ---------------------------------------------------------------------------


def test_p1_unlikely_is_not_a_hedge():
    ir = DeterministicClaimParser.parse(
        "Smoking causes cancer; the effect is unlikely to be confounded by age."
    )
    assert "likely" not in ir.qualifiers
    assert ir.causal_strength == CausalStrength.COUNTERFACTUAL_CAUSAL


def test_p2_modal_hedge_downgrades_causal_strength():
    ir = DeterministicClaimParser.parse("IL-7 may promote tissue-resident memory formation.")
    assert ir.causal_strength == CausalStrength.HYPOTHESIZED_CAUSAL


def test_global_qualifier_still_hedges():
    ir = DeterministicClaimParser.parse("CXCL13+ T cells likely drive macrophage polarization.")
    assert ir.causal_strength == CausalStrength.HYPOTHESIZED_CAUSAL


# ---------------------------------------------------------------------------
# P3. Plural passive voice.
# ---------------------------------------------------------------------------


def test_p3_plural_passive_parsed_as_causal():
    ir = DeterministicClaimParser.parse("Macrophage states are driven by tumor-derived CSF1.")
    assert ir.direction.value == "directed_forward"
    assert ir.causal_strength == CausalStrength.COUNTERFACTUAL_CAUSAL
    assert ir.claim_class == ClaimClass.CAUSAL
    assert "CSF1" in ir.subject_entity.name


# ---------------------------------------------------------------------------
# P4. Negated causality: honest disclaimers are never flagged as overclaims.
# ---------------------------------------------------------------------------


def test_p4_negated_causal_statement_downgrades_ir():
    ir = DeterministicClaimParser.parse("IL-6 does not drive T cell exhaustion.")
    assert ir.negated is True
    assert ir.causal_strength == CausalStrength.NONE
    assert ir.claim_class == ClaimClass.DESCRIPTIVE
    assert ir.mechanism_depth.value == "black_box"  # regression guard: downgrade must bind mech_depth


def test_p4_extended_negation_did_not_alter():
    ir = DeterministicClaimParser.parse("Pten knockout did not alter AKT phosphorylation.")
    assert ir.negated is True


def test_p4_verify_does_not_flag_negative_findings():
    ledger = ClaimLedger()
    ledger.add_evidence(
        EvidenceRef("E1", "method_run", "enrichment test", ConclusionMaturity.SUPPORTED.value)
    )
    ledger.add_claim(
        ClaimRecord(
            claim_id="C-NEG",
            statement="Our data provide no evidence that CXCL13 induces fibrosis",
            supported_by=["E1"],
        )
    )
    report = verify_ledger(ledger)
    assert report.passed, report.to_dict()


def test_p4_detector_skips_scoped_negation_but_flags_assertions():
    assert detect_assertive_causal_language("IL-6 does not drive exhaustion") is None
    assert detect_assertive_causal_language("cannot prove that drug caused the DEGs") is None
    assert detect_assertive_causal_language("CXCL13+ T cells drive tumor progression") == "drive"
    assert (
        detect_assertive_causal_language("we propose a mechanism of action") == "mechanism of action"
    )


# ---------------------------------------------------------------------------
# P5. Population scope stopword guard.
# ---------------------------------------------------------------------------


def test_p5_stopword_phrase_yields_empty_population_scope():
    ir = DeterministicClaimParser.parse("In this study, Tregs suppress effector cytokines.")
    assert ir.population_scope == ""
    assert ir.generalization_scope == GeneralizationScope.COHORT_SPECIFIC
    assert ir.causal_strength == CausalStrength.COUNTERFACTUAL_CAUSAL


def test_flagship_regression_scope_still_extracted():
    ir = DeterministicClaimParser.parse(
        "CXCL13+ CD8 T cells drive macrophage polarization in NSCLC."
    )
    assert ir.population_scope == "NSCLC"
    assert ir.causal_strength == CausalStrength.COUNTERFACTUAL_CAUSAL
