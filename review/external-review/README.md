# BioNexus independent-review handoff

This packet supports one bounded, non-author review of
`scrna.pseudobulk_de`. It separates the reviewer-controlled evidence from the
maintainer-controlled IVN ledger record and uses a two-phase, hash-bound
pre-output lock.

It can establish technical reproduction and a named scientific judgment. It
cannot establish external-lab quota credit, biological truth, clinical or
regulatory fitness, certification, or endorsement of BioNexus as a whole.

## Phase 1: pre-output lock

Before cloning the repository or viewing CI, reports, expected verdicts, or
BioNexus output:

1. Read `BLINDING_PROTOCOL.md` and only the methods-only
   `BLINDED_REVIEW_PACKET.json`.
2. Record the packet SHA-256.
3. Copy `PREOUTPUT_ASSESSMENT_TEMPLATE.json` to
   `PREOUTPUT_ASSESSMENT.json`, fill every field, record an ISO-8601 lock time,
   sign it by name, and compute its SHA-256.
4. Retain the completed file unchanged. If outputs were already seen, set the
   blinding claims to `false`; the review remains useful but does not satisfy
   the blinded-review quota.

## Phase 2: immutable reproduction

The invitation supplies a full 40-character commit SHA and a unique review
ID. Never substitute `main` or another movable ref.

macOS/Linux (replace the two placeholders):

```bash
REVIEW_COMMIT="__IMMUTABLE_REVIEW_COMMIT__" REVIEW_ID="BN-IVN-REV-001" && \
test "${#REVIEW_COMMIT}" -eq 40 && \
git clone https://github.com/HERRY423/BioNexus.git BioNexus-IVN-review && \
cd BioNexus-IVN-review && git checkout --detach "$REVIEW_COMMIT" && \
python3 -m venv .venv && . .venv/bin/activate && \
python -m pip install --upgrade pip && \
python -m pip install -e ".[review]" && \
python review/external-review/build_review_capsule.py \
  --expected-commit "$REVIEW_COMMIT" --review-id "$REVIEW_ID"
```

Windows PowerShell:

```powershell
$reviewCommit = '__IMMUTABLE_REVIEW_COMMIT__'
$reviewId = 'BN-IVN-REV-001'
if ($reviewCommit.Length -ne 40) { throw 'A full immutable commit SHA is required.' }
git clone https://github.com/HERRY423/BioNexus.git BioNexus-IVN-review
Set-Location BioNexus-IVN-review
git checkout --detach $reviewCommit
py -3 -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -e '.[review]'
& .\.venv\Scripts\python.exe review\external-review\build_review_capsule.py `
  --expected-commit $reviewCommit --review-id $reviewId
```

The builder refuses a dirty or mismatched checkout and refuses to start if the
bounded review dependency is absent. It records focused verifier-contract
tests, manifest drift checking, certification output, IVN status/integrity,
complete logs, and a resolved `pip freeze --all` environment snapshot. Failed
checks remain evidence; they are not hidden. The environment snapshot is not
a cross-platform lockfile.

## Reviewer return packet

Inspect `SUMMARY.json`, `ENVIRONMENT.json`, `PIP_FREEZE.txt`, and every log in
the ZIP. Copy `SIGNOFF_TEMPLATE.json` to `REVIEW.json` and fill every field.
Allowed verdicts are `ENDORSED`, `ENDORSED_WITH_LIMITS`, and `CHALLENGED`.
Return these two unchanged, reviewer-authored artifacts through a pull request
or another provenance-preserving channel:

- `PREOUTPUT_ASSESSMENT.json`
- `REVIEW.json`

Blank, informal, or maintainer-rewritten responses are never converted into a
verdict.

## Maintainer registration and governed promotion

The reviewer artifact is not a ledger payload. Create a separate record from
`validation/ivn/templates/INDEPENDENT_REVIEW.template.json`, copying only the
matching identity, subject, verdict, attestation, timestamps, and artifact
path. Keep `status=REGISTERED` and both receipt fields empty.

```bash
bionexus ivn register-review \
  --payload validation/ivn/reviews/BN-IVN-REV-001/LEDGER_RECORD.json \
  --repo-root .
bionexus ivn verify-review \
  --review-id BN-IVN-REV-001 \
  --expected-commit __IMMUTABLE_REVIEW_COMMIT__ \
  --verified-by "NAMED_MAINTAINER_OR_GOVERNANCE_BODY" \
  --repo-root .
bionexus ivn verify --repo-root .
bionexus ivn status --repo-root . --json
```

Registration always forces `REGISTERED`, even if an incoming ledger payload
claims otherwise. `verify-review` checks author-roster exclusion, the frozen
review SHA, two-phase blinding artifacts and timestamps, commit/capsule
provenance, disclosures, substantive review fields, and signature. It then
creates a separate hash-bound verification receipt and promotes the ledger
record. Any missing or mismatched condition refuses the transition.

The reviewer files must never be edited to improve a verdict. A correction
must arrive as a new reviewer-authored artifact and be registered through an
explicit supersession process.
