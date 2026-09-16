"""
BioNexus Air-Gapped Local Knowledge Cache & Offline MCP Accelerator.

Provides zero-latency, offline-capable embedded biomedical knowledge lookup
(HGNC/Ensembl gene symbols, cell-type markers, Reactome pathways, PDB entries)
ensuring high performance and total compliance with air-gapped HPC and secure lab policies.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

# Canonical offline high-frequency human genes with Ensembl/UniProt mappings
CANONICAL_GENE_CATALOG: List[Dict[str, Any]] = [
    {
        "symbol": "TP53",
        "name": "tumor protein p53",
        "ensembl_id": "ENSG00000141510",
        "uniprot_id": "P04637",
        "chromosome": "17",
        "synonyms": ["p53", "LFS1", "TRP53"],
        "summary": "Acts as a tumor suppressor in many tumor types; induces growth arrest or apoptosis.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "EGFR",
        "name": "epidermal growth factor receptor",
        "ensembl_id": "ENSG00000146648",
        "uniprot_id": "P00533",
        "chromosome": "7",
        "synonyms": ["ERBB", "ERBB1", "HER1"],
        "summary": "Receptor tyrosine kinase binding ligands of the EGF family and activating several signaling cascades.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "CD4",
        "name": "CD4 molecule",
        "ensembl_id": "ENSG00000010610",
        "uniprot_id": "P01730",
        "chromosome": "12",
        "synonyms": ["CD4mut", "T4"],
        "summary": "Integral membrane glycoprotein that acts as a coreceptor for MHC class II antigen receptors.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "CD8A",
        "name": "CD8a molecule",
        "ensembl_id": "ENSG00000153563",
        "uniprot_id": "P01732",
        "chromosome": "2",
        "synonyms": ["CD8", "MAL", "p32"],
        "summary": "Cell surface glycoprotein found on most cytotoxic T lymphocytes that mediates efficient cell-cell interactions.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "CD8B",
        "name": "CD8b molecule",
        "ensembl_id": "ENSG00000172116",
        "uniprot_id": "P10966",
        "chromosome": "2",
        "synonyms": ["CD8B1", "LEU2"],
        "summary": "Forms a heterodimer with CD8A on cytotoxic T cells.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "CD3D",
        "name": "CD3d molecule",
        "ensembl_id": "ENSG00000167286",
        "uniprot_id": "P04234",
        "chromosome": "11",
        "synonyms": ["CD3-DELTA", "T3D"],
        "summary": "Part of the T-cell receptor/CD3 complex involved in antigen recognition and signal transduction.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "CD3E",
        "name": "CD3e molecule",
        "ensembl_id": "ENSG00000198851",
        "uniprot_id": "P07766",
        "chromosome": "11",
        "synonyms": ["CD3-epsilon", "T3E"],
        "summary": "T-cell surface glycoprotein CD3 epsilon chain.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "MS4A1",
        "name": "membrane spanning 4-domains A1",
        "ensembl_id": "ENSG00000156738",
        "uniprot_id": "P11836",
        "chromosome": "11",
        "synonyms": ["CD20", "B1", "Bp35"],
        "summary": "B-lymphocyte antigen CD20, a specific marker for mature B cells.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "CD19",
        "name": "CD19 molecule",
        "ensembl_id": "ENSG00000177455",
        "uniprot_id": "P15391",
        "chromosome": "16",
        "synonyms": ["B4", "CVID3"],
        "summary": "Crucial B-cell surface receptor assembling with CD21 and CD81 to form antigen receptor complex.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "NCAM1",
        "name": "neural cell adhesion molecule 1",
        "ensembl_id": "ENSG00000149294",
        "uniprot_id": "P13591",
        "chromosome": "11",
        "synonyms": ["CD56", "MSK39", "NCAM"],
        "summary": "Canonical marker for human Natural Killer (NK) cells and neuroendocrine cells.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "FOXP3",
        "name": "forkhead box P3",
        "ensembl_id": "ENSG00000049768",
        "uniprot_id": "Q9BZS1",
        "chromosome": "X",
        "synonyms": ["IPEX", "JM2", "SCIDXP1"],
        "summary": "Master transcription factor governing regulatory T cell (Treg) development and function.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "TNF",
        "name": "tumor necrosis factor",
        "ensembl_id": "ENSG00000232810",
        "uniprot_id": "P01375",
        "chromosome": "6",
        "synonyms": ["TNFA", "TNF-alpha", "DIF"],
        "summary": "Cytokine involved in systemic inflammation and member of a group of cytokines that stimulate acute phase reaction.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "IL6",
        "name": "interleukin 6",
        "ensembl_id": "ENSG00000136244",
        "uniprot_id": "P05231",
        "chromosome": "7",
        "synonyms": ["IFNB2", "BSF2", "HGF"],
        "summary": "Cytokine functioning in inflammation and the maturation of B cells.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "MKI67",
        "name": "marker of proliferation Ki-67",
        "ensembl_id": "ENSG00000148773",
        "uniprot_id": "P46013",
        "chromosome": "10",
        "synonyms": ["KIA", "Ki-67"],
        "summary": "Nuclear protein associated with and necessary for cellular proliferation.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "GAPDH",
        "name": "glyceraldehyde-3-phosphate dehydrogenase",
        "ensembl_id": "ENSG00000111640",
        "uniprot_id": "P04406",
        "chromosome": "12",
        "synonyms": ["G3PD", "GAPD"],
        "summary": "Enzyme of glycolysis and widely used housekeeping reference gene.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "ACTB",
        "name": "actin beta",
        "ensembl_id": "ENSG00000075624",
        "uniprot_id": "P60709",
        "chromosome": "7",
        "synonyms": ["BRWS1", "PS1TP5BP1"],
        "summary": "Major constituent of the contractile apparatus and ubiquitous cytoskeletal protein.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "BRAF",
        "name": "B-Raf proto-oncogene, serine/threonine kinase",
        "ensembl_id": "ENSG00000157764",
        "uniprot_id": "P15056",
        "chromosome": "7",
        "synonyms": ["BRAF1", "RAFB1"],
        "summary": "Kinase in the MAP kinase / ERKs signaling pathway affecting cell division and differentiation.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "KRAS",
        "name": "KRAS proto-oncogene, GTPase",
        "ensembl_id": "ENSG00000133703",
        "uniprot_id": "P01116",
        "chromosome": "12",
        "synonyms": ["C-K-RAS", "K-RAS2A", "K-RAS4B"],
        "summary": "Small GTPase cycling between active GTP-bound and inactive GDP-bound states.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "BRCA1",
        "name": "BRCA1 DNA repair associated",
        "ensembl_id": "ENSG00000012048",
        "uniprot_id": "P38398",
        "chromosome": "17",
        "synonyms": ["BRCAI", "BRCC1", "FANCS"],
        "summary": "Nuclear phosphoprotein that plays a role in maintaining genomic stability and DNA double-strand break repair.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "PDCD1",
        "name": "programmed cell death 1",
        "ensembl_id": "ENSG00000188389",
        "uniprot_id": "Q15116",
        "chromosome": "2",
        "synonyms": ["PD1", "CD279", "SLEB2"],
        "summary": "Immune-checkpoint receptor expressed on activated T cells, B cells, and myeloid cells.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "CD274",
        "name": "CD274 molecule",
        "ensembl_id": "ENSG00000120217",
        "uniprot_id": "Q9NZQ7",
        "chromosome": "9",
        "synonyms": ["PD-L1", "PDL1", "B7-H1"],
        "summary": "Programmed cell death 1 ligand 1 that binds PDCD1 to inhibit T cell activation.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "PECAM1",
        "name": "platelet and endothelial cell adhesion molecule 1",
        "ensembl_id": "ENSG00000140265",
        "uniprot_id": "P16284",
        "chromosome": "17",
        "synonyms": ["CD31", "endoCAM"],
        "summary": "Adhesion molecule on endothelial cells and platelets.",
        "species": "Homo sapiens",
    },
    {
        "symbol": "EPCAM",
        "name": "epithelial cell adhesion molecule",
        "ensembl_id": "ENSG00000119888",
        "uniprot_id": "P16422",
        "chromosome": "2",
        "synonyms": ["CD326", "EGP", "TROP1"],
        "summary": "Pan-epithelial differentiation antigen and diagnostic marker for epithelial tumors.",
        "species": "Homo sapiens",
    },
]

# Canonical cell-type marker catalog (CellMarker 2.0 / PanglaoDB derived)
CANONICAL_CELL_MARKERS: Dict[str, List[str]] = {
    "T cell": ["CD3D", "CD3E", "CD3G", "TRAC"],
    "CD4+ T cell": ["CD4", "CD3D", "CD3E", "IL7R"],
    "CD8+ T cell": ["CD8A", "CD8B", "CD3D", "CD3E", "GZMB", "PRF1"],
    "Treg": ["FOXP3", "IL2RA", "CD4", "IKZF2"],
    "B cell": ["CD19", "MS4A1", "CD79A", "CD79B", "BANK1"],
    "Plasma cell": ["SDC1", "MZB1", "JCHAIN", "IGHG1"],
    "NK cell": ["NCAM1", "KLRD1", "NKG7", "GNLY"],
    "Monocyte": ["CD14", "FCGR3A", "CSF1R", "LYZ"],
    "Macrophage": ["CD68", "MARCO", "MSR1", "MRC1", "ITGAM"],
    "Dendritic cell": ["ITGAX", "HLA-DRA", "CD1C", "CLEC9A"],
    "Endothelial cell": ["PECAM1", "VWF", "CDH5", "KDR"],
    "Epithelial cell": ["EPCAM", "KRT8", "KRT18", "KRT19"],
    "Fibroblast": ["COL1A1", "COL1A2", "DCN", "ACTA2"],
    "Neutrophil": ["S100A8", "S100A9", "FCGR3B"],
    "Erythrocyte": ["HBA1", "HBA2", "HBB"],
}

# Canonical Reactome core pathways
CANONICAL_REACTOME_PATHWAYS: List[Dict[str, Any]] = [
    {
        "stId": "R-HSA-1640170",
        "name": "Cell Cycle",
        "species": "Homo sapiens",
        "genes": ["TP53", "MKI67", "CDK1", "CDK2", "CCNA2", "CCNB1"],
    },
    {
        "stId": "R-HSA-69620",
        "name": "Cell Cycle Checkpoints",
        "species": "Homo sapiens",
        "genes": ["TP53", "ATM", "ATR", "CHEK1", "CHEK2", "MDM2"],
    },
    {
        "stId": "R-HSA-1280215",
        "name": "Cytokine Signaling in Immune system",
        "species": "Homo sapiens",
        "genes": ["IL6", "TNF", "IFNG", "IL2", "JAK1", "STAT3"],
    },
    {
        "stId": "R-HSA-5663202",
        "name": "Diseases of signal transduction by growth factor receptors",
        "species": "Homo sapiens",
        "genes": ["EGFR", "BRAF", "KRAS", "PIK3CA", "PTEN"],
    },
    {
        "stId": "R-HSA-109581",
        "name": "Apoptosis",
        "species": "Homo sapiens",
        "genes": ["TP53", "BAX", "BCL2", "CASP3", "CASP8", "CASP9"],
    },
    {
        "stId": "R-HSA-389948",
        "name": "PD-1 signaling",
        "species": "Homo sapiens",
        "genes": ["PDCD1", "CD274", "PTPN11", "LCK", "ZAP70"],
    },
]

# Canonical PDB entries
CANONICAL_PDB_STRUCTURES: Dict[str, Dict[str, Any]] = {
    "P04637": {"pdb_id": "1TUP", "title": "Tumor suppressor p53 complexed with DNA", "resolution": 2.2},
    "P00533": {"pdb_id": "1IVO", "title": "EGFR extracellular domain in complex with EGF", "resolution": 2.8},
    "P01116": {"pdb_id": "4OBE", "title": "KRAS G12D with small molecule inhibitor", "resolution": 1.95},
    "P15056": {"pdb_id": "4MNE", "title": "BRAF kinase domain V600E mutant", "resolution": 2.4},
    "Q15116": {"pdb_id": "4ZQK", "title": "Structure of human PD-1 in complex with PD-L1", "resolution": 2.45},
}


class BioLocalCache:
    """Embedded SQLite & In-Memory Local Knowledge Base with Zero-Egress Support."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None) -> None:
        self._db_path = str(db_path) if db_path else ":memory:"
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        self._populate_canonical_data()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS kv_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    ttl_seconds REAL
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS genes (
                    symbol TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    ensembl_id TEXT NOT NULL,
                    uniprot_id TEXT NOT NULL,
                    chromosome TEXT,
                    synonyms_json TEXT,
                    summary TEXT,
                    species TEXT
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS cell_markers (
                    cell_type TEXT NOT NULL,
                    marker_symbol TEXT NOT NULL,
                    PRIMARY KEY (cell_type, marker_symbol)
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS pathways (
                    st_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    species TEXT,
                    genes_json TEXT
                )
            """)

    def _populate_canonical_data(self) -> None:
        with self._conn:
            # Populate genes
            for g in CANONICAL_GENE_CATALOG:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO genes (symbol, name, ensembl_id, uniprot_id, chromosome, synonyms_json, summary, species)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        g["symbol"],
                        g["name"],
                        g["ensembl_id"],
                        g["uniprot_id"],
                        g["chromosome"],
                        json.dumps(g["synonyms"]),
                        g["summary"],
                        g["species"],
                    ),
                )

            # Populate cell markers
            for ct, markers in CANONICAL_CELL_MARKERS.items():
                for m in markers:
                    self._conn.execute(
                        "INSERT OR REPLACE INTO cell_markers (cell_type, marker_symbol) VALUES (?, ?)",
                        (ct, m),
                    )

            # Populate pathways
            for p in CANONICAL_REACTOME_PATHWAYS:
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO pathways (st_id, name, species, genes_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (p["stId"], p["name"], p["species"], json.dumps(p["genes"])),
                )

    def get_gene(self, query: str) -> Optional[Dict[str, Any]]:
        """Query gene by exact symbol, synonym, Ensembl ID, or UniProt ID."""
        q_upper = query.strip().upper()
        cursor = self._conn.cursor()

        # 1. Exact symbol
        cursor.execute("SELECT * FROM genes WHERE UPPER(symbol) = ?", (q_upper,))
        row = cursor.fetchone()
        if row:
            return self._row_to_gene(row)

        # 2. Exact Ensembl or UniProt ID
        cursor.execute(
            "SELECT * FROM genes WHERE UPPER(ensembl_id) = ? OR UPPER(uniprot_id) = ?",
            (q_upper, q_upper),
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_gene(row)

        # 3. Synonym search
        cursor.execute("SELECT * FROM genes")
        for r in cursor.fetchall():
            syns = [s.upper() for s in json.loads(r["synonyms_json"] or "[]")]
            if q_upper in syns:
                return self._row_to_gene(r)

        return None

    def _row_to_gene(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "symbol": row["symbol"],
            "name": row["name"],
            "ensembl_id": row["ensembl_id"],
            "uniprot_id": row["uniprot_id"],
            "chromosome": row["chromosome"],
            "synonyms": json.loads(row["synonyms_json"] or "[]"),
            "summary": row["summary"],
            "species": row["species"],
            "source": "BioNexusLocalCache",
        }

    def get_markers(self, cell_type: str) -> List[str]:
        """Retrieve canonical gene markers for a given cell type."""
        ct_query = cell_type.strip().lower()
        cursor = self._conn.cursor()
        cursor.execute("SELECT DISTINCT cell_type FROM cell_markers")
        matching_types = [
            r["cell_type"]
            for r in cursor.fetchall()
            if ct_query in r["cell_type"].lower() or r["cell_type"].lower() in ct_query
        ]

        markers: Set[str] = set()
        for ct in matching_types:
            cursor.execute("SELECT marker_symbol FROM cell_markers WHERE cell_type = ?", (ct,))
            for r in cursor.fetchall():
                markers.add(r["marker_symbol"])

        return sorted(markers)

    def get_pathways_for_gene(self, gene_symbol: str) -> List[Dict[str, Any]]:
        """Find Reactome pathways involving the specified gene symbol."""
        g_upper = gene_symbol.strip().upper()
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM pathways")
        results: List[Dict[str, Any]] = []

        for row in cursor.fetchall():
            genes = [g.upper() for g in json.loads(row["genes_json"] or "[]")]
            if g_upper in genes:
                results.append({
                    "stId": row["st_id"],
                    "name": row["name"],
                    "species": row["species"],
                    "source": "BioNexusLocalCache",
                })

        return results

    def get_pdb_summary(self, uniprot_or_symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieve canonical 3D PDB structure metadata for a protein."""
        gene = self.get_gene(uniprot_or_symbol)
        uniprot_id = gene["uniprot_id"] if gene else uniprot_or_symbol.strip().upper()
        struct = CANONICAL_PDB_STRUCTURES.get(uniprot_id)
        if struct:
            res = dict(struct)
            res["uniprot_id"] = uniprot_id
            res["source"] = "BioNexusLocalCache"
            return res
        return None

    def get_kv(self, key: str) -> Optional[Any]:
        """Retrieve a cached object by key if not expired."""
        cursor = self._conn.cursor()
        cursor.execute("SELECT payload, created_at, ttl_seconds FROM kv_cache WHERE cache_key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            return None

        created_at = row["created_at"]
        ttl = row["ttl_seconds"]
        if ttl is not None and (time.time() - created_at) > ttl:
            with self._conn:
                self._conn.execute("DELETE FROM kv_cache WHERE cache_key = ?", (key,))
            return None

        try:
            return json.loads(row["payload"])
        except Exception:
            return row["payload"]

    def set_kv(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        """Save a key-value pair to persistent local cache."""
        payload_str = json.dumps(value) if not isinstance(value, str) else value
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO kv_cache (cache_key, payload, created_at, ttl_seconds)
                VALUES (?, ?, ?, ?)
                """,
                (key, payload_str, time.time(), ttl_seconds),
            )

    @staticmethod
    def is_offline_mode() -> bool:
        """Check whether system is operating in air-gapped or offline mode."""
        return os.environ.get("BIONEXUS_OFFLINE", "0") in ("1", "true", "TRUE", "yes")


# Global default local cache instance
default_local_cache = BioLocalCache()
