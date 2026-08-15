#!/usr/bin/env python3
"""Plugin environment gate. Run before analysis skills."""

from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bio_research.doctor import main

if __name__ == "__main__":
    main()
