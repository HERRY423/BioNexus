#!/usr/bin/env python3
"""
Spatial Transcriptomics Visualization & Interactive Atlas Generator.
Generates publication-quality static figures (spatial domains, feature gradients, niches)
and lightweight interactive HTML tissue slice explorers.
"""

import argparse
import json
import logging
import os
from typing import Optional

import matplotlib
import numpy as np
from scipy import sparse

matplotlib.use("Agg")
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
logger = logging.getLogger("SpatialVisualization")


def plot_spatial_discrete(
    adata,
    color_key: str = "spatial_domain",
    spatial_key: str = "spatial",
    output_path: str = "spatial_domains.png",
    spot_size: float = 30.0,
    title: Optional[str] = None,
):
    """Plot discrete spatial annotations (domains, niches, or cell types)."""
    coords = adata.obsm.get(spatial_key)
    if coords is None:
        raise ValueError(f"Spatial coordinates '{spatial_key}' missing.")

    if color_key not in adata.obs:
        raise ValueError(f"Annotation column '{color_key}' not found in adata.obs.")

    labels = adata.obs[color_key].astype(str)
    categories = np.unique(labels)
    cmap = plt.get_cmap("tab20", len(categories))
    cat_to_color = {cat: cmap(i) for i, cat in enumerate(categories)}

    fig, ax = plt.subplots(figsize=(8, 8), dpi=300)
    for cat in categories:
        mask = (labels == cat).values
        ax.scatter(
            coords[mask, 0],
            coords[mask, 1],
            c=[cat_to_color[cat]],
            label=cat,
            s=spot_size,
            alpha=0.85,
            edgecolors="none",
        )

    ax.set_aspect("equal")
    ax.invert_yaxis()  # Standard histological coordinate convention
    ax.set_xlabel("Spatial X Coordinate")
    ax.set_ylabel("Spatial Y Coordinate")
    ax.set_title(title or f"Spatial Distribution: {color_key}", fontsize=14, fontweight="bold")
    ax.legend(bbox_to_anchor=(1.05, 1), loc="upper left", frameon=True, fontsize=9)
    plt.tight_layout()

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved discrete spatial plot to {output_path}")


def plot_spatial_continuous(
    adata,
    feature_name: str,
    spatial_key: str = "spatial",
    output_path: str = "spatial_feature.png",
    cmap_name: str = "viridis",
    spot_size: float = 30.0,
):
    """Plot continuous feature (gene expression, total counts, or cell type proportion)."""
    coords = adata.obsm.get(spatial_key)
    if coords is None:
        raise ValueError(f"Spatial coordinates '{spatial_key}' missing.")

    # Check obs columns first, then var genes
    if feature_name in adata.obs:
        values = adata.obs[feature_name].values.astype(float)
    elif feature_name in adata.var_names:
        X = adata.X.toarray() if sparse.issparse(adata.X) else adata.X
        idx = list(adata.var_names).index(feature_name)
        values = X[:, idx].astype(float)
    else:
        raise ValueError(f"Feature '{feature_name}' not found in adata.obs or adata.var_names.")

    fig, ax = plt.subplots(figsize=(8, 8), dpi=300)
    sc = ax.scatter(coords[:, 0], coords[:, 1], c=values, cmap=cmap_name, s=spot_size, alpha=0.9, edgecolors="none")
    cbar = plt.colorbar(sc, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(feature_name, fontsize=11)

    ax.set_aspect("equal")
    ax.invert_yaxis()
    ax.set_xlabel("Spatial X Coordinate")
    ax.set_ylabel("Spatial Y Coordinate")
    ax.set_title(f"Spatial Expression: {feature_name}", fontsize=14, fontweight="bold")
    plt.tight_layout()

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)
    logger.info(f"Saved continuous spatial plot to {output_path}")


def generate_interactive_html(adata, output_path: str = "spatial_atlas.html", spatial_key: str = "spatial"):
    """Generate standalone HTML tissue slice viewer with hover tooltip metadata."""
    coords = adata.obsm.get(spatial_key, np.zeros((adata.n_obs, 2)))
    n_spots = min(adata.n_obs, 5000)  # Cap for lightweight browser rendering

    domains = adata.obs["spatial_domain"].values if "spatial_domain" in adata.obs else ["Unknown"] * adata.n_obs
    niches = adata.obs["spatial_niche"].values if "spatial_niche" in adata.obs else ["Unknown"] * adata.n_obs
    counts = adata.obs["total_counts"].values if "total_counts" in adata.obs else [0.0] * adata.n_obs

    spots_data = []
    for i in range(n_spots):
        spot_dict = {
            "x": float(coords[i, 0]),
            "y": float(coords[i, 1]),
            "id": str(adata.obs_names[i]),
            "domain": str(domains[i]),
            "niche": str(niches[i]),
            "counts": float(counts[i]),
        }
        spots_data.append(spot_dict)

    json_payload = json.dumps(spots_data)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>BioNexus Spatial Transcriptomics Atlas</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 20px; background: #0f172a; color: #f8fafc; }}
        h1 {{ font-size: 20px; margin-bottom: 8px; color: #38bdf8; }}
        #container {{ display: flex; gap: 20px; }}
        #canvas-box {{ background: #1e293b; border-radius: 8px; padding: 15px; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }}
        #tooltip {{ position: absolute; display: none; background: rgba(15, 23, 42, 0.95); border: 1px solid #38bdf8; border-radius: 6px; padding: 10px; font-size: 12px; pointer-events: none; }}
        #info-panel {{ width: 280px; background: #1e293b; border-radius: 8px; padding: 15px; font-size: 13px; }}
        .badge {{ display: inline-block; padding: 2px 6px; border-radius: 4px; background: #334155; margin-right: 5px; }}
    </style>
</head>
<body>
    <h1>BioNexus Spatial Transcriptomics Atlas</h1>
    <p style="color: #94a3b8; font-size: 13px; margin-top: 0;">Interactive tissue spot explorer ({n_spots} spots rendered)</p>
    <div id="container">
        <div id="canvas-box">
            <canvas id="spatialCanvas" width="600" height="600"></canvas>
        </div>
        <div id="info-panel">
            <h3>Spot Information</h3>
            <p>Hover over tissue spots to inspect domain annotations and counts.</p>
            <div id="spotDetails"></div>
        </div>
    </div>
    <div id="tooltip"></div>

    <script>
        const spots = {json_payload};
        const canvas = document.getElementById("spatialCanvas");
        const ctx = canvas.getContext("2d");
        const tooltip = document.getElementById("tooltip");
        const spotDetails = document.getElementById("spotDetails");

        // Scale coordinates to canvas
        let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
        spots.forEach(s => {{
            if (s.x < minX) minX = s.x; if (s.x > maxX) maxX = s.x;
            if (s.y < minY) minY = s.y; if (s.y > maxY) maxY = s.y;
        }});
        const pad = 40;
        const scaleX = (canvas.width - 2 * pad) / (maxX - minX || 1);
        const scaleY = (canvas.height - 2 * pad) / (maxY - minY || 1);

        // Color mapping for domains
        const colors = ["#38bdf8", "#818cf8", "#c084fc", "#f472b6", "#fb7185", "#34d399", "#fbbf24", "#a3e635"];
        const domainMap = {{}};
        let colorIdx = 0;

        spots.forEach(s => {{
            if (!(s.domain in domainMap)) {{
                domainMap[s.domain] = colors[colorIdx % colors.length];
                colorIdx++;
            }}
            s.cx = pad + (s.x - minX) * scaleX;
            s.cy = pad + (s.y - minY) * scaleY;
        }});

        function draw() {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            spots.forEach(s => {{
                ctx.beginPath();
                ctx.arc(s.cx, s.cy, 3.5, 0, 2 * Math.PI);
                ctx.fillStyle = domainMap[s.domain] || "#94a3b8";
                ctx.fill();
            }});
        }}
        draw();

        canvas.addEventListener("mousemove", (e) => {{
            const rect = canvas.getBoundingClientRect();
            const mouseX = e.clientX - rect.left;
            const mouseY = e.clientY - rect.top;
            let found = null;

            for (let s of spots) {{
                const dx = s.cx - mouseX;
                const dy = s.cy - mouseY;
                if (dx*dx + dy*dy < 25) {{
                    found = s;
                    break;
                }}
            }}

            if (found) {{
                tooltip.style.display = "block";
                tooltip.style.left = (e.pageX + 12) + "px";
                tooltip.style.top = (e.pageY + 12) + "px";
                tooltip.innerHTML = `<strong>${{found.id}}</strong><br>Domain: ${{found.domain}}<br>Niche: ${{found.niche}}<br>Counts: ${{found.counts}}`;
                spotDetails.innerHTML = `<p><strong>ID:</strong> ${{found.id}}</p><p><strong>Domain:</strong> <span class="badge" style="background:${{domainMap[found.domain]}}">${{found.domain}}</span></p><p><strong>Niche:</strong> ${{found.niche}}</p><p><strong>Total Counts:</strong> ${{found.counts}}</p>`;
            }} else {{
                tooltip.style.display = "none";
            }}
        }});
    </script>
</body>
</html>
"""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"Generated interactive spatial HTML atlas at {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Spatial Transcriptomics Visualization")
    parser.add_argument("--input", "-i", required=True, help="Input spatial AnnData .h5ad file")
    parser.add_argument("--output-dir", "-o", default="spatial_plots", help="Directory to save figures")
    parser.add_argument("--feature", "-f", default=None, help="Continuous feature or gene name to plot")

    args = parser.parse_args()
    import scanpy as sc

    adata = sc.read_h5ad(args.input)
    os.makedirs(args.output_dir, exist_ok=True)

    if "spatial_domain" in adata.obs:
        plot_spatial_discrete(
            adata, color_key="spatial_domain", output_path=os.path.join(args.output_dir, "spatial_domains.png")
        )
    if "spatial_niche" in adata.obs:
        plot_spatial_discrete(
            adata, color_key="spatial_niche", output_path=os.path.join(args.output_dir, "spatial_niches.png")
        )
    if args.feature:
        plot_spatial_continuous(
            adata, feature_name=args.feature, output_path=os.path.join(args.output_dir, f"spatial_{args.feature}.png")
        )

    generate_interactive_html(adata, output_path=os.path.join(args.output_dir, "spatial_atlas.html"))


if __name__ == "__main__":
    main()
