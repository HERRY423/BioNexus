# 第一次投稿前 DE 影子审阅

首个产品承诺：接收已有多供体单细胞差异表达产物，指出可能影响声明的问题、缺失证据和最小修复，交由研究者复核。减少错误外推与节省时间尚待实验室试点验证。

## 先体验一份报告

在当前源码目录安装核心包（表格审计不需要 Scanpy、GPU 或分析后端）：

```bash
python -m pip install -e .
bionexus audit-de --demo --bundle review-demo
```

打开 review-demo/REVIEW.md。示例是合成数据，故意缺少 FDR 列与执行证据，退出码 1 是预期审计结果，不是通过。目录包含重点页、完整审计、机器结果、输入指纹、空白人工评审和不含审计发现的参考评审模板。

示例用于理解结果，不能计入实验室净收益。重复体验请使用新目录名，旧目录不会被覆盖。

## 用自己的分析

最小起点是已有 DE 表和样本表；无需迁移 Scanpy、Seurat、R 或 Nextflow 工作流。样本表至少标明 donor 与 condition；缺少信息时保留未评估状态。没有执行证据的结果格式识别不能授权群体推断。

```bash
bionexus audit-de --de-table de_results.csv --sample-sheet samples.csv --claim "请替换为拟写入论文的具体声明" --bundle review-case-001
```

可按实际产物补充 --script analysis.ipynb、--execution execution.json，以及显式 --donor-col / --condition-col。只有 .h5ad 时使用 --h5ad results.h5ad；读取它需要安装 goldchain 依赖。不要为了通过审计补写不存在的执行记录。

先看 REVIEW.md 的重点，再查 audit-full.md 中全部发现与证据。输入保持只读；目录内记录输入文件名和哈希，不复制原始数据。报告可能包含原始供体标识和声明，分享范围由实验室决定。

退出码保持原审计语义：0 表示该入口的审计通过；1 可能是需修正、缺证据或读取失败。查看报告或错误信息区分，不把命令执行完成视为科学授权。没有生成报告时先解决路径或读取错误。

## 记录一次真实复核

交接前可运行 `bionexus audit-de-verify review-case-001`。它核对机器结果与
两份可读报告是否匹配 manifest，退出码 0 仅表示文件一致。旧包返回
LEGACY_LIMITED（退出码 3），不会自动补齐缺失的报告哈希。需要检测 manifest
本身是否改变时，传入交接时独立留存的 `--expected-manifest-sha256`。
这些核验不验证统计拟合、原始输入、评审者身份或科学结论。详见
[兼容契约](de-bundle-compatibility.md)。

按[试点指南](de-pilot-guide.zh-CN.md)完成参考审阅、发现判定和时间记录，再汇总：

```bash
bionexus audit-de-summary review-case-001/review.json --out pilot-observations.md
bionexus audit-de-summary review-case-001/review.json --json --out pilot-observations.json
```

空白评审显示 PENDING，未填时间显示未评估；合成示例排除，负收益保留。这个汇总描述人工观察，不认证身份、独立性、科学结论或净收益。

后端合成实验和发布验证另见[已有验证记录](../review/deep-analysis-2026-09-04/RESPONSE.md)。它们与用户试点收益不同。
