"""
Unit and Adversarial Benchmark Tests for Claim Semantics and Warrant Engine.

Evaluates adversarial paraphrasing, passive voice, periphrastic causality,
metaphorical drivers, Chinese causal rewrites, and HybridClaimParser fail-closed semantics.
"""


from bionexus.claim_semantics import (
    ClaimClass,
    DeterministicWarrantEngine,
    Directionality,
    EvidenceProfile,
    HybridClaimParser,
    ScientificClaimParser,
)

ADVERSARIAL_CAUSAL_VARIANTS = [
    # 1. Periphrastic causality / Verbal phrases
    "CXCL13+ CD8 T cells are pivotal in shaping macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells play an indispensable role in driving macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells act as a master regulator of macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells serve as the primary engine for macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells function as the master switch for macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells exert control over macrophage polarization in NSCLC",
    # 2. Passive voice causal constructions
    "Macrophage polarization in NSCLC is driven by CXCL13+ CD8 T cells",
    "Macrophage polarization is orchestrated by CXCL13+ CD8 T cells in NSCLC",
    "Macrophage polarization is dictated by CXCL13+ CD8 T cells in NSCLC tumors",
    "Macrophage polarization is governed by CXCL13+ CD8 T cells in NSCLC",
    "Macrophage polarization is steered by CXCL13+ CD8 T cells in NSCLC",
    "Macrophage polarization is shaped by CXCL13+ CD8 T cells in NSCLC",
    # 3. Metaphorical / Action drivers
    "CXCL13+ CD8 T cells fuel macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells steer macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells remodel macrophage phenotype in NSCLC",
    "CXCL13+ CD8 T cells instigate macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells orchestrate macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells dictate macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells trigger macrophage polarization in NSCLC",
    # 4. Culprit / Attribution nouns
    "CXCL13+ CD8 T cells are the culprit behind macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells are responsible for macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells are the primary cause of macrophage polarization in NSCLC",
    "CXCL13+ CD8 T cells are the master switch behind macrophage differentiation in NSCLC",
    # 5. Chinese paraphrastic / passive / metaphorical causal rewrites
    "CXCL13+ CD8 T细胞重塑NSCLC中巨噬细胞表型",
    "CXCL13+ CD8 T细胞是NSCLC中巨噬细胞极化的主要推手",
    "NSCLC中巨噬细胞极化由CXCL13+ CD8 T细胞介导",
    "CXCL13+ CD8 T细胞在NSCLC巨噬细胞极化中起决定性作用",
    "CXCL13+ CD8 T细胞主导NSCLC巨噬细胞极化",
]


def test_adversarial_evasion_zero_escapes_to_descriptive():
    """
    Every adversarial variant must be recognized as CAUSAL or MECHANISTIC.
    Zero causal assertions are permitted to slip through as DESCRIPTIVE.
    """
    escaped_to_descriptive = []

    for text in ADVERSARIAL_CAUSAL_VARIANTS:
        ir = ScientificClaimParser.parse(text)
        if ir.claim_class not in (ClaimClass.CAUSAL, ClaimClass.MECHANISTIC):
            escaped_to_descriptive.append((text, ir.claim_class.value))

    assert (
        len(escaped_to_descriptive) == 0
    ), f"The following causal assertions evaded detection and escaped to non-causal classes:\n{escaped_to_descriptive}"


def test_adversarial_variants_rejected_under_observational_data():
    """
    When provided only with observational/spatial colocalization facts (no perturbation),
    every adversarial variant MUST fail warrant evaluation with is_fully_warranted=False.
    """
    spatial_facts = EvidenceProfile(
        observational_data=True,
        spatial_colocalization=True,
        ligand_receptor_inference=True,
        perturbation=False,  # NO perturbation
        biological_replicates_count=20,
        confound_controls=["donor", "sample"],
    )

    for text in ADVERSARIAL_CAUSAL_VARIANTS:
        ir = ScientificClaimParser.parse(text)
        verdict = DeterministicWarrantEngine.evaluate(ir, spatial_facts)

        assert not verdict.is_fully_warranted, (
            f"Adversarial variant '{text}' was improperly approved without perturbation! "
            f"Verdict: {verdict.to_dict()}"
        )

        # Causal or mechanistic tier must be explicitly un-warranted
        tier_statuses = {name: v.is_warranted for name, v in verdict.tier_verdicts.items()}
        assert not tier_statuses.get("causal_claim", True) or not tier_statuses.get(
            "mechanistic_claim", True
        ), f"Causal or mechanistic tier was falsely granted for '{text}'"


def test_adversarial_variants_approved_with_functional_perturbation():
    """
    When backed by valid empirical functional perturbation and replicates,
    the causal claim can be warranted.
    """
    perturbation_facts = EvidenceProfile(
        observational_data=True,
        spatial_colocalization=True,
        ligand_receptor_inference=True,
        perturbation=True,
        temporal_evidence=True,
        biological_replicates_count=5,
        pseudobulk_aggregated=True,
        independent_validation=True,
    )

    text = "CXCL13+ CD8 T cells are pivotal in shaping macrophage polarization in NSCLC"
    ir = ScientificClaimParser.parse(text)
    verdict = DeterministicWarrantEngine.evaluate(ir, perturbation_facts)

    assert verdict.is_fully_warranted, f"Perturbation evidence failed to warrant claim: {verdict.to_dict()}"
    tier_map = {name: v.is_warranted for name, v in verdict.tier_verdicts.items()}
    assert tier_map["causal_claim"] is True
    assert tier_map["mechanistic_claim"] is True


def test_passive_voice_entity_resolution():
    """Verify that passive voice correctly maps grammatical object to semantic subject."""
    text = "Macrophage polarization is orchestrated by CXCL13+ CD8 T cells in NSCLC"
    ir = ScientificClaimParser.parse(text)

    assert ir.direction == Directionality.DIRECTED_FORWARD
    assert "CD8" in ir.subject_entity.name
    assert "macrophage" in ir.object_entity.name.lower()
    assert ir.population_scope.upper() == "NSCLC"


def test_fail_closed_adversarial_shield_metadata():
    """Test that adversarial evasion detection is clearly recorded in metadata."""
    text = "CXCL13+ CD8 T cells are the mastermind behind macrophage exhaustion in NSCLC"
    ir = ScientificClaimParser.parse(text)

    assert ir.claim_class in (ClaimClass.CAUSAL, ClaimClass.MECHANISTIC)
    assert ir.metadata.get("adversarial_evasion_detected") is True
    assert "fail-closed" in ir.metadata.get("evasion_shield_rationale", "").lower()


def test_hybrid_claim_parser_mock_llm():
    """Test HybridClaimParser with a mock LLM extractor."""
    def mock_llm_extractor(text: str):
        return {
            "claim_class": "CAUSAL",
            "subject": "CXCL13+ CD8 T cells",
            "object": "macrophage polarization",
            "is_causal": True,
        }

    parser = HybridClaimParser(llm_extractor=mock_llm_extractor, fail_closed=True)
    ir = parser.parse("Some obscure non-standard causal phrasing between CXCL13+ CD8 T cells and macrophage polarization")

    assert ir.claim_class in (ClaimClass.CAUSAL, ClaimClass.MECHANISTIC)
    assert ir.metadata.get("llm_extracted") is True
    assert ir.metadata["llm_raw_output"]["is_causal"] is True


def test_hybrid_claim_parser_fail_closed_prevents_downgrade():
    """
    Even if an LLM is hallucinating and claims an asserted causal statement is DESCRIPTIVE,
    the fail-closed policy forbids downgrading below what the adversarial rule shield caught.
    """
    def buggy_llm_extractor(text: str):
        return {
            "claim_class": "DESCRIPTIVE",
            "is_causal": False,
        }

    parser = HybridClaimParser(llm_extractor=buggy_llm_extractor, fail_closed=True)
    ir = parser.parse("CXCL13+ CD8 T cells drive macrophage polarization in NSCLC")

    # Must stay CAUSAL or MECHANISTIC due to fail-closed reconciliation
    assert ir.claim_class in (ClaimClass.CAUSAL, ClaimClass.MECHANISTIC)
