# BioNexus Core 发布与能力认证门禁映射矩阵 (Core vs. Capability Gates Matrix)

## 背景与范围边界
当前 BioNexus Core 1.0 的正式支持范围已冻结收窄于 **已完成多供体 DE 材料的被动审阅与验证**（详见 [core-support.v1.json](../../src/bionexus/data/core-support.v1.json) 与 [GA_CRITERIA.md](../../GA_CRITERIA.md)）。然而，现有发布流水线（`release.yml`）仍绑定了 `annotation` 与 `spatial` 等广泛能力的黄金链及压力测试。

### 核心准则 (Golden Rule)
> **优先跑通现有全部严格门禁；如果需要拆分 Core 发布与能力认证流程，应公开逐项映射保留哪些检查、哪些证据独立发布，绝不能为了变绿直接删门禁。**

---

## 逐项门禁映射分类表 (Gate Mapping Taxonomy)

| 门禁标识 | 检查项与脚本 | 归属分类 | 发布流水线处理机制 | 独立证据归档形式 |
| :--- | :--- | :--- | :--- | :--- |
| **G0-VERSION** | 版本单一可信源一致性 (SSOT: Git Tag / pyproject / versions) | **Core 阻断门禁 (P0)** | 阻断级：三者版本不一致立即退出并终止构建。 | 源码元数据 |
| **G1-STATIC** | Ruff Lint 与 Mypy 类型检查 (21 个核心模块) | **Core 阻断门禁 (P0)** | 阻断级：类型错误或代码格式不合规直接拦截。 | CI 日志记录 |
| **G2-UNIT** | Core Unit Tests & 固定覆盖率底线 (`run_core_quality.py`) | **Core 阻断门禁 (P0)** | 阻断级：任何单测失败或分支覆盖率低于 baseline 即拦截。 | JUnit XML 报告 |
| **G2-TRACE** | DE 规范与反例双向可追溯性 (`check_de_traceability.py`) | **Core 阻断门禁 (P0)** | 阻断级：核心规范缺少反例或回归测试时阻断。 | `.quality/de-traceability/` |
| **G2-BUNDLE** | DE Bundle 契约与旧版读取兼容 (`check_de_bundle_contract.py`) | **Core 阻断门禁 (P0)** | 阻断级：新版写输出或旧版读解析异常时阻断。 | JSON 审计回执 |
| **G2-CONTRACT**| 冻结支持范围与具名 GA 准入校验 (`check_release_contract.py`) | **Core 阻断门禁 (P0)** | 阻断级：范围漂移或未激活时阻断 GA（RC 校验范围合法性）。 | JSON 合同回执 |
| **G5-WHEEL** | 干净隔离环境安装与 CLI 验证 (无源码 tree 的干净 venv) | **Core 阻断门禁 (P0)** | 阻断级：Wheel 打包缺少文件或入口点异常直接阻断。 | Wheel 校验报告 |
| **C1-PB-STRESS**| Pseudobulk 7 维推断压力测试 (`pseudobulk_stress_test.py`) | **能力认证流 (P1)** | 保持在 rc8 门禁全量执行，生成运行回执；可作为 Tier-2 独立流。 | `validation/pseudobulk/INFERENTIAL_STRESS_REPORT.json` |
| **C2-ANN-STRESS**| Annotation 10 维证据基准测试 (`annotation_stress_test.py`) | **能力认证流 (P1)** | 保持在 rc8 门禁全量执行，生成运行回执；可作为 Tier-2 独立流。 | `validation/annotation/INFERENTIAL_STRESS_REPORT.json` |
| **C3-SP-STRESS**| Spatial 11 维空间推断有效性基准 (`spatial_stress_test.py`) | **能力认证流 (P1)** | 保持在 rc8 门禁全量执行，生成运行回执；可作为 Tier-2 独立流。 | `validation/spatial/INFERENTIAL_STRESS_REPORT.json` |
| **C4-FLAGSHIP** | 旗舰验证执行与跳过诚实性 (`run_flagship_validation.py`) | **能力认证流 (P1)** | 保持在 rc8 门禁全量执行，生成旗舰报告；真实数据集缺失时诚实记录 SKIPPED。 | `validation/*/REPORT.json` |
| **C5-EVIDENCE** | 证据索引自顶向下严格核验 (`check_evidence_index.py`) | **能力认证流 (P1)** | 校验全库源码与报告哈希的一致性，拒绝过期绑定。 | `validation/EVIDENCE_INDEX.json` |

---

## 独立发布与证据追溯机制
1. **Core 发布资产清单 (Release Assets)**：
   - GitHub Release 随附核心制品：`bionexus_reliability-*.whl`、`*.tar.gz` (sdist)、`SHA256SUMS.txt`、`benchmark_report.md`、`wheel_benchmark_report.md`、`plugin.json`、`mcp.json` 与 Sigstore SLSA 构建证明。
   - 在满足 Python (>=3.10) 及操作系统前置依赖的干净环境中安装核心包后，提供受支持范围内的 DE 审阅工具链与标准 CLI（详见 `core-support.v1.json`；更高级黄金链与空间分析功能需按需安装对应可选依赖）。
2. **能力认证与执行记录归档机制 (Validation Artifacts & Receipts)**：
   - GitHub Actions 流水线产物：提供工作流制品 `release-validation-run-capsules`（包含 `validation/runs/` 执行回执快照），支持构建追溯。
   - 源码仓库追踪证据：由 `validation/EVIDENCE_INDEX.json` 与各子域的 `CERTIFICATION.json` 记录工程验收指标与哈希绑定，支持外部科学家离线下载并复核技术结论（需遵循既定科学局限，不构成无约束的独立第三方生物学真理性证明）。
