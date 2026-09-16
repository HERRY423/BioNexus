# 外部先导启动包

## 当前状态

`attempt-03/PILOT_STATUS.json` 是机器可读的诚实状态。当前真实外部任务、外部站点、合格双审阅任务
和完整成本记录均为 0；因此先导尚未执行。此目录只表示启动材料和本地校验已准备。

## 外部保管者操作顺序

1. 阅读 `PROTOCOL.zh-CN.md`，确认任务、站点、审阅者均符合独立性条件。
2. 为每个真实任务填写 `attempt-03/TASK_INTAKE_TEMPLATE.json`，计算数据集和任务包 SHA-256。
3. 把任务写入 `attempt-03/PLAN_TEMPLATE.json`，设置冻结时间；在外部受控位置保存计划摘要。
4. 用生产命令生成观察表：
   `python -m bionexus.de_external_study template --plan PLAN.json --out OBSERVATIONS.json`
5. 两名参考审阅者分别填写 `REFERENCE_REVIEW_TEMPLATE.json`，并在任何臂完成前冻结。
6. 操作员填写 `ARM_OUTPUT_TEMPLATE.json` 和 `COST_LOG_TEMPLATE.csv`；未完成项保持缺失。
7. 用生产评分器生成摘要，并传入外部保存的计划摘要：
   `python -m bionexus.de_external_study score PLAN.json OBSERVATIONS.json --expected-plan-sha256 <sha256> --out SUMMARY.json`
8. 发布时同时提供计划、观察、摘要、原始分歧、排除理由和匿名化成本记录。

不得向受测产品或操作员提供参考标签。不得把本地 54 例、模板校验或 ZIP 哈希写成外部完成证明。
