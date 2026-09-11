# 工程质量门禁与 DE 要求证据

本轮维护按三个阶段推进：建立实测门禁、按职责拆分 CLI、为受支持的 DE 核心要求补齐可执行映射。它不改变 BNS 规范的成熟度，也不授予科学认证或替代具名科学负责人的判断。

## 1. 核心类型与覆盖率

从仓库根目录执行：

```powershell
python -m mypy
python scripts/run_core_quality.py --output .quality/local-01
```

输出目录必须是新目录；再次运行使用 `local-02` 等新路径。所需开发依赖在 `pyproject.toml` 的 `dev` extra 中。

`mypy.ini` 对 contracts、evidence_model、warrant、claim_semantics、de_audit、de_bundle 六个模块启用函数签名和函数体检查。内部导入会被跟踪，但当前只有这六个显式模块的诊断构成门禁；第三方库实现和未列入的内部模块不在完整检查承诺内。`no_site_packages` 使 Python 3.10 目标检查不受本机较新科学库语法影响，代价是未校验第三方库的类型契约。这里没有用全局忽略内部错误来通过检查。

覆盖率测试清单在 `quality/core-tests.json`，固定 Hypothesis 随机种子为 20260911。该配置只依赖核心运行时，不要求安装 scVI、Scanpy 等可选科学后端。完整测试矩阵仍独立保留。

`quality/coverage-baseline.json` 记录六个模块分别的行与分支下限，来自修改前固定核心测试清单的实测值，向下取两位小数。新增边界测试已加入清单。`scripts/check_coverage.py` 对以下情况返回非零退出码：

- 任一核心模块覆盖率低于对应下限。
- 核心模块从报告中消失。
- 未采集分支覆盖率，或测量分母为空、数值非法。
- 下限缺失、非法或整个受保护模块清单为空。

报告还会列出其他源码模块的覆盖率，但它们没有因此获得受保护声明。这个门禁不是全仓 80% 或科学正确性证明。新增代码应补充有意义的反例，不能通过降低下限、扩大排除范围或增加无断言测试来消除失败。调整受支持范围须在评审中解释；提升下限应附新的实测报告。

`--measure-only` 只收集测量，明确输出门禁未评估；CI 与发布流程不使用这个选项。Windows 无符号链接权限时，相关已有测试可能跳过；这不算已验证的路径，Linux CI 负责另行执行。

类型检查本轮发现并修复的行为问题：显式 `technical/model_fidelity` 引用了不存在的 `ClaimClass` 成员。现在保留不支持的原始声明类别，并返回未建立 warrant；未知类别和否定句不能继承较容易的声明类别而通过。合法类别与既有数据格式保持兼容。

## 2. CLI 职责拆分与兼容

`bionexus.cli:main` 和 `python -m bionexus.cli` 继续有效。入口从 4,852 行减为 1,349 行，只保留控制台配置、参数解析、分发及兼容导出。处理函数位于 `src/bionexus/commands/`：

| 模块 | 职责 |
|---|---|
| scaffold | 生成技能模板 |
| diagnostics | doctor、清单、注册表、后端身份诊断 |
| de | DE 审核、结果包校验和摘要 |
| validation | preflight、verify、bench、eval、conformance |
| standards | 规范、ABI、能力和认证记录展示 |
| claims | 声明、规则、账本和路由接口 |
| execution | 已有执行、集群、大数据和模型命令 |
| experimental | 已有实验性命令 |
| security | 安全、guard 和缓存命令 |
| ivn | 独立验证记录与证据债务 |
| lab | LIMS、GA4GH、仪器、合规和 Nextflow 接口 |

这只是代码组织变化，不扩大任何命令的支持或授权范围，也不新增自主规划或调度行为。

旧的 `bionexus.cli.handle_*` 导入路径继续导出同一处理函数。原领域模块的路径没有搬迁。对文件位置敏感的 bench 模板定位已随目录层级调整。

`tests/fixtures/cli_contract_v1.json` 来自拆分前源码，而非新实现。`test_cli_compatibility.py` 比较全部命令及子命令的参数、别名、默认值、选项、帮助文字；既有 CLI 行为测试继续检查 JSON、退出码、错误路径和生成文件。后续新增参数需要解释性更新这一兼容快照，不要自动覆盖它以掩盖意外变化。

回退应恢复同一版本的 CLI 入口与命令包，保留用户数据和已有审核结果；仅删除命令包会破坏新入口。历史入口源码留存在本轮 review 目录，不能将一次代码重构当作结果包或规范版本迁移。

## 3. DE 要求映射与执行收据

映射文件是 `spec/de-audit-traceability.yaml`，复用已有 `contract_traceability` 引擎，覆盖计数输入、供者推断边界、未验证状态以及结果包完整性。

```powershell
# 仅检查引用：不会把测试声明变成执行证据
python scripts/check_de_traceability.py --output .quality/de-declared-01

# 实际运行映射测试并记录本地执行证据
python scripts/check_de_traceability.py --run --output .quality/de-executed-01
```

每条有实现的要求必须同时关联正向与反向测试。缺失的实现符号、失效测试引用、缺少反向案例会失败。执行模式记录每个测试的 setup/call/teardown；参数化测试必须所有案例通过，跳过、缺失和 teardown 失败都不能生成该测试的通过声明。测试期间源文件变化时不签发收据。

报告保留规范、源码、执行脚本和映射测试的 SHA-256、实际 pytest 参数、逐例结果及 XML 报告。收据由本地运行产生，不接受导入旧收据来升级当前 checkout 的状态。历史报告只对应其记录的文件哈希；源码或测试发生变化后须在新目录重新执行。

7 条要求有有界测试映射；以下两项仍为 `acknowledged_gap`：

- **BNS-EM-007**：独立校准证据尚未由该工程配置建立。
- **BNS-PV-009**：本地文件校验不等于文件系统强制不可变，也不等于外部锚定的追加式溯源。

每条映射的 `scope_note` 明确测试的实际含义。例如，合成执行元数据可满足既有审核器的特定检查，但不证明真实后端执行或生产者身份。`tested` 仅指哈希绑定的本地技术测试，`scientific_authorization` 始终为 `NONE`。映射外的规范不被视为通过。

CI 的 `reliability-quality` 作业和发布流程均运行类型、覆盖率与 DE 要求门禁。工作流配置不等于已通过的托管 CI；本地验证和远端运行状态必须分别报告。
