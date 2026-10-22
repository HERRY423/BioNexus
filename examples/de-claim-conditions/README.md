# Executable DE claim prerequisites — synthetic acceptance examples

All three packages have byte-identical DE results. No biological analysis was
executed to produce them; they are engineering fixtures, not research evidence.

| Package | Design | Expected cohort conditions | Table observation |
| --- | --- | --- | --- |
| `valid` | Independent donors, crossed batches, estimable contrast | `SATISFIED` | `SATISFIED` |
| `confounded` | Batch identical to condition | `UNSATISFIED` | `SATISFIED` |
| `missing-design` | Design reference omitted | `NOT_ASSESSED` | `SATISFIED` |

In the last package `design.csv` is retained as background, but its existence
cannot substitute for a bound reference. Each `expected-report.json` captures the
local run, including checker and schema digests; it does not authenticate execution.

From the repository root:

```python
from bionexus.de.conditions import verify_de_claim_conditions

for case in ("valid", "confounded", "missing-design"):
    report = verify_de_claim_conditions(f"examples/de-claim-conditions/{case}/contract.json")
    print(case, report["status"], report["claims"][0]["supported_statements"])
```

For the full audit and an exportable review:

```bash
bionexus audit-de --de-table examples/de-claim-conditions/valid/results.csv --sample-sheet examples/de-claim-conditions/valid/metadata.csv --claim-contract examples/de-claim-conditions/valid/contract.json --bundle review-claim-example
```

The full audit has additional missing evidence and returns exit code 1. Its
`claim_conditions` section independently reports the bounded prerequisite result.
See the [scope and input contract](../../docs/executable-claim-conditions.zh-CN.md).
