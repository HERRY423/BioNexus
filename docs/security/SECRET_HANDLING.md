# BioNexus Secret Handling & Credential Management Policy

This document outlines policies and technical controls for handling API keys, tokens, and credentials within BioNexus.

---

## 1. Zero Hardcoded Secrets Invariant

**Invariant BNS-SEC-004:** No API tokens, private keys, passwords, or authentication secrets may be hardcoded in repository code, commit history, test fixtures, or configuration files.

- Secrets must be injected exclusively via runtime environment variables (e.g. `GH_TOKEN`, `NCBI_API_KEY`, `OPENAI_API_KEY`) or institutional secret managers (e.g. HashiCorp Vault, AWS Secrets Manager, GCP Secret Manager).
- BioNexus includes automated regex scanning in `bionexus.egress_guard` that actively intercepts and blocks payloads containing GitHub personal access tokens (`ghp_...`), OpenAI keys (`sk-...`), or AWS credentials (`AKIA...`).

---

## 2. Environment Variables & Standard Identifiers

| Variable | Service | Required For |
| :--- | :--- | :--- |
| `GH_TOKEN` / `GITHUB_TOKEN` | GitHub API | GitHub Discussions / Issue creation scripts |
| `NCBI_API_KEY` | NCBI E-Utilities | Increased rate limits for PubMed / dbSNP / ClinVar queries |
| `CHEMBL_API_KEY` | ChEMBL (Optional) | Rate limit increases |
| `BIONEXUS_EGRESS_MODE` | BioNexus Governance | `OFFLINE_STRICT` / `ALLOWLIST` / `CONNECTED` |

---

## 3. Pre-Commit & CI Secret Scanning

- All commits are scanned for secrets before push.
- GitHub Push Protection is enabled on `HERRY423/BioNexus`.
- Automated CI jobs scan for accidental token inclusion in scripts and test suites.

---

## 4. Local Credential Storage

- Local MCP servers and scripts must read credentials from environment variables or standard OS credential stores.
- Never write credentials into `.json`, `.yaml`, or `.env` files tracked by git (`.gitignore` must contain `.env*`, `*.pem`, `*.key`, `credentials.json`).
