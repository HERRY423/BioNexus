# Scientific Semantics neutral governance

This directory is the public, machine-validated governance proposal for the
BioNexus Scientific Semantic Conventions. It separates:

1. **technical authority** — the Scientific Semantics Council (SSC) evolves the
   vocabulary, registry, schemas, and conformance specification;
2. **commercial authority** — product operators fund infrastructure, operate
   services, market products, and license trademarks under published policy;
3. **certification authority** — an assurance scheme owner recognizes
   independent conformity assessment bodies (CABs), and CABs perform
   assessment and issue, suspend, or revoke certificates.

No branch may exercise another branch's reserved powers. In particular,
BioNexus maintainers and commercial operators cannot certify their own tools.

## Current state

The SSC is `FORMING`, not operationally independent. The roster is empty,
institutional adoption declarations are empty, no assurance body is recognized,
and certification/badging remains suspended. These are deliberate, testable
facts in the JSON registries—not narrative caveats.

The governance proposal applies prospectively. It does not silently change the
frozen BNS-019 0.1.0 release or its interoperability trial digest. A future
BNS-019 release may incorporate the framework only through the public RFC and
Council formation process.

Run the governance audit:

```bash
python scripts/validate_semantic_governance.py
```

The command exits non-zero for role overlap, an unsupported independence claim,
an active certification state without a recognized independent CAB, an
unverified adopter claim, or an invalid public record.
