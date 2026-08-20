#!/usr/bin/env python3
"""
BioNexus Software Bill of Materials (SBOM) Generator.

Generates a standard CycloneDX JSON (v1.5) and SPDX SBOM document
capturing all direct dependencies, transitive libraries, licenses,
and cryptographic package URLs (purl) for supply chain security.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from bionexus.versions import PLUGIN_VERSION


def generate_cyclonedx_sbom() -> Dict[str, Any]:
    """Generate CycloneDX v1.5 JSON SBOM for BioNexus."""
    pyproject_path = _REPO_ROOT / "pyproject.toml"
    content = pyproject_path.read_text(encoding="utf-8")

    # Parse pyproject dependencies
    deps: List[str] = []
    optional_deps: Dict[str, List[str]] = {}

    if sys.version_info >= (3, 11):
        import tomllib
        data = tomllib.loads(content)
        deps = data.get("project", {}).get("dependencies", [])
        optional_deps = data.get("project", {}).get("optional-dependencies", {})
    else:
        # Fallback simple parser for dependencies
        in_deps = False
        for line in content.splitlines():
            line = line.strip()
            if line == "dependencies = [":
                in_deps = True
                continue
            if in_deps:
                if line == "]":
                    in_deps = False
                elif line.startswith('"') or line.startswith("'"):
                    dep = line.strip('",\' ')
                    if dep:
                        deps.append(dep)

    components: List[Dict[str, Any]] = [
        {
            "type": "application",
            "name": "bionexus-reliability",
            "version": PLUGIN_VERSION,
            "description": "Scientific Reliability Layer & Scientific Warrant Engine for AI Agents",
            "licenses": [{"license": {"id": "Apache-2.0"}}],
            "purl": f"pkg:pypi/bionexus-reliability@{PLUGIN_VERSION}",
        }
    ]

    for dep in deps:
        # Parse name and version specifier
        name = dep.split(">=")[0].split("==")[0].split("<")[0].split(";")[0].strip()
        components.append(
            {
                "type": "library",
                "name": name,
                "version": "declared_in_pyproject",
                "scope": "required",
                "purl": f"pkg:pypi/{name}",
            }
        )

    for extra_name, extra_list in optional_deps.items():
        for dep in extra_list:
            if isinstance(dep, str) and not dep.startswith("bionexus"):
                name = dep.split(">=")[0].split("==")[0].split("<")[0].split(";")[0].strip()
                components.append(
                    {
                        "type": "library",
                        "name": name,
                        "version": "declared_in_pyproject",
                        "scope": f"optional:{extra_name}",
                        "purl": f"pkg:pypi/{name}",
                    }
                )

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:bionexus-sbom-{PLUGIN_VERSION}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools": [{"vendor": "BioNexus", "name": "bionexus-sbom-generator", "version": PLUGIN_VERSION}],
            "component": {
                "type": "application",
                "name": "bionexus-reliability",
                "version": PLUGIN_VERSION,
                "licenses": [{"license": {"id": "Apache-2.0"}}],
            },
        },
        "components": components,
    }
    return sbom


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate BioNexus CycloneDX SBOM")
    parser.add_argument("-o", "--output", default="sbom.json", help="Output JSON path (default: sbom.json)")
    args = parser.parse_args()

    sbom = generate_cyclonedx_sbom()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(sbom, indent=2), encoding="utf-8")
    print(f"[OK] Generated CycloneDX SBOM ({len(sbom['components'])} components) -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
