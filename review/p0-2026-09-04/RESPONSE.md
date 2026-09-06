# 三项 P0 改进与验证记录

本轮承接 `review/deep-analysis-2026-09-04/RESPONSE.md`，保留原始评估和历史失败报告。BioNexus 继续是被动、由宿主调用的证据审计层；没有增加自主规划、调度或平台功能。

## 最终工程验收

- 冻结提交：`cc923849783ac1d0b430f5e7ba494fa1cef1b0aa`，草稿 PR：https://github.com/HERRY423/BioNexus/pull/35 。原 main 未改动。
- 本地完整测试：1291 passed / 8 skipped；随后新增的归档回归测试 3/3 通过。8 个跳过为 6 个 POSIX/Slurm 条件测试与 2 个未安装 scVI 的测试，不计为通过。
- 最终托管检查：35 success / 0 failure；仅 GitHub Pages 部署按 PR 条件跳过。Python 3.10–3.12 × Windows/macOS/Linux 的核心矩阵 9/9、科学矩阵 9/9 全部通过；额外 scVI 和降级作业亦通过。
- CI 严格完整基准：92 个门禁 + 14 个 frontier = **106/106**，0 失败、0 跳过，L3 **13/13**。包含公共数据轨道，见 `hosted-full-benchmark.md`。
- CI 运行：https://github.com/HERRY423/BioNexus/actions/runs/33871774845 。清单及作业明细保存在 `hosted-checks.json`、`hosted-run.json`、`hosted-artifacts.json`。
- 本地源码归档：`C:/Plugin/BioNexus/.codex-p0-freeze-python313-final/source.zip`；SHA-256：`811e6e87c82f64697d37552bfe398b9973569d098823ef8efaf75d4b001876c5`。同目录保存依赖版本快照与 manifest；CI 另保存 18 个受支持环境的重现包。
- 已下载并复核 Windows/Python 3.12 核心重现包（`.codex-p0-ci-core-windows312`）：源码 ZIP 与依赖快照均通过哈希校验，CI 测试的 PR 合并提交 `5cb1b3132605c53f228e57274e199cb20920fba0` 的 Git tree 与本地冻结提交完全一致（`a50de0eb1f58a47e91257ee6adefc253d2ca14fc`）。两种 commit 身份没有混为一谈。
- 本地 Python 3.12 重复安装在下载大型依赖前停止，未宣称本地 3.12 通过；对应验证已由实际托管矩阵完成。冻结提交中的早期 VALIDATION 记录保留当时状态，本工作目录的记录及上述 CI 链接记录最终状态。

以上关闭工程 P0，不关闭独立科学验证、经验校准批准或外部治理缺口。

## P0-1：统一注释证据上限

- `assess_annotation_metadata` 作为共享入口，直接评估、ABI 和路由器重算同一个注释判断。
- “声明有来源”不再被填成 marker/reference 的数值分数。缺少测量或未获批准的校准配置仍为 TENTATIVE；缺少来源、错误类型、开放集等情况保留拒绝或冲突。
- 宿主传入的 `annotation_assessment`、`external_validation=True` 和覆盖选项不能自行提高上限。
- 证据卡把执行预检与身份结论分开，身份相关的 ceiling、claim maturity、sufficiency、policy 和缺失证据说明保持一致。
- BF-026 原输入现已通过预期的保守判定。新增 26 个反例和一致性测试，覆盖声明矛盾、伪造摘要、不同入口和后端拒绝优先级。

## P0-2：用实际扰动结果评估聚类稳定性

- 新增 `scrna_cluster_stability.py`，由调用者明确给出分辨率、采样比例和随机种子，执行有上限的 Leiden 网格并保存原始分区。
- 按细胞 ID 对齐后重新计算 ARI，拒绝错数据集、重复 ID、单簇/全单例分区等无效比较；显示共同细胞数量与覆盖率。
- 不设置“少于 30 个细胞必定无效”之类未经校准的门槛。任何细胞数下，强稳定性主张都需要扰动证据；普通探索仍可运行。
- 90 细胞合成夹具：4 次运行、6 个比较，最小/平均 ARI 为 1.0。
- 30 细胞子样本：12 次运行、66 个比较，最小/平均 ARI 为 1.0；共同细胞最少 14，最低覆盖率 0.5。输入派生过程见 `small30-input.json`。
- 上述通过的是调用者预先声明的 ARI≥0.8 工程条件。不是通用科学阈值，也不证明细胞身份、稀有群体或外部有效性。独立验证仍为 NOT_ESTABLISHED。

## P0-3：冻结源码、依赖和验证范围

- 在 `.codex-p0-integration` 隔离 checkout 中保留并整合现有工作，原始 main 工作区未被重置。
- 新增 `capture_reproducibility.py`：要求干净提交，输出 Git 源码 ZIP、commit/tree、SHA-256、Python/OS 和精确已安装版本。依赖版本快照限定于对应系统与解释器，不声称包含 wheel 哈希或离线依赖包。
- Python 3.10–3.12 × Windows/macOS/Linux 的 core/scientific CI 作业都保存源码和依赖快照，包括失败作业。
- 全量测试修正了旧断言：自声明工具回执不授予证据因子；两项作者关联研究不能计作独立研究；修复已通过的 frontier 案例不需要人为保留失败。
- 隔离运行的缓存权限、缺少公共数据及未解压 Xenium 的错误保留在历史日志中，未通过放宽业务规则规避。
- 最终测试、提交、冻结文件与托管 CI 结果记录在本目录的 `VALIDATION.json`；没有列为通过的项目不可视为通过。

## 本地有界基准

`benchmark/manifest.json` 记录运行源码、夹具和报告哈希，运行前后源码一致。

| 范围 | 结果 |
|---|---:|
| 门禁用例 | 84/84 |
| Frontier 用例 | 14/14 |
| 合计 | 98/98 |
| 植入信号 L3 后端执行 | 5/5 |

此报告显式排除 `flagship_validation`，L2 是脚本回放，L3 是合成夹具。三个单分辨率 ROBUST 用例的预期状态被改为更保守的 DEGRADED_ADVISORY，未提高其 PRELIMINARY 上限。报告中的 CALIBRATED 仅表示该回归语料的标签对齐，不是 APPROVED 的经验校准结论。

## 仍需要外部协助

独立真实数据验证、非作者盲审、独立实现/治理、机构身份与签名信任锚、正式宿主重新安装后的验收，仍需对应外部证据。代码、测试、重现包和送审材料可在仓库内完成，无法替外部人员生成独立性或科学批准。本轮不据测试通过率自动提高原始加权评估分数。
