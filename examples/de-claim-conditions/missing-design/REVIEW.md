SYNTHETIC ENGINEERING EXAMPLE; no DE model executed.

## 声明成立条件的可执行验证

逐项产物检查；不构成科学授权或执行真实性认证。

### X-T — NOT_ASSESSED
Under the supplied model, X / T / disease versus control has a upward association in the analyzed cohort.

- artifact_results: EXTERNAL_RECORD_CHECKED / SATISFIED — Supply and bind the exact results artifact bytes.
- artifact_metadata: EXTERNAL_RECORD_CHECKED / SATISFIED — Supply and bind the exact metadata artifact bytes.
- artifact_design: MISSING / NOT_ASSESSED — Supply and bind the exact design artifact bytes.
  修复或补充：Export design and its SHA-256 in the contract.
- artifact_model: EXTERNAL_RECORD_CHECKED / SATISFIED — Supply and bind the exact model artifact bytes.
- model_binding: EXTERNAL_RECORD_CHECKED / NOT_ASSESSED — Model record binds result, metadata, design, formula, cell set and contrast.
  修复或补充：Supply result, metadata and design references before comparing the model binding.
- sample_alignment: MISSING / NOT_ASSESSED — Every model row maps uniquely to the declared sample and donor.
  修复或补充：Supply a bound model, numeric design and sample-level metadata.
- design_encoding: MISSING / NOT_ASSESSED — Actual matrix equals the declared additive model encoded from sample metadata.
  修复或补充：Supply a bound model, numeric design and sample-level metadata.
- contrast_identity: MISSING / NOT_ASSESSED — Numeric contrast estimates numerator minus denominator, with nuisance terms zero.
  修复或补充：Supply a bound model, numeric design and sample-level metadata.
- contrast_estimability: MISSING / NOT_ASSESSED — Target contrast lies in the row space of the actual design matrix.
  修复或补充：Supply a bound model, numeric design and sample-level metadata.
- model_rank: MISSING / NOT_ASSESSED — Supported fixed-effect model is full rank with positive residual degrees of freedom.
  修复或补充：Supply a bound model, numeric design and sample-level metadata.
- statistical_unit: MISSING / NOT_ASSESSED — Model rows account for donor repetition under the supported design.
  修复或补充：Supply a bound model, numeric design and sample-level metadata.
- result_identity: ARTIFACT_EXTRACTED / SATISFIED — Exactly one result row matches gene, cell set and ordered comparison.
- effect_direction: ARTIFACT_EXTRACTED / SATISFIED — Finite log2 fold change agrees with the requested direction.
- effect_uncertainty: ARTIFACT_EXTRACTED / SATISFIED — Reported interval at the requested level excludes zero in the claimed direction.
- adjusted_significance: ARTIFACT_EXTRACTED / SATISFIED — Reported adjusted p-value meets the explicit claim threshold.
- population_transport: MISSING / NOT_ASSESSED — Sampling and target-population transport assumptions need review.
  修复或补充：Provide claim-specific evidence for scientific review; declarations cannot satisfy this check.
- causal_identification: MISSING / NOT_ASSESSED — Intervention, confounding and identification assumptions need review.
  修复或补充：Provide claim-specific evidence for scientific review; declarations cannot satisfy this check.

当前支持的具体表述（限已检查范围）：
- The supplied table reports X / T / disease versus control: log2 fold change 1.2.
