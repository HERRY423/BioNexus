# rc6 后 P0 修复记录

本次对应审阅对话指定的四项 P0：negation warrant、execution-binding edge cases、IVN Pages、GA support policy。起点为 `4bf9a754cb9a58a02bddaad3acb7d8f62d518f5d`，工作区已有工程重构及边界修复；本次保留这些修改，没有重置、提交、推送或发布版本。

## 修复结果

1. **否定声明**：保留“未证明”的局限性措辞，但其生物学证据上限为 `UNASSESSED`；移除 negated 标记及复合句中的免责语句对其他主张的放行。无效应、等效、非劣效不能依靠普通 DE 表或 `perturbation=True` 获得支持。普通不显著结果仍可通过事实核查；缺失调整后 p 值不再充当阴性结果。原来要求把“IL-6 不驱动耗竭”降为描述性主张的旧测试，已替换为保留机制证据要求的断言，并单独验证诚实局限性措辞。
2. **执行绑定**：要求明确统计单位、方法、成功拟合状态、设计公式与矩阵列、供体数量与标识，以及与实际审核表格一致的文件 SHA-256。缺字段、未知状态、矛盾别名、重复 JSON 键、伪重复标签、供体错配、无文件字节的 DataFrame 都不能获得绑定通过。另修复了 `ISSUE_FOUND` 仍可进入 `ROBUST_PASS` 的总判定漏洞。通过文本明确只证明输入一致性，不证明真实模型执行、生产者身份或科学有效性。
3. **Pages**：在线核实 rc6 的构建和加密校验成功，部署被环境策略拒绝：只允许 main，却从 release tag 部署。工作流改为 main 发布账本，tag/PR 构建并留存普通 artifact；部署权限下放至 deploy 作业，保留原环境保护。错误原文及工作流哈希见 `pages-check.json`。本地 IVN 校验通过，账本成功构建；修改后的远端部署尚未运行。
4. **支持政策**：补齐 12 个月 Core 1.x 支持窗口方案、最新 minor 修复、窗口内 90 天关键补丁回补、科学规则修改通知及 90 天 EOL 通知。MAINTENANCE、SECURITY、SUPPORT 保持一致。实际日期、具名维护者及接受记录须由 GA 发布时确认；当前仍为 `PROPOSED / NOT ACTIVATED`。

迁移说明：[docs/rc6-p0-closure.md](../../../docs/rc6-p0-closure.md)。原有 bundle、CLI 入口及 schema 版本保留；历史结果不能自动升级，应另建目录重新审核。

## 验证口径

最终状态：`LOCAL_FIXES_VERIFIED_EXTERNAL_ACCEPTANCE_PENDING`。2026-09-12 完成汇总时，17 个冻结源码/政策文件哈希全部一致。

| 验证 | 实测结果 |
|---|---|
| 完整 unit 配置 | 1659 passed / 7 skipped / 1 deselected；0 failures、0 errors |
| 固定核心门禁 | 362 passed / 1 skipped；原有行、分支覆盖率下限全部通过 |
| DE 要求执行映射 | 111 passed；科学授权仍为 NONE |
| 安装后 wheel P0 回归 | 89 passed；旧 bundle 为 LEGACY_LIMITED |
| 类型、lint、diff | 18 模块 mypy、Ruff、git diff --check 均通过 |
| 注册表与 IVN | 平台清单及插件镜像无漂移；IVN 6 个实体校验通过 |

7 个全量跳过项来自 Windows 符号链接权限和需要 POSIX bash 的 Slurm 检查。完整运行保留 172 条依赖/科学库警告；未把警告隐藏或宣称为后端科学有效性证明。全量日志、JUnit、DE 收据及 wheel 报告已归档于本目录。

- 初始定向基线：67 项通过。新增 P0 文件包含 89 个实际回归用例。
- 最终固定核心门禁、DE 要求执行收据、完整单元测试和安装后 wheel 用例的计数由 `summarize.py` 从 JUnit 读取，写入 `summary.json`。只有零失败、零错误且冻结源码哈希一致时才能生成最终汇总。
- 覆盖率下限没有降低；mypy 检查 18 个既有受保护模块；Ruff 与 diff whitespace 检查通过。注册表/插件镜像检查通过，无需生成新的镜像。
- wheel/sdist 在新目录构建，保留旧产物。安装到独立目标目录后用 `python -I` 导入，逐文件确认来自安装目录且字节与最终源码一致，再运行全部 89 个 P0 用例，并确认旧 bundle 仍为 `LEGACY_LIMITED`。
- wheel 使用本机已有依赖，包版本仍为 rc6；它是本地修改版，**不是已发布 rc6 artifact，也不构成干净机器安装验证**。
- 全量配置沿用仓库 CI 的 unit 命令，排除 `flagship_data` 和独立 scVI smoke。Windows/Python 3.13.9 本地结果不能替代 Python 3.10–3.12 多系统托管矩阵；跳过原因在汇总中保留。

## 尚未由本次工作建立的证据

修改后提交的托管 CI、main Pages 部署、真实具名维护者对 GA 支持窗口的承诺尚未完成。独立科学 review、外部 shadow-use、Codex/Claude 双 host conformance、GA tag 签名和正式发布也未由本次本地修复建立。不能据此宣称已达到 GA 或完成独立科学认证。

## 复核命令

```powershell
$env:PYTHONPATH='src'
python -m mypy
python -m ruff check src tests scripts evals
python scripts/run_core_quality.py --output .quality/rc6-p0-core-recheck-01
python scripts/check_de_traceability.py --run --output .quality/rc6-p0-de-recheck-01
python -m pytest tests/unit/ -q -m 'not flagship_data' --ignore=tests/unit/test_scvi_smoke.py --basetemp=.pytest-tmp-rc6-p0-recheck-01 -o cache_dir=.pytest-cache-rc6-p0
python scripts/registry_compiler.py --check
python -m bionexus.cli ivn verify
git diff --check
```

每次使用新的输出目录。已归档的验证只适用于记录的文件哈希；后续修改需要重新核查，不能复用旧收据声称当前源码通过。
