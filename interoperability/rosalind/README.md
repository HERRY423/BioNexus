# BioNexus ChatGPT & Rosalind Adapter (BNS-022 / BNS-019)

The BioNexus Rosalind Adapter provides seamless interoperability between OpenAI ChatGPT (Custom GPTs / GPT Actions / Function Calling), Rosalind Bioinformatics Assistants, and the BioNexus epistemic reliability engine.

## Key Capabilities

1. **OpenAI Tool Calling Schema Export**:
   - Converts BioNexus canonical registry tools and scientific verification methods into standard JSON schemas consumable by OpenAI and ChatGPT actions.
2. **Cryptographic Tool Execution Receipts (`bionexus.tool-execution-receipt.v1`)**:
   - Automatically digests incoming request arguments (`request_sha256`) and tool execution outputs (`response_sha256`).
   - Issues a tamper-evident, hash-signed receipt for every tool call.
3. **Passive Evidence Intake & Warrant Checking**:
   - Maps raw tool outputs into structured `ExternalEvidenceEnvelope` objects across 6 scientific evidence families (`database`, `analysis`, `literature`, `structure`, `sequence`, `slide`).
   - Evaluates multi-modal claim packets against fail-closed claim ceilings without human confirmation or halluncinated evidence.

## Usage Example

```python
from bionexus.rosalind_adapter import (
    export_openai_tool_definitions,
    intake_chatgpt_tool_call,
    evaluate_rosalind_warrant,
)

# 1. Export tool definitions to register in ChatGPT Custom GPT Action
tools = export_openai_tool_definitions()

# 2. Intake tool call result from ChatGPT
result = intake_chatgpt_tool_call(
    tool_name="search_uniprot",
    arguments={"query": "P04637", "reviewed": True},
    raw_result={"entry": "P53_HUMAN", "gene": "TP53"},
)

# 3. Evaluate warrant for multi-envelope claims
evaluation = evaluate_rosalind_warrant(
    claim_id="CLM-001",
    target_claim="TP53 is a key regulator of the DNA damage response.",
    tool_results=[result],
    stated_maturity="SUPPORTED",
)
```
