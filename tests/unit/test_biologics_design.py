"""
Unit tests for Biologics & mRNA Design suite:
Antibody Fv/CDR annotation, biophysical developability liability scoring, and mRNA codon/MFE optimization.
"""

import sys
from pathlib import Path

# Add skill script directories to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "skills" / "biologics-design" / "scripts"))

from antibody_annotator import annotate_variable_domain_imgt, detect_chain_type
from antibody_developability import evaluate_antibody_developability
from mrna_engineer import optimize_mrna_sequence

# Trastuzumab (Herceptin) VH Sequence
HERCEPTIN_VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
# Trastuzumab (Herceptin) VL Sequence
HERCEPTIN_VL = (
    "DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVEIK"
)


def test_antibody_chain_detection_and_annotation():
    """Test VH and VL chain classification and IMGT CDR boundary detection."""
    chain_h = detect_chain_type(HERCEPTIN_VH)
    assert chain_h == "Heavy"

    chain_l = detect_chain_type(HERCEPTIN_VL)
    assert chain_l == "Light"

    handle_h = annotate_variable_domain_imgt(HERCEPTIN_VH)
    assert handle_h["is_valid_fv"] is True
    assert handle_h["chain_type"] == "Heavy"
    assert "CDR-H3" in handle_h["regions"]
    assert len(handle_h["cdr3_sequence"]) >= 5

    handle_l = annotate_variable_domain_imgt(HERCEPTIN_VL)
    assert handle_l["is_valid_fv"] is True
    assert handle_l["chain_type"] == "Light"
    assert "CDR-L3" in handle_l["regions"]


def test_antibody_developability_audit():
    """Test developability liability scanning and net charge calculation."""
    handle_h = annotate_variable_domain_imgt(HERCEPTIN_VH)
    dev_res = evaluate_antibody_developability(handle_h, human_germline_identity=0.88)
    assert "developability_tier" in dev_res
    assert dev_res["developability_score"] > 0.60
    assert isinstance(dev_res["liabilities"], list)

    # Synthetic problematic sequence with free Cys and hydrophobic patch in CDR3
    bad_seq = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRLLLLCYYWGQGTLVTVSS"
    handle_bad = annotate_variable_domain_imgt(bad_seq)
    dev_bad = evaluate_antibody_developability(handle_bad)
    liability_types = [liab["type"] for liab in dev_bad["liabilities"]]
    assert "Unpaired Cysteine" in liability_types or "Hydrophobic Patch in CDR3" in liability_types


def test_mrna_therapeutic_optimization():
    """Test human codon optimization, CAI, GC content, and MFE stability calculation."""
    sample_prot = "MTEYKLVVVGAGGVGKSALTIQLIQ"
    res = optimize_mrna_sequence(sample_prot)
    assert "codon_adaptation_index_cai" not in res
    assert res["sharp_li_cai"] is None
    assert 48.0 <= res["gc_content_percent"] <= 70.0
    assert res["estimated_folding_mfe_kcal_mol"] < 0.0
    assert len(res["optimized_mrna_sequence"]) == len(sample_prot) * 3
