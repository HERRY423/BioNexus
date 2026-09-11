# 多供体单细胞 DE：首轮实验室试点

**产品承诺：在投稿前审阅已有 DE 产物，指出可能影响声明的问题、证据缺口和最小修复，交由研究者裁决。**

减少无依据外推与节省审阅时间是待检验的目标。当前提供的是可记录、可复核的试点流程；空白表、内部演练和合成示例都不是已验证净收益。

## 试点边界与人员

建议先选两家实验室，每家约十个历史分析，用于发现接入和误报问题；这不是论文充分样本量。包含正确分析、真实错误、信息不足、诚实负结果和有效的配对/混合模型。按原研究与供体标记案例，避免把同一研究的多个结果视为独立研究。

指定实验室负责人、参考审阅人和发现复核人。推荐参考审阅人与 BioNexus 作者独立；软件不认证身份或独立性。先冻结案例清单、版本与纳入标准，保留所有失败、未完成和不愿复用的案例。此步骤由人员开展，不触发邀请或外联。

## 一次审阅怎么完成

1. 在原工作流保存 DE 表、样本表、拟写入论文的声明，以及已有的执行记录/脚本。给分析一个不含个人信息的 case_id。
2. 参考审阅人先看原始输入，填写 reference-review.json，只写真实确认的方法或声明问题；每个问题赋予 issue_id 和 description。空 issues 列表表示已经检查且没有确认问题，null 表示未完成。此文件不含 BioNexus 发现，不向参考审阅人发送 REVIEW.md、audit.json 或 review.json。
3. 使用 audit-de --bundle 生成新目录；可以先生成目录以取得空白参考模板，但参考审阅人看到审计发现后就不能声称盲法。
4. 参考审阅完成后，将 reference-review.json 中的三个字段复制到 review.json 的 reference_review。保留原参考文件。由复核人逐项判定 finding_judgments，不删除不喜欢的发现。
5. 记录计时和使用体验，所有发现都有人工判定后把 review_status 改为 COMPLETE。无法完成就保留 PENDING 并写原因。
6. 汇总时使用每个案例的一份最终记录。修复后重新审计请建新目录，保留旧记录；同一案例前后版本不要作为两个独立案例混入收益汇总。

软件默认只生成空白记录，不填人名、不伪造参考问题，也不自动批准科研结果。

## 最少需要填写什么

review.json 的 site_id 是实验室自定代号；reviewer_name 是实际复核人。参考审阅的 reviewer_name 和 reviewed_before_audit 也须如实填写。参考问题的 description 描述具体缺陷，不把单纯“信息没有提供”写成“分析肯定做错”。

| finding_judgments.judgment | 用法 |
|---|---|
| CONFIRMED | 人工确认发现成立，reference_issue_id 对应一个已确认参考问题，并填写 note |
| FALSE_ALARM | 人工确认误报，reference_issue_id 为 null，note 说明实际有效设计或证据 |
| UNRESOLVED | 尚不能确定，保留 note；可以关联尚未解决对应关系的参考问题 |

每个审计发现必须保留；完整评审不能缺项。若有新发现经人工确认，但原参考审阅未包含它，应保留原参考记录并标明参考补充的过程，不能倒填成事前已知或盲法发现；这类案例先保留 PENDING，单列复核，不能为凑指标改写参考标准。

汇总以“参考问题”为漏检分母：没有被确认检出、也没有被标为对应关系未解决的参考问题计为漏检。多条发现指向同一参考问题只计一次检出。误报按发现数计，二者不能混合成一个准确率。未解决发现和未解决对应关系单列。

## 用时和收益

| 字段 | 定义 |
|---|---|
| timing.baseline_review_minutes | 同一案例原流程的人工审阅时间；没有可靠记录时 null |
| timing.assisted_review_minutes | 使用 BioNexus 后，阅读、核对发现和负责人复核的总人工时间 |
| timing.setup_minutes | 本案例实际承担的安装、整理输入和接入时间；不要自动填零 |
| timing.repair_minutes | 根据本次复核修复分析或表述所用时间 |
| timing.comparison | 相同案例可配对为 PAIRED_SAME_CASE；不可配对为 UNPAIRED；未知为 null |
| author_help_count | 本案例需要作者帮助的次数，未知为 null |
| report_understood / claim_changed / would_reuse | 真实人工 yes/no；未回答为 null |

系统仅在配对两侧都有用时时计算“原审阅时间−辅助审阅时间”。进一步减去 setup 与 repair 需要两项都已测量。负数表示成本增加，原样保留。这是旧的部分成本指标，缺少双方误报处理、沟通等成本，不能称为完整净收益；配对案例还存在熟悉效应，回忆时间也存在偏差。

当前开发版新增 `costs` 双臂五项成本，汇总输出升级为 `de-pilot-summary.v2`。旧记录仍可读，但不会自动计为完整成本。正式外部任务应使用预先冻结全体任务的研究汇总，避免只汇总成功填写的审阅包。参见[外部增益与可纠错治理操作指南](external-gain-and-correctable-governance.zh-CN.md)。

病例选择、原始计时、独立性与身份不能靠 JSON 或哈希认证。汇总始终保留 net_benefit=NOT_ESTABLISHED；真实的采用决定应同时查看错误率、漏检、未解决项、时间与复用意愿。不能把少数填完的正面案例代替所有入组案例。

```bash
bionexus audit-de-summary lab-a-001/review.json lab-b-001/review.json --out pilot-observations.md
bionexus audit-de-summary lab-a-001/review.json lab-b-001/review.json --json --out pilot-observations.json
```

缺失值不补零；PENDING 和合成示例排除并列出原因；重复案例、报告哈希变更、非法时间、缺项判定会拒绝汇总。输出文件必须是新文件。

## 何时继续、调整或暂停

试点开始前由负责人约定可接受误报、关键漏检和用时范围。若正确分析频繁被误报、严重问题持续漏检或净复核成本增加，应调整规则/呈现后重试并保留旧结果。只有出现可重复的实际收益，才讨论扩大人群和任务范围。研究者的科学裁决、试点采用决定、正式外部验证分别记录。
