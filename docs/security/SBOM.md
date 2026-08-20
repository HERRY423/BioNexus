# BioNexus Software Bill of Materials (SBOM) Specification

## 1. Overview & Standard

BioNexus generates a cryptographically verifiable **Software Bill of Materials (SBOM)** adhering to the [CycloneDX v1.5](https://cyclonedx.org/) and [SPDX 2.3](https://spdx.dev/) standards.

The SBOM provides:
- Complete inventory of all runtime, analytical, and optional dependencies.
- Standard Package URLs (`purl`) for automated vulnerability scanning in enterprise scanners (e.g. Snyk, Trivy, Grype, GitHub Dependency Graph).
- Explicit license declarations for all components (Apache-2.0, BSD-3-Clause, MIT).

---

## 2. Generating the SBOM

To generate the SBOM for the current BioNexus installation:

```bash
# Generate CycloneDX JSON
python scripts/generate_sbom.py -o sbom.json

# Or via CLI
bionexus security sbom -o sbom.json
```

---

## 3. Automated Vulnerability Scanning & CI

In GitHub Actions, each release build executes `pip-audit` against the SBOM and pinned dependencies to ensure:
1. Zero known vulnerabilities (CVEs with CVSS score $\ge 7.0$).
2. Immediate alerting on newly disclosed vulnerabilities in upstream dependencies (`scanpy`, `pydeseq2`, `torch`, etc.).
