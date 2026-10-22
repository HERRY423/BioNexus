SYNTHETIC ENGINEERING EXAMPLE; no DE model executed.

## 声明成立条件的可执行验证

逐项产物检查；不构成科学授权或执行真实性认证。

### X-T — SATISFIED
Under the supplied model, X / T / disease versus control has a upward association in the analyzed cohort.

- artifact_results: EXTERNAL_RECORD_CHECKED / SATISFIED — Supply and bind the exact results artifact bytes.
- artifact_metadata: EXTERNAL_RECORD_CHECKED / SATISFIED — Supply and bind the exact metadata artifact bytes.
- artifact_design: EXTERNAL_RECORD_CHECKED / SATISFIED — Supply and bind the exact design artifact bytes.
- artifact_model: EXTERNAL_RECORD_CHECKED / SATISFIED — Supply and bind the exact model artifact bytes.
- model_binding: EXTERNAL_RECORD_CHECKED / SATISFIED — Model record binds result, metadata, design, formula, cell set and contrast.
- sample_alignment: ARTIFACT_EXTRACTED / SATISFIED — Every model row maps uniquely to the declared sample and donor.
- design_encoding: ARTIFACT_EXTRACTED / SATISFIED — Actual matrix equals the declared additive model encoded from sample metadata.
- contrast_identity: ARTIFACT_EXTRACTED / SATISFIED — Numeric contrast estimates numerator minus denominator, with nuisance terms zero.
- contrast_estimability: ARTIFACT_EXTRACTED / SATISFIED — Target contrast lies in the row space of the actual design matrix.
- model_rank: ARTIFACT_EXTRACTED / SATISFIED — Supported fixed-effect model is full rank with positive residual degrees of freedom.
- statistical_unit: ARTIFACT_EXTRACTED / SATISFIED — Model rows account for donor repetition under the supported design.
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
- Under the supplied model, X / T / disease versus control has a upward association in the analyzed cohort.
