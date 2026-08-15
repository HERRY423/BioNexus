"""JSON config for gold-chain CLIs. CLI flags override file keys."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

PathLike = Union[str, Path]


def load_pipeline_config(path: Optional[PathLike]) -> Dict[str, Any]:
    if path is None:
        return {}
    dest = Path(path)
    if not dest.is_file():
        raise FileNotFoundError(f"Pipeline config not found: {dest}")
    data = json.loads(dest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Pipeline config must be a JSON object")
    return data


def merge_config(file_cfg: Mapping[str, Any], cli: Mapping[str, Any]) -> Dict[str, Any]:
    """CLI values win when not None."""
    out = dict(file_cfg)
    for key, value in cli.items():
        if value is not None:
            out[key] = value
    return out
