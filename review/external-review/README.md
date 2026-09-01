# BioNexus independent-review handoff

This directory is the external handoff for the first human IVN review. It is
deliberately narrower than an external-laboratory replication.

## What this packet can establish

- A reviewer reproduced a fixed Git commit and retained all pass, fail, and
  abstention outputs in a SHA-256-bound capsule.
- A named non-author documented an independent scientific judgment about the
  `scrna.pseudobulk_de` rules and claim ceiling.
- The signed review can be registered in the IVN without the maintainer
  rewriting the reviewer's conclusions.

It does **not** establish external-lab quota credit, biological truth,
certification, clinical validity, or endorsement of BioNexus as a whole.
The portable capsule excludes the repository-wide positive artifact test that
requires separately retained flagship annotation and spatial data files; its
fail-closed verifier tests remain included. This exclusion is recorded in the
capsule summary rather than being treated as a pass.

## Maintainer preparation: mandatory before outreach

1. Commit the implementation and documentation changes.
2. From that committed source state, run
   `python scripts/sync_flagship_reports.py`, then rerun the validation verifier
   and commit the provenance-only report rebinding. Do not rebind reports while
   the source changes are uncommitted: that would falsely pair a dirty source
   snapshot with the previous commit identity.
3. Push the final review commit to the public repository.
4. Select that full 40-character commit SHA. Do not use `main` or a movable
   branch name.
5. Keep the invitation drafts pinned to the immutable review commit below.
6. Run the command yourself from a fresh clone and retain the resulting hash.
7. Assign a unique review ID. The first proposed ID is `BN-IVN-REV-001`.
8. Confirm the intended reviewer is absent from
   `validation/ivn/REGISTRY.json` `author_roster`.

## One-click reproduction command

macOS/Linux:

```bash
REVIEW_COMMIT="339cefb98643d5e9bd2483c44469481fed7a31f6" && \
test "${#REVIEW_COMMIT}" -eq 40 && \
git clone https://github.com/HERRY423/BioNexus.git BioNexus-IVN-review && \
cd BioNexus-IVN-review && \
git checkout --detach "$REVIEW_COMMIT" && \
python3 -m venv .venv && \
. .venv/bin/activate && \
python -m pip install --upgrade pip && \
python -m pip install -e . && \
python review/external-review/build_review_capsule.py \
  --expected-commit "$REVIEW_COMMIT" \
  --review-id BN-IVN-REV-001
```

Windows PowerShell:

```powershell
$reviewCommit = '339cefb98643d5e9bd2483c44469481fed7a31f6'
if ($reviewCommit.Length -ne 40) { throw 'A full immutable commit SHA is required.' }
git clone https://github.com/HERRY423/BioNexus.git BioNexus-IVN-review
Set-Location BioNexus-IVN-review
git checkout --detach $reviewCommit
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e .
& .\.venv\Scripts\python.exe review\external-review\build_review_capsule.py `
  --expected-commit $reviewCommit `
  --review-id BN-IVN-REV-001
```

The capsule builder refuses a dirty checkout or a mismatched commit. It runs
focused pseudobulk/IVN checks, certification reporting, artifact verification,
and IVN status/integrity checks. Non-zero checks are recorded and packaged
instead of discarded.

## Reviewer action

1. Run one command above.
2. Inspect `SUMMARY.json` and every log inside the generated ZIP.
3. Copy `SIGNOFF_TEMPLATE.json` to `REVIEW.json`.
4. Fill every identity, disclosure, reproduction, scientific-review, verdict,
   and signature field. Keep `status` as `REGISTERED`; do not claim
   `VERIFIED` merely because the form is complete.
5. Return `REVIEW.json` through a reviewer-authored pull request or another
   provenance-preserving channel. Negative and partial reviews are valid.

Allowed IVN verdicts are `ENDORSED`, `ENDORSED_WITH_LIMITS`, and `REJECTED`.
The reviewer may also decline to submit the packet. Never translate a blank or
informal response into a verdict.

## Maintainer registration after receipt

Place the unchanged reviewer artifact at the `review_path` stated in the JSON,
then register it:

```bash
bionexus ivn register-review \
  --payload validation/ivn/reviews/BN-IVN-REV-001/REVIEW.json \
  --repo-root .
bionexus ivn verify --repo-root .
bionexus ivn status --repo-root . --json
```

Registration computes and stores the artifact SHA-256, but `REGISTERED` still
does not count. Promotion to `VERIFIED` requires a separate, documented check
of non-authorship, the actual blinding protocol, the attestation, the review
artifact hash, and the reviewer-controlled signature. If any condition is
missing, leave the record `REGISTERED` and report the gap.

After a justified status transition, rebuild and inspect the ledger:

```bash
bionexus ivn verify --repo-root .
bionexus ivn status --repo-root . --json
bionexus ivn build-ledger --repo-root . --output docs/ivn/index.html
```

The signed JSON must never be edited by the maintainer to improve its verdict.
Any correction must come from the reviewer as a new, attributable artifact.
