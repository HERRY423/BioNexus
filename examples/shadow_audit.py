#!/usr/bin/env python3
"""Inspect declared example metadata; do not run an analysis or inspect real data."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bionexus.intent_router import route_scientific_intent

if __name__ == "__main__":
    decision = route_scientific_intent(
        "Run differential expression between conditions",
        data_metadata={
            "n_cells": 5000,
            "has_condition": True,
            "conditions": ["ctrl", "treat"],
            "min_replicates_per_condition": 1,
            "is_normalized": False,
            "is_integer_like": True,
        },
        research_purpose="screening",
        lab_policy="shadow_audit",
    )
    print(json.dumps(decision.to_dict(), indent=2))
