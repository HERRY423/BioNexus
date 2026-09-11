# 三阶段工程维护结果

状态：**COMPLETED_LOCAL_ENGINEERING_VALIDATION**。本轮工作在已有未提交改动之上完成，保留用户原有工作；没有提交、推送或发布。

## 已完成

1. **实测质量门禁**：为六个核心模块加入 mypy 检查，以及分别约束行和分支覆盖率的门禁。下限来自修改前核心测试实测，未降低。缺少模块或分支数据直接失败。CI 和发布流程都已接入。
2. **CLI 按职责拆分**：从 4,852 行减为 1,349 行，处理函数进入 11 个命令模块；入口保留参数解析、分发与兼容导出。拆分前冻结的全部 argparse 契约与安装后结果一致。
3. **DE 规范执行证据**：为 7 条要求关联实现、正向测试和反向测试，执行 21 个案例通过；保留两个明确缺口。复用已有追溯引擎，没有修改 BNS 状态或增加规范编号。

类型检查初次发现 16 处错误。除修正注解和类型边界外，修复了显式 technical/model_fidelity 类别引用不存在枚举成员的崩溃，并阻止未知类别通过描述性或否定句路径获得 warrant。新增回归测试覆盖这一行为。

同时修复了影响当前工作区质量检查的 19 处 lint 问题（未使用导入、导入顺序及一个未定义的 Tuple 注解）。安全扫描改为在遍历前剪除原先已排除的目录，保持原扫描范围；本轮扫描通过，耗时约 15 秒。插件镜像均经官方 registry 编译器生成。

## 验证结果

| 检查 | 结果 | 证据 |
|---|---|---|
| 完整本地 unit 配置 | 1,492 passed，7 skipped，1 deselected；约 312 秒 | [测试日志](tests.after.log)、[JUnit](tests.after.xml) |
| 本轮完整 unit 覆盖率 | 行 79.70%，分支 65.24% | [coverage.after.json](coverage.after.json) |
| 固定种子核心门禁 | 191 passed，1 skipped；六模块下限通过 | [核心日志](core-seeded.log)、[覆盖率](core-seeded/coverage.json) |
| 核心类型检查 | 六模块通过；初始 16 处错误已修复 | [初始诊断](types.before.log)、[最终静态检查](static-final.json) |
| CLI 兼容性 | 21 passed | [CLI 日志](cli-tests.log) |
| DE 要求证据执行 | 21 passed；7 tested、2 acknowledged_gap | [最终报告](de-final/report.json)、[收据](de-final/receipts.json) |
| 报告门禁及发布配置回归 | 5 passed | [日志](final-report-checks.log) |
| wheel 构建与安装后检查 | 通过；11 个命令模块、参数契约和旧结果包读取 | [wheel 检查](wheel-smoke.json)、[构建日志](build.log) |
| Ruff、registry/镜像、DE 历史包兼容 | 本地通过 | [最终静态检查](static-final.json)；wheel 检查另覆盖旧包读取 |

完整 unit 配置排除了 `test_scvi_smoke.py`，并排除 `flagship_data` 标记。7 个跳过分别为：Windows 符号链接权限案例 1 个、需要 POSIX bash 的 Slurm 门禁案例 6 个。它们不是通过结果。初始完整基线运行曾中断，`tests.before.log` 不作为完整套件通过证据；固定核心修改前测量和最终完整回归均有完成记录。

本机 Python 为 **3.13.9**，有现存科学依赖；这不同于 CI 声明的 Python 3.10–3.12 矩阵。wheel 检查采用隔离安装目录及现存宿主依赖，尚不构成干净机器安装验收。远端 CI **未运行或核验**，不能将工作流配置表述为托管检查已绿。

`git diff --check` 还报告了原有未提交改动中的尾部空行；未为消除这些既有格式提示而改写无关代码。Ruff 已通过，但本地受限目录的遍历仍有权限提示。

## 核心覆盖率及初始下限

这里的下限仅约束固定核心测试配置，不将全仓数字冒充核心门禁。

| 模块 | 初始行下限 | 当前行覆盖率 | 初始分支下限 | 当前分支覆盖率 |
|---|---:|---:|---:|---:|
| contracts | 80.11% | 80.11% | 61.29% | 61.29% |
| evidence_model | 84.23% | 84.23% | 77.90% | 77.91% |
| warrant | 95.93% | 95.97% | 80.55% | 80.56% |
| claim_semantics | 83.76% | 85.76% | 67.18% | 71.09% |
| de_audit | 65.42% | 65.43% | 54.25% | 54.26% |
| de_bundle | 87.50% | 87.50% | 87.03% | 87.04% |

这些数字不能证明科学正确性。后续应围绕真实失败案例提高覆盖率；不要通过降低下限处理回归。

## 保留的科学和规范边界

- `BNS-EM-007`：独立校准证据未建立。
- `BNS-PV-009`：强制不可变存储及外部锚定的追加式溯源未建立。
- 映射的 `tested` 只指本地工程执行，收据不具备独立签名认证效果。`scientific_authorization` 为 `NONE`。
- 计数的数值检查不能认证真实原始计数来源；合成执行元数据和审核器的 `ROBUST_PASS` 不能证明真实后端身份、真实运行或独立科学 warrant。

日常操作、兼容边界和重跑命令见 [工程维护说明](../../../docs/engineering-quality.md)。机器摘要在 [summary.json](summary.json)，主要证据文件的哈希在 [evidence.sha256.json](evidence.sha256.json)。最终 DE 报告中的源码哈希已核对与当前工作区一致。
