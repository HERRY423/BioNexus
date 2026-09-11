"""Tamper-evident receipts for live BioNexus MCP host acceptance (compatibility shim)."""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to sys.path if not present for in-tree execution
_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import bionexus.mcp_host_audit as _impl

# Re-export everything from bionexus.mcp_host_audit
for _k, _v in _impl.__dict__.items():
    if not _k.startswith("__"):
        globals()[_k] = _v

sys.modules["mcp_host_audit"] = _impl
sys.modules["scripts.mcp_host_audit"] = _impl
sys.modules[__name__] = _impl
