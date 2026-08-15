"""
Unit tests for Clinical Variant Interpretation suite:
ACMG classification engine, Bayesian posteriors, variant annotation, splice prediction,
population genetics, and pharmacogenomics.
"""

import sys
from pathlib import Path

# Add skill script directories to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "skills" / "variant-interpretation" / "scripts"))

from acmg_classifier import classify_acmg_deterministic, compute_bayesian_pathogenicity, evaluate_variant_acmg
from clinical_report_generator import generate_clinical_report_markdown
from pharmacogenomics import lookup_pharmacogenomics
from population_genetics import evaluate_population_frequencies
from splice_predictor import DONOR_PWM, predict_splice_disruption, score_sequence_pwm
from variant_annotator import parse_variant_string


def test_acmg_deterministic_pathogenic_rules():
    """Test standard ACMG rule combinations for Pathogenic and Likely Pathogenic."""
    # PVS1 + PM2 + PP3 -> Pathogenic
    det_class, reasons = classify_acmg_deterministic({"PVS1", "PM2", "PP3"})
    assert det_class == "Pathogenic"

    # PS1 + PS2 -> Pathogenic (>= 2 Strong)
    det_class2, _ = classify_acmg_deterministic({"PS1", "PS2"})
    assert det_class2 == "Pathogenic"

    # PVS1 + PM1 -> Likely Pathogenic
    det_class3, _ = classify_acmg_deterministic({"PVS1", "PM1"})
    assert det_class3 == "Likely Pathogenic"

    # BA1 -> Benign
    det_class4, _ = classify_acmg_deterministic({"BA1"})
    assert det_class4 == "Benign"

    # Conflicting criteria -> VUS
    det_class5, _ = classify_acmg_deterministic({"PVS1", "BS1"})
    assert det_class5 == "Uncertain Significance"


def test_bayesian_posterior_pathogenicity():
    """Test Tavtigian Bayesian formulation of ACMG evidence."""
    # Strong pathogenic evidence
    post, odds, tier = compute_bayesian_pathogenicity({"PVS1", "PM2", "PP3"})
    assert post >= 0.99
    assert odds > 1000.0
    assert tier == "Pathogenic"

    # Neutral / no evidence
    post_neutral, odds_neutral, tier_neutral = compute_bayesian_pathogenicity(set())
    assert post_neutral == 0.10  # Prior
    assert odds_neutral == 1.0
    assert tier_neutral == "Uncertain Significance"

    # Benign evidence (BA1)
    post_benign, odds_benign, tier_benign = compute_bayesian_pathogenicity({"BA1"})
    assert post_benign < 0.001
    assert tier_benign == "Benign"


def test_variant_string_parsing():
    """Test parsing of genomic VCF, HGVS cDNA, and protein strings."""
    # VCF format
    p1 = parse_variant_string("chr17:41245466:G:A")
    assert p1["format"] == "genomic_vcf"
    assert p1["chrom"] == "17"
    assert p1["pos"] == 41245466

    # cDNA format
    p2 = parse_variant_string("c.5266dupC")
    assert p2["format"] == "hgvs_cdna"
    assert p2["predicted_consequence"] == "frameshift"

    # Protein format
    p3 = parse_variant_string("p.Glu1818Ter")
    assert p3["format"] == "hgvs_protein"
    assert p3["predicted_consequence"] == "nonsense"


def test_splice_site_disruption_prediction():
    """Test in silico 5' donor splice site PWM scoring."""
    # Consensus: CAG|GTGAGT
    wt_score = score_sequence_pwm("CAGGTGAGT", DONOR_PWM)
    mut_score = score_sequence_pwm("CAGATGAGT", DONOR_PWM)  # +1 G>A mutation destroys canonical donor
    assert wt_score > mut_score

    res = predict_splice_disruption("CAGGTGAGT", "CAGATGAGT", splice_type="donor")
    assert res["delta_splice_score"] > 5.0
    assert res["acmg_evidence"] == []
    assert "PVS1" not in "".join(res["acmg_evidence"])


def test_population_genetics_popmax():
    """Test gnomAD subpopulation frequency evaluation."""
    subpops = {
        "nfe": 0.00002,
        "afr": 0.000005,
        "eas": 0.0
    }
    res = evaluate_population_frequencies(subpops)
    assert res["popmax_af"] == 0.00002
    assert "PM2" not in res["activated_acmg_criteria"]

    common_subpops = {"nfe": 0.06, "afr": 0.02}
    res_common = evaluate_population_frequencies(common_subpops)
    assert "BA1" in res_common["activated_acmg_criteria"]


def test_pharmacogenomics_lookup():
    """Test CPIC guideline lookup for DPYD and CYP2C19."""
    dpyd_res = lookup_pharmacogenomics("DPYD", "c.1905+1G>A")
    assert dpyd_res["has_cpic_guideline"] is True
    assert "Fluorouracil" in dpyd_res["drug"]
    assert "5-FU" in dpyd_res["clinical_recommendation"]

    cyp_res = lookup_pharmacogenomics("CYP2C19", "*2")
    assert cyp_res["has_cpic_guideline"] is True
    assert "Clopidogrel" in cyp_res["drug"]


def test_clinical_report_markdown_generation():
    """Test clinical report markdown compilation."""
    eval_res = evaluate_variant_acmg(
        variant_id="c.5266dupC",
        gene_symbol="BRCA1",
        criteria=["PVS1", "PM2", "PP3"]
    )
    md = generate_clinical_report_markdown(eval_res, patient_id="PT-TEST-01")
    assert "# RESEARCH VARIANT INTERPRETATION SUMMARY" in md
    assert "BRCA1" in md
    assert "c.5266dupC" in md
    assert "PATHOGENIC" in md
    assert "CLIA ID" not in md
    assert "CAP Accredited" not in md
