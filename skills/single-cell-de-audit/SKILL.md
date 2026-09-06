---
name: single-cell-de-audit
display_name: "Multi-Donor Single-Cell DE Evidence Audit"
description: Evidence audit for multi-donor single-cell differential expression before lab meetings, manuscript submission, or data sharing. Users keep Scanpy, Seurat, or existing workflows; BioNexus audits pseudoreplication, donor replicates, donor cell imbalance, batch confounding, raw count layers, and FDR compliance, returning the 5 essential pillars (issues affecting conclusion, sample/step/claim mapping, minimal actionable fix, permissible claim scope, and PI one-time decisions).
tier: core
grade: gold-wrapper
status: canonical
backend: "bionexus.de_audit"
---

# Multi-Donor Single-Cell DE Evidence Audit (`single-cell-de-audit`)

> [!NOTE]
> **Lab-First High-Yield Workflow**: This skill transforms BioNexus adoption into an immediate, high-yield research review stage:
> **多供体单细胞差异表达，在组会、投稿或共享前的证据审计**。
> Researchers continue using their preferred workflows (Scanpy, Seurat, R, Nextflow, or custom scripts). BioNexus receives existing analysis artifacts and returns concrete, actionable scientific answers.

---

## 🎯 When to Use This Skill

Activate this skill whenever:
1. **组会汇报前 (Before Lab Meetings)**: A researcher wants to verify whether candidate differential genes stand up to scrutiny or if they are false discoveries driven by pseudoreplication / single-donor dominance.
2. **论文投稿前 (Before Manuscript Submission)**: Preparing scRNA-seq differential expression results for peer review (Nature, Cell, Genome Biology, bioRxiv) and ensuring methodology avoids standard reviewer rejection traps.
3. **数据或分析移交共享 (Before Data Sharing / Consortium Handoff)**: Auditing external or collaborator-provided single-cell DE results, sample designs, or code before building downstream wet-lab validation campaigns.

---

## 📥 Accepted Inputs (Zero Migration Friction)

BioNexus does NOT require scientists to rewrite code or declare complicated metadata files. It directly accepts:
- **Single-cell count objects**: Scanpy `.h5ad` or objects with cell metadata (`obs`).
- **Differential expression tables**: `.csv` / `.tsv` results from Seurat `FindMarkers`, Scanpy `rank_genes_groups`, PyDESeq2, edgeR, or DESeq2.
- **Sample design sheets**: `.csv` / `.tsv` detailing donor ID, condition, batch, and covariates (or automatically parsed from `adata.obs`).
- **Analysis scripts / notebooks**: `.ipynb`, `.py`, `.R`, `.Rmd`.
- **Target scientific claim statements**: Manuscript text or proposed conclusions.

---

## 🚀 Quick Start (CLI & Python)

### 1. Command Line Interface

```bash
# Scenario A: Audit AnnData object directly (auto-detects obs metadata, matrix layers, and rank_genes_groups)
bionexus audit-de data.h5ad -o audit_report.md

# Scenario B: Audit precomputed DEG table + sample sheet before submission
bionexus audit-de --de-table de_results.csv --sample-sheet samples.csv -o audit_report.md

# Scenario C: Full audit of AnnData + DE results + Jupyter Notebook + Claim statement
bionexus audit-de data.h5ad \
    --de-table de_results.csv \
    --script analysis.ipynb \
    --claim "IFITM1 is a validated population-level biomarker for disease severity" \
    --out audit_report.md
```

### 2. Python API

```python
from bionexus import audit_differential_expression

result = audit_differential_expression(
    adata=adata,                 # or adata_path="data.h5ad"
    de_table=de_results_df,      # or de_table="de_results.csv"
    sample_metadata=samples_df,  # or sample_metadata="samples.csv"
    code_path="analysis.ipynb",  # optional script / notebook
)

# Print human-readable terminal report with ANSI colors
print(result.summary_text(use_color=True))

# Save publication-ready Markdown report
Path("audit_report.md").write_text(result.to_markdown(), encoding="utf-8")
```

---

## 📊 The 5 Essential Pillars Returned (五大核心产出)

| 产出维度 | 科学含义与实验室价值 | 输出形式 |
| :--- | :--- | :--- |
| **1. 哪个问题会影响当前结论** | 区分致命阻断（伪重复、N=1、完全批次混杂）、高影响偏差（单供体主导、未校正FDR）、方法学建议 | 分级警示卡（BLOCKER / HIGH_IMPACT / ADVISORY）及机制解释 |
| **2. 问题对应哪个样本、步骤或声明** | 精确定位到具体供体 ID、代码调用行、或具体受损的科学论断 | 定位映射表（涉及样本、涉及代码步骤、涉及文稿声明） |
| **3. 最小修复是什么** | 提供最小改动量、可直接复制粘贴运行的修复代码或过滤方案 | 可直接执行的 Python/R 脚本片段 |
| **4. 当前可以陈述到什么范围** | 明确划分允许陈述的科学边界与严禁越界的推断范围 | 规范边界声明 + 推荐可用的 Methods/Results 英文段落 |
| **5. 哪些分歧需要负责人一次性裁决** | 提炼出 1~3 个必须由导师/PI 裁决的方法学权衡问题 | 结构化选项 A/B 与权衡利弊分析 |

---

## 🛡️ Scientific Grounding & Non-Negotiables

- **Squair et al. (2021) Nature Communications**: Single-cell pseudoreplication (treating cells as biological replicates) inflates nominal false discoveries by up to 90%. Condition-level DE requires donor-level replicate aggregation (Pseudobulk) with $N \ge 3$ biological replicates.
- **BN-F001**: Count models (PyDESeq2 / edgeR) strictly require discrete raw integer counts. Passing log-normalized floats invalidates negative binomial dispersion modeling.
- **BN-F006**: Complete confounding between condition and technical batch cannot be rescued mathematically without orthogonal validation or balanced resequencing.
