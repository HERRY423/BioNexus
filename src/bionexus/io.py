"""Minimal cross-skill I/O helpers for FASTA, simple VCF lines, AnnData, and PDB."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

PathLike = Union[str, Path]


def read_fasta(path: PathLike) -> Dict[str, str]:
    """Read a FASTA file into {header: sequence} (headers without '>')."""
    records: Dict[str, List[str]] = {}
    current: Optional[str] = None
    text = Path(path).read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(">"):
            current = line[1:].split()[0]
            records[current] = []
        elif current is not None:
            records[current].append(line.upper())
    return {k: "".join(v) for k, v in records.items()}


def write_fasta(path: PathLike, records: Dict[str, str]) -> None:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    for header, seq in records.items():
        lines.append(f">{header}")
        for i in range(0, len(seq), 80):
            lines.append(seq[i : i + 80])
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_simple_vcf_line(line: str) -> Optional[Tuple[str, int, str, str]]:
    """Parse CHROM POS REF ALT from a non-header VCF line. Returns None for headers."""
    raw = line.strip()
    if not raw or raw.startswith("#"):
        return None
    parts = raw.split("\t") if "\t" in raw else raw.split()
    if len(parts) < 5:
        raise ValueError(f"Not a VCF variant line: {line!r}")
    chrom, pos_s, _vid, ref, alt = parts[:5]
    return chrom, int(pos_s), ref.upper(), alt.split(",")[0].upper()


def read_h5ad(path: PathLike):
    """Load AnnData; requires the scverse extra."""
    try:
        import anndata as ad
    except ImportError as exc:
        raise ImportError("Reading .h5ad requires anndata. pip install 'bionexus[scverse]'") from exc
    return ad.read_h5ad(str(path))


def write_h5ad(adata, path: PathLike) -> None:
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(str(dest))


def parse_pdb_ca_atoms(pdb_text: str) -> Tuple[List[str], "object"]:
    """Parse CA atoms from PDB text. Returns (sequence, Nx3 float array)."""
    import numpy as np

    seq: List[str] = []
    coords: List[List[float]] = []
    three_to_one = {
        "ALA": "A", "CYS": "C", "ASP": "D", "GLU": "E", "PHE": "F",
        "GLY": "G", "HIS": "H", "ILE": "I", "LYS": "K", "LEU": "L",
        "MET": "M", "ASN": "N", "PRO": "P", "GLN": "Q", "ARG": "R",
        "SER": "S", "THR": "T", "VAL": "V", "TRP": "W", "TYR": "Y",
    }
    for line in pdb_text.splitlines():
        if not line.startswith("ATOM"):
            continue
        if line[12:16].strip() != "CA":
            continue
        res = line[17:20].strip()
        seq.append(three_to_one.get(res, "X"))
        coords.append([float(line[30:38]), float(line[38:46]), float(line[46:54])])
    return seq, np.asarray(coords, dtype=float)
