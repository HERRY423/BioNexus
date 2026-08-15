"""Small golden cases that fail if the science contract is gutted."""

from __future__ import annotations

from pathlib import Path
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "biologics-design" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "clinical-cohort-analysis" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "variant-interpretation" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "spatial-transcriptomics" / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "skills" / "protein-structure-analysis" / "scripts"))

from antibody_annotator import annotate_variable_domain_imgt, detect_chain_type
from survival_analyzer import compute_kaplan_meier, log_rank_test
from acmg_classifier import classify_acmg_deterministic, compute_bayesian_pathogenicity
from spatial_variable_genes import calculate_morans_i_vectorized, compute_spatial_weights_matrix
from structural_alignment import kabsch_superposition


HERCEPTIN_VH = "EVQLVESGGGLVQPGGSLRLSCAASGFNIKDTYIHWVRQAPGKGLEWVARIYPTNGYTRYADSVKGRFTISADTSKNTAYLQMNSLRAEDTAVYYCSRWGGDGFYAMDYWGQGTLVTVSS"
HERCEPTIN_VL = "DIQMTQSPSSLSASVGDRVTITCRASQDVNTAVAWYQQKPGKAPKLLIYSASFLYSGVPSRFSGSRSGTDFTLTISSLQPEDFATYYCQQHYTTPPTFGQGTKVEIK"


def test_herceptin_chain_and_cdr3_present():
    assert detect_chain_type(HERCEPTIN_VH) == "Heavy"
    assert detect_chain_type(HERCEPTIN_VL) == "Light"
    heavy = annotate_variable_domain_imgt(HERCEPTIN_VH)
    assert heavy["is_valid_fv"]
    assert len(heavy["cdr3_sequence"]) >= 8
    assert "WGGDGFYAMDY" in heavy["full_sequence"]
    assert heavy["method"] in {"abnumber_imgt", "regex_cys_trp_anchors"}


def test_km_is_monotone_and_starts_at_one():
    times = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
    events = np.array([1, 1, 0, 1, 0])
    km_times, km_probs, median = compute_kaplan_meier(times, events)
    assert km_probs[0] == 1.0
    assert np.all(np.diff(km_probs) <= 1e-12)
    assert median > 0
    chi2, pval = log_rank_test(times, events, times + 5, events)
    assert 0.0 <= pval <= 1.0
    assert chi2 >= 0.0


def test_acmg_combination_table():
    label, _ = classify_acmg_deterministic({"PVS1", "PM2", "PP3"})
    assert label == "Pathogenic"
    label_b, _ = classify_acmg_deterministic({"BA1"})
    assert label_b == "Benign"
    post, odds, tier = compute_bayesian_pathogenicity(set())
    assert abs(post - 0.10) < 1e-9
    assert odds == 1.0
    assert tier == "Uncertain Significance"


def test_planted_spatial_pattern_has_high_moran():
    coords = np.array([(i % 10, i // 10) for i in range(100)], dtype=float)
    expr = np.zeros((100, 2))
    expr[:, 0] = (coords[:, 0] < 5).astype(float) * 10.0
    expr[:, 1] = np.random.default_rng(0).normal(size=100)
    weights = compute_spatial_weights_matrix(coords, n_neighbors=4)
    i_scores, _, _ = calculate_morans_i_vectorized(expr, weights)
    assert i_scores[0] > 0.3
    assert i_scores[0] > i_scores[1]


def test_kabsch_recovers_translation():
    rng = np.random.default_rng(1)
    mobile = rng.normal(size=(20, 3))
    target = mobile + np.array([3.0, -2.0, 1.5])
    _aligned, _rot, rmsd = kabsch_superposition(mobile, target)
    assert rmsd < 0.2
