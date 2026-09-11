#!/usr/bin/env python3
"""
Local Fallback MCP Server for BioNexus (Compatibility Wrapper).
Delegates directly to bionexus.mcp_server in the installed package or in-tree src.
"""
import sys
from pathlib import Path

# Add src to sys.path if not present for in-tree execution
sys_src = str(Path(__file__).resolve().parent.parent / "src")
if sys_src not in sys.path:
    sys.path.insert(0, sys_src)

import bionexus.mcp_server as _mcp_server

# Re-export everything for static analyzers and callers
for _k, _v in _mcp_server.__dict__.items():
    if not _k.startswith("__"):
        globals()[_k] = _v

# Make sys.modules aliases so unittest patch("local_mcp_server.xyz")
# patches bionexus.mcp_server directly
sys.modules["local_mcp_server"] = _mcp_server
sys.modules[__name__] = _mcp_server

if __name__ == "__main__":
    _mcp_server.main()
