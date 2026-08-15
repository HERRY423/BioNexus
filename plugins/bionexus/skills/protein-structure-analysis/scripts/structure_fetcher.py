#!/usr/bin/env python3
"""
Macromolecular Structure Fetcher & PDB/CIF Coordinate Parser.
Downloads experimental structures from RCSB PDB and AI predictions from AlphaFold DB;
parses atom coordinates, extracts CA backbones, and extracts per-residue pLDDT/B-factors.
"""

import argparse
import logging
import os
import sys
import urllib.request
from typing import Any, Dict, Optional

import numpy as np

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("StructureFetcher")


def parse_pdb_text(pdb_text: str) -> Dict[str, Any]:
    """
    Parse standard PDB format text into atom records, CA coordinates,
    residue sequence, and per-residue B-factors / pLDDT scores.
    """
    ca_coords = []
    ca_residues = []
    ca_res_ids = []
    b_factors = []
    hetero_atoms = []

    # Map 3-letter AA to 1-letter
    aa_3to1 = {
        "ALA": "A",
        "CYS": "C",
        "ASP": "D",
        "GLU": "E",
        "PHE": "F",
        "GLY": "G",
        "HIS": "H",
        "ILE": "I",
        "LYS": "K",
        "LEU": "L",
        "MET": "M",
        "ASN": "N",
        "PRO": "P",
        "GLN": "Q",
        "ARG": "R",
        "SER": "S",
        "THR": "T",
        "VAL": "V",
        "TRP": "W",
        "TYR": "Y",
    }

    for line in pdb_text.splitlines():
        record_type = line[:6].strip()
        if record_type == "ATOM":
            atom_name = line[12:16].strip()
            res_name = line[17:20].strip()
            line[21].strip()
            res_seq = int(line[22:26].strip())
            x = float(line[30:38].strip())
            y = float(line[38:46].strip())
            z = float(line[46:54].strip())
            b_factor = float(line[60:66].strip()) if len(line) >= 66 and line[60:66].strip() else 0.0

            if atom_name == "CA":
                ca_coords.append([x, y, z])
                ca_residues.append(aa_3to1.get(res_name, "X"))
                ca_res_ids.append(res_seq)
                b_factors.append(b_factor)

        elif record_type == "HETATM":
            atom_name = line[12:16].strip()
            res_name = line[17:20].strip()
            if res_name not in ("HOH", "WAT"):
                x = float(line[30:38].strip())
                y = float(line[38:46].strip())
                z = float(line[46:54].strip())
                hetero_atoms.append({"atom": atom_name, "residue": res_name, "coords": [x, y, z]})

    coords_arr = np.array(ca_coords, dtype=float) if ca_coords else np.zeros((0, 3))
    b_factors_arr = np.array(b_factors, dtype=float) if b_factors else np.zeros(0)

    return {
        "n_residues": len(ca_residues),
        "sequence": "".join(ca_residues),
        "ca_coordinates": coords_arr,
        "residue_indices": ca_res_ids,
        "b_factors_or_plddt": b_factors_arr,
        "mean_b_factor": float(np.mean(b_factors_arr)) if len(b_factors_arr) > 0 else 0.0,
        "hetero_atoms_count": len(hetero_atoms),
        "bound_ligands": list({h["residue"] for h in hetero_atoms}),
    }


def fetch_structure_pdb(pdb_id: str, save_path: Optional[str] = None) -> Dict[str, Any]:
    """Download and parse 3D structure from RCSB Protein Data Bank."""
    pdb_id_clean = pdb_id.strip().upper()
    url = f"https://files.rcsb.org/download/{pdb_id_clean}.pdb"
    logger.info(f"Fetching PDB structure {pdb_id_clean} from {url}...")

    req = urllib.request.Request(url, headers={"User-Agent": "BioNexus/2.0.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode("utf-8")

    if save_path:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)) or ".", exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)

    parsed = parse_pdb_text(content)
    parsed["source"] = "RCSB_PDB"
    parsed["identifier"] = pdb_id_clean
    return parsed


def fetch_structure_alphafold(uniprot_id: str, save_path: Optional[str] = None) -> Dict[str, Any]:
    """Download and parse AI predicted structure from AlphaFold Protein Structure DB."""
    acc = uniprot_id.strip().upper()
    url = f"https://alphafold.ebi.ac.uk/files/AF-{acc}-F1-model_v4.pdb"
    logger.info(f"Fetching AlphaFold structure for UniProt {acc} from {url}...")

    req = urllib.request.Request(url, headers={"User-Agent": "BioNexus/2.0.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode("utf-8")

    if save_path:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)) or ".", exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            f.write(content)

    parsed = parse_pdb_text(content)
    parsed["source"] = "AlphaFold_DB"
    parsed["identifier"] = acc
    return parsed


def main():
    parser = argparse.ArgumentParser(description="PDB / AlphaFold Structure Fetcher")
    parser.add_argument("--pdb", "-p", help="PDB ID (e.g. '7K43')")
    parser.add_argument("--uniprot", "-u", help="UniProt ID (e.g. 'P04637')")
    parser.add_argument("--out", "-o", help="Output PDB file path")

    args = parser.parse_args()
    if args.pdb:
        data = fetch_structure_pdb(args.pdb, save_path=args.out)
    elif args.uniprot:
        data = fetch_structure_alphafold(args.uniprot, save_path=args.out)
    else:
        logger.error("Must provide either --pdb or --uniprot ID.")
        sys.exit(1)

    logger.info(f"Parsed {data['n_residues']} residues, mean B-factor/pLDDT: {data['mean_b_factor']:.2f}")


if __name__ == "__main__":
    main()
