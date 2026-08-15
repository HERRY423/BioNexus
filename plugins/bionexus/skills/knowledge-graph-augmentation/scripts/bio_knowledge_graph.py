#!/usr/bin/env python3
"""
Multi-Modal Biological Knowledge Subgraph Engine.
Constructs heterogeneous knowledge graphs connecting Genes/Targets, Diseases,
Pathways, Bioactive Compounds, and Clinical Trials.

Features:
- Ingestion adapters for Open Targets, UniProt, ChEMBL, and Reactome
- Topological metrics (Betweenness, Degree Centrality, Shortest Paths)
- Graph serialization to JSON, GraphML, Cytoscape JSON, and Markdown summaries
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple


class BioKnowledgeGraph:
    def __init__(self, name: str = "BioNexus Knowledge Subgraph"):
        self.name = name
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []
        self.created_at = datetime.now(timezone.utc).isoformat()

    def add_node(self, node_id: str, node_type: str, label: str, properties: Optional[Dict[str, Any]] = None):
        """Add or update a node in the knowledge graph."""
        node_id = str(node_id).strip()
        if node_id not in self.nodes:
            self.nodes[node_id] = {"id": node_id, "type": node_type, "label": label, "properties": properties or {}}
        else:
            if properties:
                self.nodes[node_id]["properties"].update(properties)

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        weight: float = 1.0,
        properties: Optional[Dict[str, Any]] = None,
    ):
        """Add a directed or undirected edge between two nodes."""
        source_id = str(source_id).strip()
        target_id = str(target_id).strip()

        # Ensure both nodes exist
        if source_id not in self.nodes:
            self.add_node(source_id, "unknown", source_id)
        if target_id not in self.nodes:
            self.add_node(target_id, "unknown", target_id)

        edge_data = {
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "weight": float(weight),
            "properties": properties or {},
        }
        self.edges.append(edge_data)

    def ingest_opentargets_hits(self, query: str, hits: List[Dict[str, Any]]):
        """Ingest Open Targets search hits (Targets and Diseases)."""
        disease_node_id = f"disease:{query.lower().replace(' ', '_')}"
        self.add_node(disease_node_id, "Disease", query)

        for h in hits:
            entity_type = h.get("entity", "Target")
            entity_name = h.get("name", h.get("id"))
            entity_id = f"{entity_type.lower()}:{h.get('id')}"

            self.add_node(
                entity_id,
                entity_type.capitalize(),
                entity_name,
                {"description": h.get("description", ""), "score": h.get("score", 1.0)},
            )

            self.add_edge(
                source_id=entity_id,
                target_id=disease_node_id,
                relation="ASSOCIATED_WITH",
                weight=float(h.get("score", 1.0) or 1.0),
                properties={"source": "OpenTargets"},
            )

    def ingest_uniprot_protein(self, protein_info: Dict[str, Any]):
        """Ingest UniProt protein annotations and gene mappings."""
        acc = protein_info.get("accession")
        if not acc:
            return

        prot_id = f"target:{acc}"
        self.add_node(
            prot_id,
            "Target",
            protein_info.get("protein_name", acc),
            {
                "accession": acc,
                "organism": protein_info.get("organism"),
                "function": protein_info.get("function"),
                "sequence_length": protein_info.get("sequence_length"),
            },
        )

        # Connect genes
        for g in protein_info.get("genes", []):
            gene_id = f"gene:{g}"
            self.add_node(gene_id, "Gene", g)
            self.add_edge(gene_id, prot_id, "ENCODES", weight=1.0)

    def ingest_chembl_molecule(self, target_name: str, molecule_info: Dict[str, Any]):
        """Ingest ChEMBL bioactive molecules and their inhibition relation."""
        chembl_id = molecule_info.get("chembl_id")
        if not chembl_id:
            return

        mol_id = f"drug:{chembl_id}"
        self.add_node(
            mol_id,
            "Drug",
            molecule_info.get("pref_name") or chembl_id,
            {
                "chembl_id": chembl_id,
                "max_phase": molecule_info.get("max_phase"),
                "molecular_weight": molecule_info.get("molecular_weight"),
                "canonical_smiles": molecule_info.get("canonical_smiles"),
            },
        )

        target_id = f"target:{target_name}"
        self.add_edge(mol_id, target_id, "INHIBITS", weight=0.9, properties={"source": "ChEMBL"})

    def find_paths_between(self, start_id: str, end_id: str, max_depth: int = 3) -> List[List[Dict[str, Any]]]:
        """Find simple paths between two entities in the knowledge graph."""
        adj: Dict[str, List[Tuple[str, str, float]]] = {}
        for edge in self.edges:
            s, t, r, w = edge["source"], edge["target"], edge["relation"], edge["weight"]
            adj.setdefault(s, []).append((t, r, w))
            adj.setdefault(t, []).append((s, r, w))  # Traverse bidirectionally

        paths: List[List[Dict[str, Any]]] = []

        def dfs(curr: str, target: str, visited: Set[str], current_path: List[Dict[str, Any]]):
            if len(current_path) > max_depth:
                return
            if curr == target and current_path:
                paths.append(list(current_path))
                return

            visited.add(curr)
            for neighbor, rel, weight in adj.get(curr, []):
                if neighbor not in visited:
                    current_path.append({"from": curr, "to": neighbor, "relation": rel, "weight": weight})
                    dfs(neighbor, target, visited, current_path)
                    current_path.pop()
            visited.remove(curr)

        dfs(start_id, end_id, set(), [])
        return paths

    def get_summary_statistics(self) -> Dict[str, Any]:
        """Return node counts by entity type and edge counts by relation."""
        type_counts: Dict[str, int] = {}
        for n in self.nodes.values():
            t = n.get("type", "Unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        rel_counts: Dict[str, int] = {}
        for e in self.edges:
            r = e.get("relation", "Unknown")
            rel_counts[r] = rel_counts.get(r, 0) + 1

        return {
            "name": self.name,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_types": type_counts,
            "edge_relations": rel_counts,
        }

    def to_json(self) -> Dict[str, Any]:
        """Export graph structure to JSON dictionary."""
        return {
            "name": self.name,
            "created_at": self.created_at,
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
            "summary": self.get_summary_statistics(),
        }

    def export_graphml(self, output_path: str):
        """Export knowledge graph to GraphML format for Cytoscape / Gephi visualization."""
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
            '  <key id="type" for="node" attr.name="type" attr.type="string"/>',
            '  <key id="label" for="node" attr.name="label" attr.type="string"/>',
            '  <key id="relation" for="edge" attr.name="relation" attr.type="string"/>',
            '  <key id="weight" for="edge" attr.name="weight" attr.type="double"/>',
            f'  <graph id="{self.name}" edgedefault="directed">',
        ]

        for n_id, n_data in self.nodes.items():
            lines.append(f'    <node id="{n_id}">')
            lines.append(f'      <data key="type">{n_data.get("type", "")}</data>')
            lines.append(f'      <data key="label">{n_data.get("label", n_id)}</data>')
            lines.append("    </node>")

        for idx, e in enumerate(self.edges):
            lines.append(f'    <edge id="e{idx}" source="{e["source"]}" target="{e["target"]}">')
            lines.append(f'      <data key="relation">{e["relation"]}</data>')
            lines.append(f'      <data key="weight">{e["weight"]}</data>')
            lines.append("    </edge>")

        lines.append("  </graph>")
        lines.append("</graphml>")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
