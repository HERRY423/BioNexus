# 本轮交付与证据边界

2026-09-10，本地开发工作区。保留此前修改与实验结果；本轮未发布版本、联系实验室或产生专家科学标签。

本轮完成了外部任务比较、完整人工成本和可纠错治理的可执行实现。**尚未证明外部任务错误率下降或实验室获得净收益。** 实际核查本地 `validation/ivn/REGISTRY.json`，`lab_studies`、`reviews`、`calibration_freezes` 均为 0。

## 已完成

| 要求 | 实现及可核查行为 |
|---|---|
| 外部任务同时降低两类错误 | 冻结全体任务与源码摘要；观察文件绑定计划；参考与产品分开；至少两个具名、声明独立且盲法的参考审阅者；开发重叠/合成任务排除并保留；缺失、失败、争议不可消失；两类错误同时减少才显示描述性改善 |
| 实验室完整成本 | 原流程/辅助流程各包含安装、审阅、误报处理、修复、沟通；未知不补零；按实际外部队列核对实验室安装总账；负收益保留；质量与时间综合改善标记同时要求双重错误减少和完整人工成本节省 |
| 可纠错科学治理 | 修复未声明范围被当作普适、平台子串误匹配及忽略特征数/组织限制；改票保留历史理由；旧验证不能认证新票；专家分歧持续待审；注册表差异形成历史报告复核队列，保留旧字节与未知适用性 |

`de-pilot-summary` 从 v1 升至 v2，明确区分旧的部分成本与双臂完整人工成本。`review.v1` 和 `bundle.v1` 保持可读。新功能可由当前源码的 `python -m bionexus.de_external_study` 与 `python -m bionexus.rule_impact` 使用。完整操作、字段、迁移与局限见 [执行指南](../../docs/external-gain-and-correctable-governance.zh-CN.md)。

## 实际验证

- 针对性与相关兼容测试：**104 passed，1 skipped**。跳过为当前 Windows 环境无法创建测试符号链接；没有将跳过算通过。
- 覆盖拒绝全部、接受全部、技术失败、删除登记任务、参考分歧、开发人员冒充参考、参考看到结果后补填、错误任务绑定、源码漂移、重复记录、负成本、缺成本、安装分摊不平、改票复用验证、历史报告损坏等路径。
- Ruff 检查通过；`git diff --check` 通过；注册表与插件镜像一致性检查通过；旧 DE 审阅包契约检查通过。
- 实际调用模板、汇总与影响清单入口完成 [run-01 本地演练](run-01/REHEARSAL.json)。仅用合成任务，外部任务计入数 0，创建专家标签 0，创建实验室计时记录 0；旧审阅包所有文件字节保持不变。
- 本轮未进行全量测试、干净机器安装、已安装插件验收或远端 CI/发布。上述结果不能代替这些检查。

测试命令：

```powershell
python -m pytest tests/unit/test_de_external_study.py tests/unit/test_rule_impact.py tests/unit/test_de_pilot.py tests/unit/test_rule_calibration.py tests/unit/test_de_bundle.py tests/unit/test_human_adjudication.py tests/unit/test_evaluation_contract.py tests/unit/test_scientific_semantics_governance.py -q -p no:cacheprovider
python scripts/registry_compiler.py --check
python scripts/check_de_bundle_contract.py
```

演练可使用一个不存在的新目录重复执行；不会覆盖旧结果：

```powershell
python review/external-gain-governance-2026-09-10/run_rehearsal.py review/external-gain-governance-2026-09-10/run-02
```

## 仍然没有关闭的缺口

1. **没有真实外部对照结果。** 本轮没有具备独立专家参考及完整人工成本的开发外任务，因此不能报告外部错误率改善幅度、统计显著性或实验室采用收益。标签、时间戳、身份及指纹对应的产物真实性仍须外部核查；本地表单一致不等于独立性。
2. **本轮没有校准 DE 科学判定阈值。** 当前源码仍有需要单独纠正和验证的执行事实绑定、定向声明核对问题：`de_audit.py` 仍会据执行记录声明识别供体聚合，并有 `warrant_res.is_fully_warranted or claim_ir.negated` 分支；极小 p 值的 BFA-001c 规则仍存在。本轮的外部任务汇总并没有修好这些判定路径，不能据此宣称上一轮科学挑战集的问题已经解决。
3. **历史影响是待复核清单。** 当前只比较传入注册表与报告；没有规则命中记录不能证明未受影响，纯代码修订仍要通过现有源码依赖检查和维护者人工复核。系统不替具名科学负责人裁决，不自动更新规则。
4. **成本输出限于人工时间。** 未涵盖货币、设备、算力与科学错误的经济损失；当前比较是描述性观察，不是随机对照因果净效应。

接下来应先在开发集修复上述执行绑定与精确声明判断，并锁定新版本；随后由未参与开发的研究者使用冻结外部任务、保留所有争议与失败、填报两组完整成本。外部任务一旦用于规则修改，即成为开发信息，下一轮应换用新的留出任务。不要通过统一降低拦截强度来换取表面上的通过率。
