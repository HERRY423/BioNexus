"""Kernel contracts and honesty regressions."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "variant-interpretation" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "clinical-cohort-analysis" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "protein-language-models" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "variant-interpretation" / "scripts"))

from acmg_classifier import evaluate_variant_acmg
from clinical_report_generator import generate_clinical_report_markdown
from immune_deconvolution import deconvolve_immune_microenvironment
from plm_fitness_scorer import score_variant_delta_llr
from variant_annotator import (
    annotate_variant_full,
    ingest_external_annotation,
    parse_variant_string,
    propose_acmg_criteria,
)

from bionexus.backends import probe
from bionexus.contracts import GRADE_C, attach_meta, refuse
from bionexus.inventory import SKILLS, get_skill


def test_inventory_covers_seventeen_skills():
    names = {rec["name"] for rec in SKILLS}
    assert "start" in names
    assert "scvi-tools" in names
    assert "variant-interpretation" in names
    assert get_skill("protein-language-models")["grade"] == "refuse"
    assert get_skill("single-cell-rna-qc")["tier"] == "core"


def test_attach_meta_and_refuse():
    wrapped = attach_meta({"x": 1}, method="demo", backend="local", evidence_grade=GRADE_C)
    assert wrapped["method"] == "demo"
    assert wrapped["evidence_grade"] == "C"
    assert wrapped["abstain"] is False
    denied = refuse(method="esm2", reason="weights not loaded")
    assert denied["abstain"] is True
    assert denied["evidence_grade"] == "abstain"


def test_no_default_pm2_or_pp3():
    parsed = parse_variant_string("c.5266dupC")
    codes, rationale = propose_acmg_criteria(parsed, gene_info={"symbol": "BRCA1"})
    assert "PM2" not in codes
    assert "PP3" not in codes
    assert "PVS1" not in codes
    assert "PM2_withheld" in rationale
    assert "PVS1_withheld" in rationale

    full = annotate_variant_full("c.5266dupC", "BRCA1")
    assert "PM2" not in full["proposed_acmg_criteria"]
    assert full["population_genetics"]["gnomad_global_af"] is None


def test_pvs1_requires_lof_mechanism_flag():
    parsed = parse_variant_string("p.Glu1818Ter")
    codes, _ = propose_acmg_criteria(
        parsed, gene_info={"symbol": "BRCA1"}, lof_is_known_mechanism=True
    )
    assert "PVS1" in codes


def test_immune_nnls_refuses_random_signature():
    bulk = np.ones((2, 10))
    with pytest.raises(ValueError, match="signature matrix"):
        deconvolve_immune_microenvironment(bulk, [f"g{i}" for i in range(10)])


def test_blosum_is_not_labeled_esm_or_pp3():
    kras = "MTEYKLVVVGAGGVGKSALTIQLIQNHFVD"
    res = score_variant_delta_llr(kras, "G12D")
    assert res["method"] == "blosum62_substitution"
    assert "esm" not in res["method"]
    assert res["acmg_computational_evidence"] == "abstain"
    assert res["abstain"] is True


def test_research_report_has_no_forged_lab_ids():
    ev = evaluate_variant_acmg("c.5266dupC", "BRCA1", ["PVS1", "PM2", "PP3"])
    md = generate_clinical_report_markdown(ev)
    assert "99D2081423" not in md
    assert "8410291" not in md
    assert "CLIA" in md  # disclaimer that it is NOT CLIA
    assert "not CLIA/CAP" in md.lower() or "not a clinical diagnostic" in md.lower()


def test_backend_probe_smoke():
    status = probe("sklearn")
    assert status.name == "sklearn"
    assert status.available is True


def test_splice_pwm_does_not_assign_acmg():
    sys.path.insert(0, str(PROJECT_ROOT / "skills" / "variant-interpretation" / "scripts"))
    from splice_predictor import predict_splice_disruption

    res = predict_splice_disruption("CAGGTGAGT", "CAGATGAGT", splice_type="donor")
    assert res["acmg_evidence"] == []
    assert res["method"] == "donor_acceptor_pwm_logodds"


def test_provenance_sidecar_disclaims_part11():
    from bionexus.provenance import sidecar

    note = sidecar(activity_name="demo")["compliance_note"]
    assert "21 CFR" in note
    assert "ALCOA+" in note


def test_esm_probe_is_gated():
    status = probe("esm")
    assert status.available is False
    assert "BIONEXUS_ALLOW_ESM" in status.note


def test_vep_like_json_ingest_does_not_invent_codes():
    mapped = ingest_external_annotation({"gene": "TP53", "consequence": "missense"})
    assert "PM2" not in mapped["proposed_acmg_criteria"]
    assert "PP3" not in mapped["proposed_acmg_criteria"]
    mapped2 = ingest_external_annotation(
        {
            "gene": "BRCA1",
            "consequence": "frameshift",
            "gnomad_af": 1e-6,
            "lof_is_known_mechanism": True,
        }
    )
    assert "PVS1" in mapped2["proposed_acmg_criteria"]
    assert "PM2" in mapped2["proposed_acmg_criteria"]
