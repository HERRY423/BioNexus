"""
Unit tests for Protein Structure Analysis & Drug Design suite:
PDB parser, pLDDT confidence analysis, binding pocket detector, Vina docking generator,
Kabsch superposition, TM-score, and target tractability scorer.
"""

import pytest
import numpy as np
from pathlib import Path
import sys

# Add skill script directories to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "skills" / "protein-structure-analysis" / "scripts"))

from structure_fetcher import parse_pdb_text
from structure_analyzer import (
    analyze_plddt_confidence,
    compute_contact_map,
    compute_radius_of_gyration,
    estimate_secondary_structure,
    analyze_protein_structure_full
)
from binding_pocket_detector import detect_binding_pockets_grid
from molecular_docking import (
    generate_vina_grid_box,
    calculate_dissociation_constant,
    parse_vina_log,
    check_lipinski_rule_of_5
)
from structural_alignment import (
    kabsch_superposition,
    compute_tm_score,
    align_two_structures
)
from drugability_scorer import evaluate_target_tractability


# Sample PDB formatted string for a 5-residue helical peptide
SAMPLE_PDB_TEXT = """
ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 88.50           N
ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00 88.50           C
ATOM      3  C   ALA A   1       2.000   1.428   0.000  1.00 88.50           C
ATOM      4  O   ALA A   1       1.250   2.400   0.000  1.00 88.50           O
ATOM      5  N   LEU A   2       3.320   1.500   0.000  1.00 92.10           N
ATOM      6  CA  LEU A   2       4.000   2.800   0.000  1.00 92.10           C
ATOM      7  N   VAL A   3       5.200   2.600   1.200  1.00 78.40           N
ATOM      8  CA  VAL A   3       6.100   3.700   1.500  1.00 78.40           C
ATOM      9  N   PHE A   4       7.000   3.500   2.500  1.00 45.20           N
ATOM     10  CA  PHE A   4       8.000   4.500   3.000  1.00 45.20           C
ATOM     11  N   GLY A   5       9.000   4.200   4.000  1.00 35.00           N
ATOM     12  CA  GLY A   5      10.000   5.200   4.500  1.00 35.00           C
HETATM   13  C1  LIG A 100      12.000   6.000   5.000  1.00 50.00           C
"""


def test_structure_fetcher_pdb_parser():
    """Test PDB text parser extracts CA coordinates, residues, and B-factors."""
    res = parse_pdb_text(SAMPLE_PDB_TEXT)
    assert res["n_residues"] == 5
    assert res["sequence"] == "ALVFG"
    assert res["ca_coordinates"].shape == (5, 3)
    assert len(res["b_factors_or_plddt"]) == 5
    assert res["hetero_atoms_count"] == 1
    assert "LIG" in res["bound_ligands"]


def test_plddt_confidence_analysis():
    """Test AlphaFold pLDDT tier classification."""
    plddt = np.array([95.0, 85.0, 75.0, 60.0, 40.0])
    analysis = analyze_plddt_confidence(plddt)
    assert analysis["mean_plddt"] == 71.0
    assert analysis["percent_very_high"] == 20.0  # 1 / 5
    assert analysis["percent_disordered_very_low"] == 20.0


def test_contact_map_and_radius_of_gyration():
    """Test contact map and compactness calculations."""
    coords = np.array([
        [0.0, 0.0, 0.0],
        [3.8, 0.0, 0.0],
        [7.6, 0.0, 0.0],
        [0.0, 3.8, 0.0],
        [0.0, 0.0, 3.8]
    ])
    dist_mat, contact_map = compute_contact_map(coords, contact_threshold_angstrom=5.0)
    assert dist_mat.shape == (5, 5)
    assert contact_map.shape == (5, 5)
    assert contact_map[0, 1] is True or contact_map[0, 1] == 1  # 3.8 < 5.0

    rg = compute_radius_of_gyration(coords)
    assert rg > 0.0


def test_binding_pocket_detection():
    """Test 3D geometric binding pocket detection."""
    # Create a synthetic hollow sphere/cup structure of 40 atoms
    theta = np.linspace(0, np.pi, 20)
    phi = np.linspace(0, np.pi, 2)
    t_grid, p_grid = np.meshgrid(theta, phi)
    r = 8.0
    x = r * np.sin(t_grid) * np.cos(p_grid)
    y = r * np.sin(t_grid) * np.sin(p_grid)
    z = r * np.cos(t_grid)
    coords = np.vstack([x.ravel(), y.ravel(), z.ravel()]).T

    pockets = detect_binding_pockets_grid(coords, grid_spacing=2.0, min_pocket_points=5)
    assert isinstance(pockets, list)
    if pockets:
        assert "druggability_score" in pockets[0]
        assert "center_coordinates" in pockets[0]


def test_molecular_docking_and_kinetics():
    """Test Vina grid generation, Kd calculation, and Lipinski checks."""
    config_text = generate_vina_grid_box([10.0, 20.0, 30.0], box_size_angstrom=(18.0, 18.0, 18.0))
    assert "center_x = 10.000" in config_text
    assert "size_x = 18.0" in config_text

    # Delta G = -8.5 kcal/mol -> Nanomolar binder
    kd_res = calculate_dissociation_constant(-8.5)
    assert "nM" in kd_res["kd_formatted"] or "uM" in kd_res["kd_formatted"]

    # Lipinski rule of 5 check
    lip_pass = check_lipinski_rule_of_5(molecular_weight=350.0, logp=2.5, hbd=2, hba=4)
    assert lip_pass["is_druglike"] is True
    assert lip_pass["lipinski_violations_count"] == 0


def test_kabsch_superposition_and_tm_score():
    """Test structural rigid-body alignment and TM-score."""
    coords_a = np.array([
        [0.0, 0.0, 0.0],
        [3.8, 0.0, 0.0],
        [7.6, 0.0, 0.0],
        [11.4, 0.0, 0.0],
        [15.2, 0.0, 0.0]
    ])
    # Translated and slightly perturbed copy
    coords_b = coords_a + np.array([5.0, 10.0, -3.0]) + np.random.normal(0, 0.05, coords_a.shape)

    p_rot, R, rmsd = kabsch_superposition(coords_b, coords_a)
    assert rmsd < 0.2  # Should align cleanly back to coords_a
    assert R.shape == (3, 3)

    tm = compute_tm_score(p_rot, coords_a)
    assert tm > 0.85  # Near perfect match


def test_target_tractability_scoring():
    """Test composite druggability and tractability evaluation."""
    sample_pockets = [{
        "pocket_id": 1,
        "druggability_score": 0.82,
        "volume_angstrom3": 550.0
    }]
    tract = evaluate_target_tractability(
        gene_symbol="EGFR",
        pockets=sample_pockets,
        mean_plddt=92.0,
        has_chembl_ligands=True,
        open_targets_score=0.90
    )
    assert tract["composite_tractability_score"] > 0.70
    assert "Tier 1" in tract["tractability_tier"]
    assert len(tract["modality_recommendations"]) >= 1
