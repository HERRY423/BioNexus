---
name: protein-structure-analysis
description: Only if the user explicitly asked for structure I/O or docking prep. Fetches PDB/AF files and writes Vina config. Does not run AlphaFold/DiffDock. Not a default analysis skill.
---

# Structure I/O and docking prep

- Fetchers download existing files. They do not fold proteins.
- Pocket detector is a CA grid heuristic (`evidence_grade=C`).
- `molecular_docking.py` writes a config file. It does not launch Vina unless the user runs the binary.
- TM-score after length truncation is not TM-align.
