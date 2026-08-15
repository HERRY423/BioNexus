"""
Unit tests for Biological Knowledge Subgraph and GraphRAG hypothesis validation.
"""

import os
import shutil
import tempfile
from pathlib import Path

# Add skill script directories to path
SKILL_ROOT = Path(__file__).parent.parent.parent / "skills" / "knowledge-graph-augmentation" / "scripts"
import sys

sys.path.insert(0, str(SKILL_ROOT))

from bio_knowledge_graph import BioKnowledgeGraph
from hypothesis_validator import build_graphrag_context, validate_target_disease_hypothesis


def test_knowledge_graph_ingestion_and_topology():
    """Verify multi-source ingestion from Open Targets, UniProt, and ChEMBL."""
    kg = BioKnowledgeGraph("Oncology Subgraph")

    # Ingest Open Targets hits
    kg.ingest_opentargets_hits(
        "Non-Small Cell Lung Cancer", [{"id": "ENSG00000146648", "name": "EGFR", "entity": "target", "score": 0.94}]
    )

    # Ingest UniProt
    kg.ingest_uniprot_protein(
        {
            "accession": "P00533",
            "protein_name": "Epidermal growth factor receptor",
            "genes": ["EGFR"],
            "organism": "Homo sapiens",
            "function": "Receptor tyrosine kinase binding ligands of the EGF family.",
        }
    )

    # Ingest ChEMBL
    kg.ingest_chembl_molecule(
        "EGFR", {"chembl_id": "CHEMBL3989912", "pref_name": "Osimertinib", "max_phase": 4, "molecular_weight": 499.6}
    )

    stats = kg.get_summary_statistics()
    assert stats["total_nodes"] >= 4
    assert stats["total_edges"] >= 3

    # Check export JSON
    json_data = kg.to_json()
    assert len(json_data["nodes"]) == stats["total_nodes"]


def test_hypothesis_validation_and_graphrag():
    """Verify shortest path finding, topological hypothesis scoring, and GraphRAG context."""
    kg = BioKnowledgeGraph("Path Test Graph")
    kg.add_node("target:braf", "Target", "BRAF")
    kg.add_node("drug:vemurafenib", "Drug", "Vemurafenib")
    kg.add_node("disease:melanoma", "Disease", "Melanoma")

    kg.add_edge("drug:vemurafenib", "target:braf", "INHIBITS", weight=0.9)
    kg.add_edge("target:braf", "disease:melanoma", "ASSOCIATED_WITH", weight=0.95)

    # Validate direct link
    report_direct = validate_target_disease_hypothesis(kg, "target:braf", "disease:melanoma")
    assert report_direct["topologically_supported"] is True
    assert report_direct["direct_link"] is True
    assert report_direct["confidence_score"] >= 0.9

    # Validate 2-hop link from Drug to Disease
    report_2hop = validate_target_disease_hypothesis(kg, "drug:vemurafenib", "disease:melanoma", max_hops=2)
    assert report_2hop["topologically_supported"] is True
    assert report_2hop["direct_link"] is False
    assert len(report_2hop["path_traces"]) > 0

    # Test GraphRAG context creation
    rag_context = build_graphrag_context(kg)
    assert "GraphRAG Context" in rag_context
    assert "BRAF" in rag_context
    assert "Vemurafenib" in rag_context
    assert "ASSOCIATED_WITH" in rag_context


def test_graphml_export():
    """Verify GraphML file generation for Cytoscape."""
    temp_dir = tempfile.mkdtemp()
    out_file = os.path.join(temp_dir, "test_subgraph.graphml")

    kg = BioKnowledgeGraph("Export Graph")
    kg.add_node("target:tp53", "Target", "TP53")
    kg.add_node("disease:sarcoma", "Disease", "Sarcoma")
    kg.add_edge("target:tp53", "disease:sarcoma", "MUTATED_IN")

    kg.export_graphml(out_file)
    assert os.path.exists(out_file)
    content = Path(out_file).read_text(encoding="utf-8")
    assert "<graphml" in content
    assert "TP53" in content
    assert "MUTATED_IN" in content

    shutil.rmtree(temp_dir, ignore_errors=True)
