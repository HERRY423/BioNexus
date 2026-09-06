# Audit one analysis before changing your workflow

Start with declared example metadata. The command below only evaluates a
request; it does not launch an analysis, send data to a provider, or change your
pipeline. Run from a BioNexus checkout after `python -m pip install -e .`.

```bash
python examples/shadow_audit.py
```

The example declares one biological replicate per condition and integer counts;
replace those declarations with metadata from your own analysis when integrating.
Read these fields in the returned JSON:

| Field | What to do with it |
|---|---|
| `matched_capability_id` | Confirm this is the analysis you actually intended. |
| `status`, `violations`, `remedies` | Record the finding and required correction. Missing backends can still cause refusal. |
| `evidence_card_template.details.warrant_assessment` | Retain the evidence ceiling and unsupported claims alongside your result. |
| `evidence_card_template.details.shadow_violations` | Review the soft warnings that the policy observed. |

Shadow mode preserves evidence ceilings. Integrity and safety invariants, and
registry-enforced constraints, still block. It is not an unconditional bypass.
One biological replicate per condition does not become population-level evidence
because a host receives permission to explore it. An absent finding does not prove
scientific validity; metadata supplied here is a declaration, not inspected data.

For a local pilot, have a named scientist review a fixed set of historical analyses
before comparing BioNexus findings. Record correct detections, false alarms, missed
problems, unresolved cases, and review time. Keep unresolved cases separate from
negatives. Decide whether to adopt advisory mode from those results; no empirical
false-positive rate or calibration approval is established by this example.

## Reproduce the software checks

For actual backend execution on small **synthetic** datasets:

```bash
python -m pip install -e ".[goldchain,spatial]"
python scripts/run_benchmark_evidence.py --suite l3_scientific_outcomes --level L3 --strict --output results/planted-l3-first-run
```

The output directory must be new. Read `report.json`, `report.md`, and
`manifest.json` together: selection, failures/skips, installed versions and raw-file
source hashes are retained. On the supported CI job these checks run before public
dataset acquisition, so a failed download cannot hide the planted endpoint results.

L1 routing, replay L2, synthetic L3, public-data studies, live-host runs, external
replication and approved empirical calibration are different evidence classes.
The full benchmark still requires the pinned public flagship datasets. Exclusions
are recorded in both report formats; a subset pass does not describe the full suite.

Next: [assessment response and remaining gaps](../review/deep-analysis-2026-09-04/RESPONSE.md).
