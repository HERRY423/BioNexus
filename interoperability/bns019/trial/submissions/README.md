# Trial submissions

Submit one directory named after a stable `submission_id`:

```text
submissions/<submission_id>/submission.json
results/<submission_id>.json
```

The submission must validate against `../schemas/submission.schema.json`; the
result must bind the exact BNS-019 version and release digest in
`../trial-manifest.json`. Include the implementation repository and immutable
commit, the exact execution command and environment, and the SHA-256 of the
result artifact.

BioNexus maintainers may reproduce, reject, or mark a submission incomplete.
Acceptance means only that the submitted software-contract result was publicly
reproduced. It does not award a badge or certify scientific validity.
