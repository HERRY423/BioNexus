---
name: protein-language-models
description: Only if the user explicitly asked for a grade-C heuristic or ESM-2 with BIONEXUS_ALLOW_ESM=1. Otherwise BLOSUM62 under its own name; never PP3. Not a default analysis skill.
---

# Protein substitution scores

## Rule

**Name = backend.** BLOSUM62 must never be labeled ESM, EVmutation, or ΔLLR from a language model.

## ESM path (grade A)

Set `BIONEXUS_ALLOW_ESM=1` so CI does not download weights. Default model `facebook/esm2_t6_8M_UR50D`. Still do **not** map scores to PP3/BP4; ClinGen requires calibrated predictors.

## BLOSUM path (grade C, abstain)

Position-independent `BLOSUM62(wt,mut) - BLOSUM62(wt,wt)`. `acmg_computational_evidence` is `abstain`.
