---
name: multiome-integration
description: Only if the user explicitly asked for a grade-C multiome sketch. ExtraTrees co-expression, not SCENIC+. Not a default analysis skill.
---

# Multiome sketches

Function names are historical. The `method` field is authoritative:

- ExtraTrees(n_estimators=10), not GRNBoost2
- Top-5% overlap fraction, not AUCell
- Inverse neighbor-distance weights, not Seurat v4 WNN
- No JASPAR scan unless the caller supplies a peak×motif matrix
