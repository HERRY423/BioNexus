# rc.5 改进后复核与下一步

复核对象：`6f84745b47f07bf4bb5a2c3c95dbe5f732472218`，版本 `1.0.0-rc.5`。
日期：2026-09-06。开始检查时 Git status 无改动记录；本轮未修改产品代码。
本文件补充而不覆盖 rc.4 的 REPORT.zh-CN.md 和 probe-results.json。

## 已确认改进

- 原公开 pseudobulk API 的三供体 + is_interventional=True 反例现在返回
  SUPPORTED / causal_claims_allowed=False；因果升级不再只由干预标志触发。
  仍需把后续设计/离散度/识别布尔声明接到实际证据。
- batch_corrected 不再自动提供 confound_controls，parameter_sweep 不再自动提供 effect_stability。
- 原含 pseudobulk 的 TODO 注释不再消除 BFA-001；但普通字符串仍能消除它。
- 解析器保留显式 population_effect 并记录与文本推断的冲突，MCP 源码已传入对应字段。
  本轮只验证直接解析器，不把它说成已完成新版真实宿主复现。
- 新 audit-de 接受常用输入、生成问题定位和 PI 决策项，产品场景更明确。
- Evidence Debt 已明确解释为启发式结构优先分，不等同实测风险下降。

## 本轮执行结果

相关既有测试：38 passed，Windows / Python 3.13.9；包括 test_de_audit、
test_evidence_index、test_pseudobulk_inferential_warrant、test_analysis_audit。
这是定向测试，不代表完整支持矩阵或独立生物学验证。

### 反例 A：新审计入口的缺失证据被当成通过

`audit_differential_expression()`、空 DE 表、仅一行 pvalue/padj 表、仅 claim_text，
均返回 ROBUST_PASS / passed=True。无输入时仍生成声称已执行 pseudobulk 和
empirical Bayes moderation 的 Methods（供体数为 0）。

仅输入六名供体、A/B 各三名的 sample sheet，未提供矩阵、模型或 DE 结果，
返回 ROBUST_POPULATION；推荐 Methods 声称已执行 NB GLM、Wald 和 BH。
因此不是单纯状态命名不佳，而是生成了无运行依据的方法学陈述。

位置：src/bionexus/de_audit.py:456、846、880、899。
验收：缺必要输入为 NEEDS_DATA/NOT_ASSESSED；每项检查有 assessed/unknown；
Methods 的过去时事实只来自执行记录；建议分析与已完成分析分开。

### 反例 B：常见 Scanpy 结构被读坏

使用官方文档规定的 structured ndarray 形状构建两行输入：IFITM1、STAT1，
pvals 为 0.001/0.01，padj 为 0.01/0.03，logFC 为 2/1。
`_extract_de_from_anndata_uns` 返回基因 I、S，pvalue/padj/log2fc 全部 null。
这是结构化夹具解析探针，没有重跑生物学分析。

位置：src/bionexus/de_audit.py:947。
验收：使用官方提取接口或正确读取 structured array；标识符和数值逐项保持一致；
解析错误不可吞掉后作为空表继续给出通过。
官方格式：https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.rank_genes_groups.html

### 反例 C：证据索引尚未验证哈希

正常 --check 返回 PASS（27 checks）。在内存中把索引内 19 个 source_files
预期摘要全部替换为 64 个零，verify_index_integrity 仍返回 PASS（27 checks）。
没有修改磁盘索引或证据文件。实现只检查报告和源码是否存在。

位置：src/bionexus/evidence_index.py:701。
验收：逐文件重新计算摘要；报告结论从对应版本报告中读取并校验；
不得在 --impact 前重新生成基线导致变化被接受为当前基线；历史执行不能靠改版本字段更新。
源码还存在硬编码 verdict、指标和 real_host_certified=True，需要逐一建立来源或降为未核实。

### 反例 D：静态审计的字符串绕过仍在

原始 sc.tl.rank_genes_groups(adata, groupby='condition') 返回 BFA-001/BFA-003。
加入 # TODO: pseudobulk later 后仍拒绝（已修好）。
加入 note = 'pseudobulk later' 后 BFA-001 消失，passed=True。
验收应覆盖注释、字符串、docstring、变量改名、未调用函数和实际数据流。

LIMS 模块与上轮源码 SHA-256 完全一致；上轮空测量默认填值与直接网络路径的问题
本轮没有新的关闭证据。应在试点范围内修复，或明确隔离该入口。

## 发布事实与阻断

- 主 CI 34023046935：failure。日志显示旗舰报告 rollup 仍为 rc.4，
  自动同步成 rc.5 后触发 git diff gate，后续依赖作业受阻。
- Release 34023057459：failure；1324 passed、3 failed、1 skipped。
  失败包括 test_evidence_index、版本一致性与 validation verifier：
  报告仍为 rc.4/源码快照不符、CI 缺真实数据、cross-host/antigravity/REPORT.json 缺失。
  后者本地存在，但 Git 跟踪清单只有该目录 README.md 和 REQUEST.json。
- tag container 34023071673：上传 bionexus.sif 时 HTTP 422；
  不能把这一上传失败描述为容器计算未通过。同 SHA 的另一 container run 成功。
- rc.5 prerelease 页面存在，不代表发布工作流验收通过。

链接：https://github.com/HERRY423/BioNexus/actions/runs/34023046935
https://github.com/HERRY423/BioNexus/actions/runs/34023057459
https://github.com/HERRY423/BioNexus/actions/runs/34023071673

## 建议只完成三个里程碑

1. 修复新增入口的缺证据正向授权、Methods 生成、真实格式解析与索引校验；
   加上述反例，不增加新的规范或能力。核查 p<1e-100 的启发式只能提示疑点，
   不能仅凭数值把正确供体级检验判为伪重复；阴性结果也不能自动成为方法缺陷。
2. 在干净检出/发行包中完成 main 和 release 验证；区分历史报告与新执行，
   对真正受影响的计算重新执行。公共数据显式获取并验证摘要，缺失就明确失败；
   不要仅全局替换 rc.4 为 rc.5。修正发行资产上传问题，保留失败历史，后续补丁用新标签。
3. 先让一位非作者分析者在自己的机器上审计 5–10 个历史包：正确设计、伪重复、
   完全混杂、诚实阴性结果、缺信息各有代表；记录误报/漏报、未知、耗时和维护者救场。
   把它当可用性与发现失败案例的试点，不能据此声称总体准确率或获批校准。

外部研究、非作者评审、校准冻结注册列表本轮仍为空。第一步应是获得一个可复核的外部
使用闭环，不必先搭更大的验证网络。后续扩大样本量与实验室数量需另作统计设计。
