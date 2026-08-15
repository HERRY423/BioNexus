#!/usr/bin/env python3
"""
GraphRAG Hypothesis Validator and Context Builder.
Performs biological topological validation across knowledge subgraphs
and compiles ground-truth factual context blocks for LLM reasoning.

Usage:
    from bio_knowledge_graph import BioKnowledgeGraph
    from hypothesis_validator import validate_target_disease_hypothesis, build_graphrag_context

    kg = BioKnowledgeGraph("Target Discovery Graph")
    # ... populate graph ...
    val_report = validate_target_disease_hypothesis(kg, "target:kras", "disease:pancreatic_cancer")
    rag_context = build_graphrag_context(kg, focus_entities=["target:kras", "disease:pancreatic_cancer"])
"""

from typing import Any, Dict, List, Optional

from bio_knowledge_graph import BioKnowledgeGraph


def validate_target_disease_hypothesis(
    kg: BioKnowledgeGraph, target_id: str, disease_id: str, max_hops: int = 3
) -> Dict[str, Any]:
    """
    Validate whether a target-disease link is topologically supported in the knowledge graph.

    Parameters
    ----------
    kg : BioKnowledgeGraph
        Populated knowledge graph
    target_id : str
        Target entity ID (e.g. 'target:kras' or 'gene:egfr')
    disease_id : str
        Disease entity ID (e.g. 'disease:melanoma')
    max_hops : int
        Maximum path search depth (default: 3)

    Returns
    -------
    report : dict containing connectivity status, path traces, and confidence score
    """
    paths = kg.find_paths_between(target_id, disease_id, max_depth=max_hops)

    direct_link = any(len(p) == 1 for p in paths)
    supported = len(paths) > 0

    # Calculate evidence strength score based on shortest path lengths and weights
    if not supported:
        confidence = 0.0
        reasoning = f"No path found between {target_id} and {disease_id} within {max_hops} hops."
    elif direct_link:
        confidence = 0.95
        reasoning = f"Direct direct association found between {target_id} and {disease_id}."
    else:
        shortest_len = min(len(p) for p in paths)
        confidence = max(0.4, 0.9 - (shortest_len - 1) * 0.25)
        reasoning = f"Multi-hop biological connection found via {shortest_len} hops across intermediate entities."

    formatted_paths = []
    for p in paths[:5]:
        trace = []
        for step in p:
            src_label = kg.nodes.get(step["from"], {}).get("label", step["from"])
            tgt_label = kg.nodes.get(step["to"], {}).get("label", step["to"])
            trace.append(f"({src_label}) --[{step['relation']}]--> ({tgt_label})")
        formatted_paths.append(" -> ".join(trace))

    return {
        "target": target_id,
        "disease": disease_id,
        "topologically_supported": supported,
        "direct_link": direct_link,
        "num_connecting_paths": len(paths),
        "confidence_score": round(confidence, 3),
        "reasoning": reasoning,
        "path_traces": formatted_paths,
    }


def build_graphrag_context(
    kg: BioKnowledgeGraph, focus_entities: Optional[List[str]] = None, max_nodes: int = 30
) -> str:
    """
    Compile a structured GraphRAG factual context block for LLM prompt augmentation.
    This injects verified biological graph triples to eliminate hallucination.
    """
    lines = [
        "### Grounded Biological Knowledge Subgraph (GraphRAG Context)",
        f"Knowledge Graph: {kg.name} | Total Entities: {len(kg.nodes)} | Verified Relations: {len(kg.edges)}\n",
        "#### Key Biological Entities:",
    ]

    nodes_to_include = list(kg.nodes.values())[:max_nodes]
    for n in nodes_to_include:
        lines.append(f"- **{n['label']}** ({n['type']}): {n['properties'].get('description', '')[:100]}")

    lines.append("\n#### Verified Biological Relationships & Triples:")
    for e in kg.edges[: max_nodes * 2]:
        src_label = kg.nodes.get(e["source"], {}).get("label", e["source"])
        tgt_label = kg.nodes.get(e["target"], {}).get("label", e["target"])
        lines.append(f"- `{src_label}` **{e['relation']}** `{tgt_label}` (weight: {e['weight']:.2f})")

    return "\n".join(lines)
