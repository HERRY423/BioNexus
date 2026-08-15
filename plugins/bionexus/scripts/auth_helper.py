#!/usr/bin/env python3
"""
Authentication & Credential Helper for BioNexus Plugin.
Loads, validates, and checks API credentials from environment variables or .env file.
"""

import argparse
import os
import sys
from typing import Dict, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

SUPPORTED_CREDENTIALS = {
    "NCBI_API_KEY": {
        "provider": "NCBI / PubMed",
        "purpose": "Raises E-utilities rate limit from 3 req/sec to 10 req/sec",
        "optional": True,
        "signup_url": "https://www.ncbi.nlm.nih.gov/account/settings/"
    },
    "BENCHLING_API_KEY": {
        "provider": "Benchling LIMS / ELN",
        "purpose": "Connects to internal lab notebook, sample registry, and workflows",
        "optional": True,
        "signup_url": "https://benchling.com/"
    },
    "BENCHLING_TENANT": {
        "provider": "Benchling LIMS / ELN",
        "purpose": "Your organization's Benchling subdomain (e.g. 'mycompany.benchling.com')",
        "optional": True,
        "signup_url": "https://benchling.com/"
    },
    "SYNAPSE_AUTH_TOKEN": {
        "provider": "Sage Bionetworks Synapse",
        "purpose": "Access collaborative research datasets, DREAM challenges, and open science data",
        "optional": True,
        "signup_url": "https://www.synapse.org/#!PersonalAccessTokens:"
    },
    "WILEY_API_KEY": {
        "provider": "Wiley Scholar Gateway",
        "purpose": "Access academic research and full-text publications",
        "optional": True,
        "signup_url": "https://scholargateway.ai/"
    },
    "CONSENSUS_API_KEY": {
        "provider": "Consensus AI",
        "purpose": "AI-powered scientific research synthesis",
        "optional": True,
        "signup_url": "https://consensus.app/"
    },
    "OWKIN_API_KEY": {
        "provider": "Owkin",
        "purpose": "AI for biology and precision drug discovery",
        "optional": True,
        "signup_url": "https://owkin.com/"
    },
    "BIORENDER_API_KEY": {
        "provider": "BioRender",
        "purpose": "Export and integrate scientific illustrations",
        "optional": True,
        "signup_url": "https://biorender.com/"
    }
}


def load_env_file(filepath: Optional[str] = None) -> Dict[str, str]:
    """Load key-value pairs from .env file into os.environ."""
    candidates = []
    if filepath:
        candidates.append(filepath)
    else:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates.extend([
            os.path.join(os.getcwd(), ".env"),
            os.path.join(root_dir, ".env"),
            os.path.expanduser("~/.gemini/config/.env")
        ])

    loaded = {}
    for cand in candidates:
        if os.path.exists(cand):
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k not in os.environ:
                                os.environ[k] = v
                            loaded[k] = v
                break
            except Exception as e:
                print(f"Warning: Could not read {cand}: {e}", file=sys.stderr)
    return loaded


def check_status():
    """Print comprehensive credential diagnostic table."""
    load_env_file()
    print("=" * 75)
    print(" [BioNexus Plugin] Credential & API Authentication Status")
    print("=" * 75)
    print(f"{'Key Name':<22} | {'Provider':<24} | {'Status':<10} | {'Type'}")
    print("-" * 75)

    configured_count = 0
    for key, meta in SUPPORTED_CREDENTIALS.items():
        val = os.environ.get(key)
        if val and len(val.strip()) > 0:
            status = "[SET] Configured"
            configured_count += 1
        else:
            status = "[--] Missing"

        req_type = "Optional" if meta["optional"] else "Required"
        print(f"{key:<22} | {meta['provider']:<24} | {status:<16} | {req_type}")

    print("-" * 75)
    print(f"Summary: {configured_count}/{len(SUPPORTED_CREDENTIALS)} credentials configured.")
    print("\nTips:")
    print("  - To configure missing keys, copy `.env.example` to `.env` and fill in your values.")
    print("  - Core databases (NCBI PubMed, bioRxiv, ChEMBL, OpenTargets, ClinicalTrials) work without any API keys.")
    print("=" * 75)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BioNexus Auth & Credential Helper")
    parser.add_argument("--status", "--check", action="store_true", help="Check credential configuration status")
    args = parser.parse_args()

    check_status()
