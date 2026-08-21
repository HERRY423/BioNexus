# BioNexus Release Signing & Cryptographic Provenance

## 1. Cryptographic Release Signing Architecture

All official releases and container images of BioNexus are signed using [Sigstore Cosign](https://www.sigstore.dev/) and GitHub Artifact Attestations (`actions/attest-build-provenance@v2`) to provide keyless, tamper-evident cryptographic provenance backed by Sigstore transparency logs.

```mermaid
graph LR
    Build["GitHub Actions Release Build"] --> Attest["GitHub Artifact Attestation<br/>(Sigstore In-toto Provenance)"]
    Attest --> Publish["GitHub Releases & PyPI"]
    Publish --> Verify["Client Verification<br/>(gh attestation verify / cosign)"]
```

---

## 2. Two-Tier Release Distribution Architecture

To strictly balance public open-source availability with institutional data governance and privacy compliance, BioNexus release assets are strictly bifurcated into two distinct layers:

### Tier 1: Public Release Assets (GitHub Releases & PyPI)
Designed for public distribution and open reproduction:
- Python Wheel (`.whl`) and Source Distribution (`.tar.gz`)
- `SHA256SUMS.txt` manifest
- Benchmark and evaluation reports (`benchmark_report.md`, `wheel_benchmark_report.md`)
- Platform manifests (`plugin.json`, `mcp.json`, `marketplace.json`)
- CycloneDX SBOM (`sbom.json`)
- GitHub Artifact Attestation (Sigstore In-toto signed DSSE bundle)

### Tier 2: Independent Research Evidence Package
Designed for biostatistical reproducibility and cryptographic audit:
- `PROVENANCE.json` (execution provenance and environment locks)
- `ATTESTATION_BUNDLE.json` (Sigstore v0.2 DSSE In-toto attestation)
- `VERIFICATION_RECEIPT.json` (Ed25519 verification receipt)
- Standalone Rekor transparency log proofs (`rekor_transparency_proof.json`)
- RFC 3161 timestamp authority evidence (`tsa_timestamp_token.json`)

> [!IMPORTANT]
> **Data Privacy & Governance Rule**: Controlled institutional LIMS data, donor-level unmasked clinical matrices, and restricted PHI are strictly excluded from public distribution packages and remain protected within air-gapped or controlled-access boundaries.

---

## 3. Verifying Release Integrity

To verify the cryptographic authenticity and provenance of a BioNexus wheel or tarball release:

### Using GitHub CLI:
```bash
gh attestation verify dist/bionexus_reliability-1.0.0rc2-py3-none-any.whl --owner HERRY423
```

### Using Sigstore Cosign:
```bash
cosign verify-blob \
  --certificate-identity "https://github.com/HERRY423/BioNexus/.github/workflows/release.yml@refs/heads/main" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  --bundle dist/bionexus-1.0.0-rc.2.bundle \
  dist/bionexus_reliability-1.0.0rc2-py3-none-any.whl
```

### Using Local SHA-256 Manifest:
```bash
sha256sum -c dist/SHA256SUMS.txt
```
