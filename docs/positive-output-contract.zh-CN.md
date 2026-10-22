# 证据状态与正向输出契约 v1（P0-A 候选）

本契约限定现有 EvidenceCard、Warrant/Policy、DE 审计与外部证据结果的解释。它不建立第二套账本，不认证科学事实，不激活 GA 支持。`scientific_authorization` 固定为 `NONE`，`scientific_facts_verified` 固定为 `false`。

## 消费者先读取什么

机器结果的 `evidence_contract` 是正向输出的解释入口。先核对版本、枚举、入口清单和状态一致性，再使用具体输出。不能仅凭旧字段 `passed`、`is_fully_warranted`、`claim_warranted`、`SUPPORTED`、`ROBUST`、`REPLICATED`、`ALLOW` 或退出码 0 推断科学有效性。

```python
from bionexus.evidence_contract import interpret_positive_output

decision = interpret_positive_output(result.to_dict(),
    surface="python:bionexus.de_audit.audit_differential_expression")
# decision["positive"] 仅代表 decision["basis"] 和 decision["scope"] 所限定的结果。
# scientific_facts_verified=False; scientific_authorization=NONE
```

`validate_evidence_contract` 校验字段、版本和状态关系；`contract_schema` / `data/evidence-state.v1.schema.json` 提供结构模式。校验通过只说明契约一致，不证明发送者声明属实。拒绝未知版本、未知枚举、额外状态字段，以及不一致的正向状态。`interpret_positive_output` 进一步拒绝未接入入口、缺失契约和借用其他入口的支持级别。

## 各类正向结果的含义

| assessment_kind / positive_basis | 可以陈述 | 不能由此推断 |
|---|---|---|
| CONDITIONAL / DECLARED_PREMISES | 如果所填条件成立，规则计算满足相应条件；可保留声明的条件上限 | 声明为真、执行已发生、独立验证完成 |
| ARTIFACT_REVIEW / CHECKED_ARTIFACTS | 所列文件或内存产物的具体检查结果，包含有限阴性、局部观察、部分 NA | 供体身份真实、原分析确实运行、总体或因果结论成立 |
| BUNDLE_INTEGRITY / CONSISTENT_BYTES | 固定文件的摘要与清单一致 | 文件作者可信、分析正确、审查者独立 |
| EXTERNAL_REVIEW / BOUND_RESPONSE_AND_DECLARED_REVIEW | 成功状态回执与请求/响应绑定，且存在声明的人工审查关系 | 远端执行得到独立认证、审查者身份真实、跨工具等于独立科学重复 |
| UNACCEPTED / NONE | 保留原始材料，不能按本契约接受其正向输出 | 其他模块已获核心支持或验证 |

`input_integrity`、`analysis_execution`、`premises`、`human_review`、`reviewer_identity`、`independence` 分别记录。`SUCCESS_REPORTED_AND_BOUND` 特意限定为“回执报告成功且内容绑定”，不等于验证真实执行。具名审查仍是 `RECORDED_UNAUTHENTICATED` / `DECLARED`；本候选没有独立性认证器，`independence` 保留 `UNKNOWN`。

## 状态转换规则

| 输入变化 | 可发生的状态变化 | 禁止的变化 |
|---|---|---|
| 增加合法布尔声明、供体数、等级 | 条件规则可能从 RESTRICTED 到 POSITIVE | input_integrity / execution / independence 变为已核验 |
| 完成所列产物检查 | 增加 observations；可得到限定范围的产物正向结果 | 自动认证产物来源与科学解释 |
| 回执缺失、被篡改、响应为空、失败或等待中 | 外部支持被限制；声明的审查原文保留 | 失败证据升级为支持 |
| 同一证据重复或枚举/版本未知 | 拒绝或限制相应结论 | 重复次数增加证据强度 |
| 新增具名审查 | 记录审查与身份声明来源 | 自动认证身份或独立性 |
| 独立性未知，但已有合法单次观察 | 保留单次范围的检查或条件结论 | 一律弃权，或宣称已独立重复 |
| 概率全部不可估计、布尔/复数/非有限值 | 禁止 DE 正向审计；保留失败原因 | 当成“没有差异” |
| 合法部分 NA / 有限阴性结果 / 数字字符串 | 在其他必要条件满足时保留窄结论 | 将 NA 填零或扩大到“无生物效应” |

非有限诊断数值在 JSON 中记录为 `{"numeric_state":"NONFINITE","representation":"inf"}` 等标签，避免非法 JSON；原始输入与内存诊断保留。不将其改为零或普通空值。

## 入口和版本边界

`data/positive-output-surfaces.v1.json` 列明 CLI、MCP 和包顶层公开入口，加上此次接入的模块入口。未接入项及未知入口默认为 `UNACCEPTED`，不因共享 EvidenceCard 或包版本获得支持。`CANDIDATE_CORE` 仅表示本地候选契约覆盖；`EXPERIMENTAL` 不构成原生宿主验收。

CLI 的 `audit-de`、`audit-de-verify`、`audit-de-summary`，Python 对应结果，及其 Markdown/JSON 消费者使用相同契约文本或字段。条件引擎、路由、MCP preflight、Rosalind 与生态证据转换保留实验性边界。`ALLOW` 仅表示部署干预规则，不表示科学授权。

字段 `rule_revision=positive-output-v1` 和 `implementation_revision=p0a-1` 标识这份解释契约的规则与实现修订，**不代表全部领域规则或整个源码的版本**。完整源码身份以候选 `CANDIDATE.json`、源码摘要和 wheel 摘要为准。包版本仍为现有 RC；不把版本号升级、干净机器部署或实验室收益验收并入 P0-A。

## 历史与迁移

旧记录不改写。历史 bundle 可以继续做字节一致性检查；无 `evidence_contract` 时，`stored_audit_contract` 为 UNACCEPTED，不补造科学前提。新 bundle 将契约与 audit.json 一起绑定进摘要。读取器将“存储的生产者声明”与“本次文件一致性结果”分开。

保留条件计算旧字段以兼容既有调用；新增 `legacy_field_semantics` 与每层条件来源，文本入口也明示条件性。只读取旧成功位的消费者需要迁移至上面的门禁函数；本候选不将这些旧消费者算作已验收。缺失或未知契约不得自动按当前默认值升级。

## 验证范围

回归使用合成输入，覆盖正向与反向路径、JSON/报告/文件往返和未接入入口拒绝。独立上下文另行设计探针；失败与复验记录保留在 P0-A 审查目录。时间戳如 `evaluated_at`、`created_at` 不参与结果字段逐字比较，契约本身不含时间戳。没有运行真实实验室试点、外部科学验证、远端服务或宿主验收。
