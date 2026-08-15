---
name: provenance-and-audit
description: SHA-256 hashes, environment snapshot, and activity-aware Methods text. Use to attach a reproducibility sidecar to an analysis. Do not use for 21 CFR Part 11, GxP, ALCOA+, or CLIA audit claims.
---

# Provenance sidecar

Prefer `bio_research.provenance.sidecar` from the shared kernel. The skill scripts wrap the same functions. Methods text is generated from the activity name and recorded parameters; it will not invent an scRNA-seq paragraph for a docking job.
