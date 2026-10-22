# BioNexus plugin privacy notice

BioNexus is a repository-distributed, passive reliability plugin. The
skills-only plugin does not itself operate a BioNexus-hosted cloud service or
publisher-controlled user database. Prompts, files, and model interactions are
processed by the host product under that host's privacy terms.

Local BioNexus scripts may read files the user explicitly places in scope and
may write reports, logs, hashes, or run artifacts to the selected workspace.
Optional connected scientific workflows can contact third-party services only
when separately configured and invoked; those services have their own terms
and privacy practices. Do not provide patient identifiers, secrets, or raw
restricted data unless the chosen environment, institutional policy, and data
agreements explicitly permit it.

The public repository and issue tracker are public. Never submit confidential
data there. See [SECURITY.md](../SECURITY.md) and
[DATA_CLASSIFICATION.md](security/DATA_CLASSIFICATION.md) for handling and
reporting guidance.

This notice describes the repository package, not the independent privacy
practices of OpenAI, Anthropic, GitHub, or optional scientific data providers.

## Opt-in failure reports

BioNexus does **not** collect telemetry by default and does **not** operate a
publisher-controlled crash service in this release.

- Default: `BIONEXUS_FAILURE_REPORTS` unset / `off`. Nothing is written or sent.
- Local-only: `BIONEXUS_FAILURE_REPORTS=local` or `bionexus deploy report-failure`
  writes a sanitized JSON file under `~/.bionexus/failure-reports/` (or
  `BIONEXUS_FAILURE_REPORTS_DIR`).
- Transmit: only when the lab sets `BIONEXUS_FAILURE_REPORTS=transmit`, sets
  `BIONEXUS_FAILURE_REPORTS_ENDPOINT` to **its own** sink, uses
  `BIONEXUS_EGRESS_MODE=CONNECTED`, classifies the data as `PUBLIC_BENCHMARK`,
  and passes `--opt-in-transmit`.

Reports contain exception type, redacted traceback, BioNexus version, Python
version, OS family, optional command/capability ids, and egress mode. They do
not include argv paths, hostnames, usernames, file bytes, count matrices, gene
lists, or sample identifiers. Paths, emails, IP addresses, secrets, PHI
keywords, and long nucleotide strings are replaced with placeholders before
disk write.

`OFFLINE_STRICT` / air-gap policy, `RESTRICTED_CLINICAL_PHI`, and
`CONTROLLED_ACCESS_GENOMIC` classification make `transmit_eligible` false.
A local file is still allowed when the operator explicitly writes one; it
never leaves the host through BioNexus.

Inspect the current policy with `bionexus deploy telemetry --json`.
