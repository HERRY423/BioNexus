---
name: biologics-design
description: Only if the user explicitly asked for a grade-C heuristic. Sequence-level antibody Fv motif scan and codon-table rewrite. abnumber IMGT when installed; otherwise regex. Not SAP. Not a default analysis skill.
---

# Biologics design

## Use

- Parse VH/VL and report CDR/FR **with the method named in the JSON**.
- Flag unpaired Cys, CDR3 hydrophobic runs, NG/NS/NT, DG/DS/DT, N-X-S/T sequons.
- Rewrite a protein to a human preferred-codon table.

## Do not

- Call regex anchors IMGT/Chothia.
- Call motif flags Spatial Aggregation Propensity.
- Invent a germline identity (default is `null`).
- Call pair-count ΔG an RNAfold MFE.

## Backends

| Task | Backend | Extra |
|---|---|---|
| IMGT numbering | `abnumber` | `bionexus[structure]` |
| MFE | ViennaRNA `RNA` | `bionexus[biologics]` |
| Motifs / codon table | local | none |

Refuse to emit `evidence_grade=A` unless the matching backend ran.
