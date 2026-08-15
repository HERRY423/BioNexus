#!/usr/bin/env python3
"""Generate a Methods paragraph from a provenance sidecar.

Writes only what the activity and parameters support. Does not invent
scRNA-seq Methods for unrelated jobs.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List


def _activity_kind(activity: str, params: Dict[str, Any]) -> str:
    text = f"{activity} {' '.join(str(k) for k in params)}".lower()
    if any(token in text for token in ("scrna", "single-cell", "single cell", "mad_", "doublet", "qc")):
        return "scrna_qc"
    if any(token in text for token in ("scvi", "n_latent", "scanvi")):
        return "scvi"
    if any(token in text for token in ("acmg", "variant", "hgvs")):
        return "variant"
    if any(token in text for token in ("dock", "pdb", "structure")):
        return "structure"
    return "generic"


def generate_methods_text(manifest: Dict[str, Any]) -> str:
    env = manifest.get("environment_snapshot", {})
    packages = env.get("packages", {})
    params = manifest.get("parameters", {})
    activity = manifest.get("activity_name", "Computational Analysis")
    inputs = manifest.get("input_files", [])
    outputs = manifest.get("output_files", [])
    kind = _activity_kind(activity, params)

    lines: List[str] = [
        f"## Methods: {activity}\n",
        "### Computational Environment and Reproducibility",
        f"Analyses were run in Python v{env.get('python_version', '3.10+')} "
        f"on {env.get('os_name', 'Linux')} ({env.get('architecture', 'x86_64')}). ",
    ]
    if env.get("cuda_available"):
        lines.append(f"GPU: {env.get('cuda_device_name')} (CUDA {env.get('cuda_version', 'N/A')}).\n")
    else:
        lines.append("No CUDA device was recorded.\n")

    if kind == "scrna_qc":
        scanpy_ver = packages.get("scanpy", "not recorded")
        anndata_ver = packages.get("anndata", "not recorded")
        lines.append("### Quality Control and Preprocessing")
        lines.append(
            f"Single-cell QC used Scanpy (v{scanpy_ver}) and AnnData (v{anndata_ver}). "
            f"Cell filtering applied Median Absolute Deviation (MAD) thresholds "
            f"for total counts (MAD = {params.get('mad_counts', 'not set')}), "
            f"detected genes (MAD = {params.get('mad_genes', 'not set')}), and "
            f"mitochondrial percentage (MAD = {params.get('mad_mt', 'not set')}, "
            f"hard cutoff = {params.get('mt_threshold', 'not set')}%). "
        )
        if params.get("run_doublets"):
            lines.append("Doublets were scored with the local kNN simulation heuristic, not scDblFinder. ")
        if params.get("run_ambient"):
            lines.append(
                "Ambient RNA was estimated from empty-droplet profiles when provided; this is not SoupX/CellBender. "
            )
    elif kind == "scvi":
        scvi_ver = packages.get("scvi-tools", packages.get("scvi", "not recorded"))
        lines.append("### Deep generative modeling")
        lines.append(
            f"Latent modeling used scvi-tools (v{scvi_ver}) with "
            f"n_latent={params.get('n_latent', 'not set')}, "
            f"n_layers={params.get('n_layers', 'not set')}."
        )
    elif kind == "variant":
        lines.append("### Variant combination")
        lines.append(
            "ACMG/AMP combination used caller-supplied evidence codes and the Tavtigian 2018 likelihood-ratio product. "
            "No VEP/gnomAD query was implied by this Methods text."
        )
    elif kind == "structure":
        lines.append("### Structure handling")
        lines.append(
            "Coordinates were parsed from PDB/mmCIF text. Pocket or docking steps are reported only if those binaries were recorded in parameters."
        )
    else:
        lines.append("### Analysis")
        lines.append(
            f"See recorded parameters for the procedure. Method={manifest.get('method', 'unspecified')}; "
            f"backend={manifest.get('backend', 'unspecified')}."
        )

    lines.extend(
        [
            "\n### Data lineage",
            "SHA-256 Checksum hashes were recorded for files that existed on disk. This is not 21 CFR Part 11 evidence.",
            "| Artifact Name | Role | SHA-256 Checksum |",
            "|---|---|---|",
        ]
    )
    for item in inputs + outputs:
        digest = item.get("sha256") or "missing"
        short = digest[:24] + "..." if isinstance(digest, str) and len(digest) > 24 else digest
        lines.append(f"| `{item.get('file_name')}` | {item.get('role')} | `{short}` |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Methods text from a provenance sidecar")
    parser.add_argument("manifest", help="Path to provenance_manifest.json")
    parser.add_argument("-o", "--output", default="methods_section.md")
    args = parser.parse_args()
    if not os.path.exists(args.manifest):
        print(f"Error: Manifest file not found: {args.manifest}", file=sys.stderr)
        sys.exit(1)
    with open(args.manifest, "r", encoding="utf-8") as handle:
        manifest_data = json.load(handle)
    methods_md = generate_methods_text(manifest_data)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(methods_md)
    print(f"Methods section written -> {args.output}")


if __name__ == "__main__":
    main()
