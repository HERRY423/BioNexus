# 对 repository-deep-analysis 评估的核对、改进与验证

日期：2026-09-04。评估来源：
`C:\Users\13264\Downloads\bionexus-repository-deep-analysis`，重点读取
`src/data/analysis.ts`、`Audit.tsx`、`Architecture.tsx`、`Verdict.tsx` 和 `Roadmap.tsx`。
该目录是评估展示应用；本轮修改的是 BioNexus 项目，没有修改评估原文。
`analysis.ts` 原始字节 SHA-256：
`c6badf3720e8b2d742c4b724a14b26f08e69bb69ff1231502fe393d7d8f90fb7`。

## 判断与范围

评估最有价值的结论是：应优先缩小真实证据缺口、修复可复现的失败行为、降低
首次使用门槛。新增规范和扩展启发式能力，不能替代独立实验室复现、误报测量
和有责任人的科学评审。本轮保留 BioNexus 被宿主调用的被动可靠性层定位。

评估中的很多数字来自 2026-08-16 的历史回放，不代表当前源码状态。初始 HEAD
为 `cfb0691`，工作区已有大量未提交改动。本轮保留原有改动；没有把原有的
connector、lineage、CI、IVN、认证等工作算成本轮新成果，也没有提交、推送或发布。
每次基准的 manifest 记录工作文件哈希；HEAD 不等于完整被测工作区。

## 逐项核对

| 评估意见 | 本轮检查到的状态 | 处理 |
|---|---|---|
| L3 0/4，后端未安装 | 旧报告如此；当前 YAML 已有 5 个合成信号案例，本机有科学后端 | 修复端点验证后实际执行 5/5；保留版本与源码哈希 |
| CI 应安装 goldchain/spatial 并 strict | 当前工作区已经有此 CI 配置 | 增加公共数据下载前的独立 L3 执行与证据产物上传步骤；托管执行待验证 |
| 7 个前沿失败 | 初次重跑为 5 个；BF-010/014 已由先前工作修复 | 本轮修复 3 个路由失败，另外 2 个继续公开失败 |
| 静态 Passing 徽章 | README 已是动态 Actions 徽章 | 保留，不重复改造；本轮没有查询最新托管 CI 状态 |
| 缺乏官方 RO-Crate 验证器互操作 | 当前已有固定 roc-validator 0.11.2 的工作流 | 评估此点部分过时；存在工作流不等于本轮已执行或获外部认可 |
| 全部证据来自回放 | 当前仓库还保留公共数据研究与冻结阴性结果 | 区分真实数据研究、合成夹具、回放、外部复现，不能把所有证据混成一个比例 |
| 无 APPROVED 校准配置 | 打包注册表仍为 incomplete_not_claim_ready | 保持原状；本地基准不授予审批，不把 CALIBRATED 字符串当经验校准 |
| 外部实验室与非作者评审缺失 | 当前 IVN 仍明确无已验证外部实验室研究 | 保留缺口；已有邀评材料不能算评审完成，也没有代发邀约 |
| 术语负担大，首次接入困难 | README 先介绍较多概念 | 增加短入门页和可执行 shadow 示例，直达需要阅读的结果字段 |
| shadow 不阻断、几乎零风险 | 此说法过宽；硬不变量和强制约束仍阻断，证据上限保持 | 修正 lab_policy 中过时的“不封顶”说明，入门页明确边界 |
| PyPI / conda-forge 发布及社区治理 | 属于发布与外部采纳工作，不由本地代码证明 | 本轮未宣称新发布、机构采纳或成立治理委员会 |

## 已实现的关键修复

1. **消除真实参考数据的合成替代。** 旧下载器在网络失败后会把合成 PBMC
   写到 `pbmc3k_raw.h5ad`，还会在无下载来源时生成“Visium/ClinVar”参考。
   现在下载失败直接失败，无来源拒绝；下载和缓存均要求外部保留的预期 SHA-256。
   损坏或可能被替代的旧缓存保留原文件，但拒绝使用。哈希只证明字节相符，
   不证明来源身份或独立科学真值。CLI 改为单数据集加 `--sha256`，不再支持
   未固定版本的 `--dataset all`。
2. **让 L3 检查与声明一致。** 差异表达不再仅靠 top-5 排名通过：同时检查
   有限有效的 p 值、`padj < fdr_q_max` 和声明的正向 `log2FC >= 1`
   （对应 fold change >= 2）。marker 检查使用 YAML 的 `expected_genes`。
   空间检查逐个验证声明基因的有限 Moran 统计量，而非只硬编码 SVG_LEFT。
3. **避免坏案例从分母消失。** 不存在的 suite、空选择、非列表文件、坏案例、
   重复 ID、字符串形式的布尔标志会导致失败；不再警告后忽略。未知 L3 信号
   不再从预期答案复制实际 maturity，保持 UNASSESSED 并失败。
4. **修复统计意图路由。** 明确请求 Moran's I 时优先进入空间路径，UMAP/PCA
   替代物理坐标因而到达已有的不变量检查；簇间 marker 对比不会因附带提及
   biological replicates 而误送到条件级 pseudobulk。显式 pseudobulk 模型和
   condition-specific 请求仍保留对应条件级路径。
5. **保留可复查的执行材料。** 新命令 `scripts/run_benchmark_evidence.py`
   保存 JSON、Markdown、环境版本、源码与报告哈希；输出目录必须是新目录。
   检测到执行期间源码变化会返回非零。suite/level/exclusions 同时写入两种
   报告，避免把子集得分误读成全套通过。

## 实际验证

| 检查 | 结果与范围 |
|---|---|
| 修复前相关路由/策略测试 | 20 passed |
| 最终相关单元/集成测试 | 89 passed，2 deselected；覆盖新增反例、评估账本、原路由、策略、README |
| L3 实际后端 | 5/5 passed，0 skipped，strict；合成数据，非独立生物验证 |
| 最终 L1/L2/L3 子集 | gating 84/84，frontier 12/14，union 96/98；明确排除旗舰公共数据 suite |
| 联合校准 | 仍为 MISALIGNED，两个前沿失败未隐藏 |
| Python 环境 | Windows / Python 3.13.9；与主 CI 3.10–3.12 不同，不能代替支持矩阵证明 |
| 静态检查 | 本轮修改的 Python 文件 Ruff 通过，限定文件 git diff --check 通过 |
| 注册表与镜像 | 从 canonical roots 重新生成；registry_compiler --check 通过 |
| 托管 CI、真实宿主矩阵 | 本轮未执行/验证 |

较早启动的广范围评估测试会进入完整旗舰研究执行，运行较久后被中止；不能记为通过。
最终有意排除了两个会重复运行全套旗舰研究的测试，保留了端点、缺后端、strict
计数、CLI、收据等定向验证。完整公共数据研究未重跑，没有改写已有冻结报告。
PyDESeq2 在微型夹具上发出 dispersion trend 改用 mean trend 的警告；这不是换后端，
也不构成生物学验证。

证据文件：

- [最终基准](final-benchmark/report.md)、[逐案例 JSON](final-benchmark/report.json)、[环境与哈希](final-benchmark/manifest.json)。
- [89 项定向测试的原始输出](targeted-tests.txt)；三个时点的报告 SHA-256 均重新核对通过。
- [首次修复后的 L3](planted-l3/report.md)：端点修复完成后、路由改动前的独立时点记录。
- [路由修复前重跑](routing-replay/report.md)：保留当时 5 个失败，避免覆盖历史。
- [入门示例](../../examples/shadow_audit.py)与[简短使用指南](../../docs/quickstart-shadow-audit.md)。

## 两个未关闭案例及下一步

- **BF-026：负 marker 缺失。** L1 的 ABI ceiling 路径仍会保留 SUPPORTED，
  未呈现该案例要求的 TENTATIVE/negative remedy。专用 annotation assessment
  与通用 L1 maturity 的语义不一致，需要沿同一个评估产物接通，不能简单根据
  一个元数据布尔值制造支持。当前应调用专用注释证据评估并保留未批准校准的
  限制，不使用 L1 ceiling 单独授权注释结论。
- **30-cell clustering：缺少明确 advisory。** 当前限制为 FRAGILE，但状态仍
  PERMITTED，与预期 DEGRADED_ADVISORY 不一致。应在重复抽样/参数扰动的实测
  稳定性基础上形成建议，不能为了让案例通过新增一个未经校准的细胞数阈值。

下一阶段资源应集中在已冻结、donor-aware 的公共研究和非作者复现：保留失败
结果，按预注册设计记录假阳性、假阴性、覆盖范围和科学家复核时间，再由有
责任人的外部评审决定是否批准特定上下文的校准配置。增加本地测试数量、
生成更多规范或发布徽章不能关闭这些证据缺口。
