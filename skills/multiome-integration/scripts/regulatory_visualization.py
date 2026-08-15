#!/usr/bin/env python3
"""
Gene Regulatory Network (GRN) Visualization & Cytoscape Exporter.
Exports multi-omics regulon topologies to GraphML and Cytoscape JSON formats
and generates overlap-activity heatmaps. Not AUCell.
"""

import argparse
import json
import logging
import os
from typing import Any, Dict

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("RegulatoryVisualization")


def export_grn_to_cytoscape_json(regulons: Dict[str, Any], output_path: str = "grn_network.json") -> Dict[str, Any]:
    """Export regulon network into Cytoscape.js compatible JSON format."""
    elements = {"nodes": [], "edges": []}
    nodes_seen = set()

    for reg_name, reg_data in regulons.items():
        tf = reg_data["tf"]
        if tf not in nodes_seen:
            elements["nodes"].append({"data": {"id": tf, "name": tf, "type": "Transcription_Factor"}})
            nodes_seen.add(tf)

        for detail in reg_data.get("target_details", []):
            target = detail["target_gene"]
            if target not in nodes_seen:
                elements["nodes"].append({"data": {"id": target, "name": target, "type": "Target_Gene"}})
                nodes_seen.add(target)

            edge_id = f"{tf}_{target}"
            elements["edges"].append(
                {
                    "data": {
                        "id": edge_id,
                        "source": tf,
                        "target": target,
                        "importance": detail.get("importance", 0.1),
                        "mode": detail.get("mode", "Activator (+)"),
                    }
                }
            )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(elements, f, indent=2)
    logger.info(
        f"Exported GRN Cytoscape JSON to {output_path} ({len(elements['nodes'])} nodes, {len(elements['edges'])} edges)."
    )
    return elements


def plot_regulon_activity_heatmap(
    aucell_df: pd.DataFrame, cluster_labels: np.ndarray, output_path: str = "regulon_heatmap.png"
):
    """Plot mean overlap-activity heatmap across clusters. Not AUCell."""
    df = aucell_df.copy()
    df["cluster"] = cluster_labels
    cluster_means = df.groupby("cluster").mean()

    fig, ax = plt.subplots(figsize=(10, max(4, len(cluster_means.columns) * 0.5)), dpi=300)
    cax = ax.matshow(cluster_means.T.values, cmap="YlOrRd", aspect="auto")
    fig.colorbar(cax, ax=ax, label="Mean overlap activity (not AUCell)")

    ax.set_xticks(range(len(cluster_means.index)))
    ax.set_xticklabels(cluster_means.index, rotation=45, ha="left")
    ax.set_yticks(range(len(cluster_means.columns)))
    ax.set_yticklabels(cluster_means.columns)
    ax.set_title("Master Regulon Activity Across Multiome Clusters", fontsize=13, fontweight="bold", pad=20)
    plt.tight_layout()

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved regulon heatmap to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="GRN Regulatory Network Visualizer")
    parser.parse_args()
    logger.info("Regulatory visualization module loaded.")


if __name__ == "__main__":
    main()
