# Antigravity live-host evidence

`REQUEST.json` is a fixed, checksum-bound six-case input with hidden expected
labels. Antigravity writes `RUN.json` only after calling the local
`bionexus_host_probe`; the server appends `mcp-audit.jsonl`. The independent
verifier writes `REPORT.json` only if the request, session, receipt hash chain,
clean git binding, and all six classifications pass.

Prepare the request:

```text
python evals/antigravity_acceptance.py --prepare
```

In Antigravity invoke `/bionexus-live-acceptance`, then verify locally:

```text
python evals/antigravity_acceptance.py
```

This evidence is scoped to technical host integration. It does not evaluate
biological accuracy, clinical validity, regulatory compliance, calibration, or
cryptographic identity attestation.
