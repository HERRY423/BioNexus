# BioNexus：顶尖实验室与生物学基础设施就绪度审阅

审阅日期：2026-09-06。审阅对象：`C:\Plugin\BioNexus` 当前工作区；HEAD 为
`cfb0691713cd1d43a5c2b68c9de3903d750fcbed`，声明版本 `1.0.0-rc.4`。
工作区最初有 133 条 Git 状态记录；本地修改不能归为已发布代码。

## 判断

BioNexus 已经是有实际工程价值的科学可靠性组件，适合明确范围、有人复核的研究试点。
尚未建立作为顶尖实验室默认信任基础设施的证据。它的主要短板是判断语义的一致性、
真实运行证据、独立实证校准和可测量的实验室净收益。继续扩展规范、连接器和算法，
不能替代这四件事。建议保持被宿主调用的被动可靠性层定位。

本次检查了核心判断代码、静态审计、收据与人工裁决、LIMS/出口控制、插件入口、
三条旗舰证据、IVN/治理注册表、互操作记录、近期实际研究检查点和 GitHub CI/发布。
没有重跑生物学研究、全套单元测试或实际宿主矩阵，也没有修改产品源代码。

## 本轮新执行的检查

- `python scripts/doctor.py`：core、scverse、spatial ready；scVI、Nextflow 未就绪。
  这是本机依赖检查，不是全部科学功能运行证明。
- `python scripts/verify_validation_artifacts.py`：PASS，列出 53 条文件检查记录。
  该结果仅证明此验证器覆盖的条件，不证明全部报告语义一致或独立科学有效性。
- GitHub 只读核查：main SHA 与上述 HEAD 相同；该 SHA 上 CI run `34017206520`
  和 `33950133251` 返回 success。最新发行条目为 rc.4 prerelease。
  后续逐 job 查询出现 `unexpected EOF`，未在本轮重新确认完整 job 清单。
- 直接 API 的最小探针：见同目录 `reproduce_probes.py` 与 `probe-results.json`。
  探针只使用内存对象；网络函数被 mock，没有发出 LIMS 请求。结果绑定源文件 SHA-256。

## 已有价值应当保留

1. 把能否执行、证据强度和可允许的科学声明分开，并保留软限制与不可覆盖的不变量。
2. 后端缺失时拒绝冒名替换；保存参数、数据和执行来源。
3. 对证据依赖、矛盾、声明上限和人类科学裁决提供可审计结构。
4. 实证校准没有通过时不静默使用通用阈值。
5. 保留阴性研究、无结论结果和失败调用，而非全部改成通过。
6. 已有 Python/R/TypeScript 语义验证器、AnnData/Seurat 适配和 RO-Crate 路径。
   这些是实质工作，但维护者多语言实现不是第三方独立采纳。

## 缺口一：同一科学问题尚未获得统一且证据绑定的判断

### 公开 pseudobulk API 过度依赖声明参数

`src/bionexus/pseudobulk_warrant.py:70` 的公开函数输入
`n_donors_per_group=3, is_interventional=True`，其他参数取默认值，即返回：
`ROBUST`、`population_claims_allowed=true`、`causal_claims_allowed=true`。

函数没有接收实际设计矩阵、干预分配、效应区间、离散度、模型诊断或替代解释证据。
这是已复现的独立公开接口行为；不能据此断言每条宿主调用路径都会放行。
但被集成者单独使用时，它把必要条件过早当成了充分证据。

`src/bionexus/evidence_model.py:446` 还把 `batch_corrected=true` 映射为
`confound_controls`，把 `parameter_sweep=true` 映射为 `effect_stability`。
源码明确称这些为调用方声明，仍应在输出中机器可区分：声称做过、观察到执行、
结果支持、独立验证。做过批次校正不等于设计混杂已解决；做过扰动不等于结果稳定。

优先改进：让 CLI、MCP、直接 Python API 和专用评估消费同一份类型化判断产物；
以实际设计和诊断证据驱动正向支持。不要把只含布尔声明的路径包装为已核实结论。

### 实际宿主记录出现声明类别识别失败

`review/spatialwarrant-run-01/10_bionexus_audit/S7-run-01/overclaim-tests.json`
记录了明确的中文总体效应请求和显式 `claim_class=population_effect`，但实际返回
`requested_claim_class=descriptive`，总体层为 `NOT_APPLICABLE`。
S7 检查点记录四次实际调用均被解析为 descriptive。

这次顶层 `NEEDS_DATA` / 声明层 `ABSTAIN` 并不证明正确识别了越界。
错误分类还会使补证建议指向错误问题。应先校验显式声明类别，解析冲突进入待澄清状态，
保留原文及分类依据，再进行确定性裁决。覆盖中文、英文、同义改写、否定及多声明文本。

## 缺口二：静态审计与运行证据之间缺少可靠连接

`src/bionexus/analysis_audit.py:286` 使用整份代码中的关键词判断是否已有 pseudobulk。
本轮保持分析调用不变，仅添加 `# TODO: pseudobulk later`，BFA-001 消失，
`passed` 从 false 变为 true。仍有 FDR advisory；并非所有问题都消失。

正则筛查可以作为提示工具，不能承担“通过即可信”的角色。
应把注释和字符串与执行代码分开，增加对象/数据流、counts 层来源、
donor 聚合和实际模型输入的运行证据。无法解析的包装函数应标为未评估，不能默认为无风险。
验收应包括保持语义不变的改名、重排、注释和封装反例，而不只是新增关键词。

## 缺口三：真实科学校准与独立效用证据仍然不足

当前 `validation/ivn/REGISTRY.json` 的 `lab_studies`、`reviews`、
`calibration_freezes` 均为空；`empirical_calibration_registry.json` 没有 APPROVED profile。
`review/SCIENTIFIC_REVIEW.json` 三个评审席位均为 PENDING，已评审案例为零。
这仅描述可查注册证据，不证明项目外绝无使用者。

三条旗舰不能合并为一个成熟度分数：

| 路径 | 可查证据 | 尚缺什么 |
|---|---|---|
| pseudobulk | GSE96583 donor-aware 实际执行；有跨数据集探索及冻结阴性结果 | 独立分析者复现、异质队列、对误报/漏报的真实评估 |
| annotation evidence | 外部 Azimuth PBMC 参考标签上的非盲候选结果 | 独立生物真值、未见供体、组织/平台外推边界、批准的上下文校准 |
| spatial validity | 正式旗舰有真实 Xenium 格式样本技术验收；近期 SpatialWarrant 有六切片实际流程 | 独立病理/分割真值、有效生物重复、跨方法分歧解释、实际声明审计成功 |

SpatialWarrant 的六切片流程和一个符合主终点条件的切片需同时保留范围；
不能称为“只有 toy 数据”，也不能变为多患者生物学验证。

`validation/pseudobulk/independent/REPORT.json` 留存 negative_result：
方向一致性很高，但预注册负对照 p=0.05859375 未达到 0.05。
这个阴性结果有价值，提示“看起来一致”不足以成为可靠性校准。

近期本地基准为 96/98，排除了旗舰 suite，L2 是脚本回放，L3 为 5 个合成案例；
联合校准仍 MISALIGNED。另有不同快照的托管完整基准成功记录。
不同源码、选择范围和执行模式不可混成一个“准确率”。

需要建立外部维护的真实案例集，至少同时包含应放行、应限制、应拒绝和无法判断四类。
报告按实验室/研究/供体拆分后的错误率、覆盖率、拒绝率、置信区间及复核时间。
不能按细胞随机拆分制造独立性，不能把专家无共识样本算作负例。

## 缺口四：部署边界还不能支持机构级承诺

`src/bionexus/lims_hub.py:90` 对空测量自动生成 A1、0.0、RFU 和样本编号，
并可使用默认项目编号。这是本轮直接复现的行为：缺失测量被转成了具体数据。
LIMS 导出默认 mock，虽包含 `is_mock` 标记，也应让模拟与真实成功在顶层明确区分。

同一连接器的直接 API 使用 `requests.post`；设置 AIRGAP_STRICT / OFFLINE_STRICT 后，
本轮 mock 探针仍到达该网络调用边界。没有真的发送请求；它证明此调用路径没有使用这两个
配置所表达的拦截，而不证明整个部署一定泄漏。

实验室落地需要完整覆盖出口、拒绝缺失关键数据、处理凭据、超时、分页和幂等写入，
以及实际机构沙箱验收。宿主/容器/机构防火墙负责基础隔离，插件只对覆盖到的调用作承诺。
不要将局部 Python guard 宣称为进程级零网络保障。

`tool_receipt.py` 已正确保留无外部信任锚时零科学因子；
`human_adjudication.py` 已明确摘要不能认证现实身份。
下一步应接机构身份/授权的已有系统，通过外部执行者签名和可撤销信任根绑定收据。
这属于组织协作和部署验证，不是再定义一种 receipt level 就能完成。

## 缺口五：版本与证据的对应关系需要成为产品保证

验证器本次 PASS，但仍存在语义陈旧：

- CERTIFICATION 的 cross-host 文字称 0 traps；COMPARISON 记录 6/6。
  后者缺少足够原始宿主执行链，不能简单把认证改成通过。
- spatial CERTIFICATION 仍描述一个 cell-size-bias 端点失败；当前对应研究 REPORT 已记录通过。

这说明文件结构和哈希验证之外，还需要检查报告引用、有效版本和语义依赖。
每次结论应绑定代码、规则、依赖、数据、宿主和报告摘要；历史报告保存为历史，
变更后指出哪条结论失效及是否需重算。为用户提供一份清晰的当前状态索引。

## 缺口六：尚未证明研究人员愿意持续使用

当前入门页面仍以声明元数据示例和阅读 JSON 字段为主，SUPPORT 为 best effort。
这些适合开发者试用，但实验室的采用对象应明确到：
谁在什么时点因什么问题打开 BioNexus，完成后省下什么劳动。

建议首个场景：单细胞多供体差异表达在组会、稿件或共享前的证据审计。
输入现有 notebook、AnnData、sample sheet 和结果，输出可行动问题、定位、最小修复、
可陈述范围及一个集中人工裁决入口。继续沿用 Scanpy/Seurat/工作流宿主。

核心指标应是“减少了多少高影响错误和复核成本”，而非报警数或拒绝率。
同时计入误报、人工处理时间、维护者救场次数和四周后主动再次使用。

## 缺口七：基础设施地位需要外部维护关系

已有 Python/R/TypeScript 验证器及 AnnData/Seurat round-trip 记录；
本地旧 Nextflow trial 是 NOT_RUN，新 RO-Crate sidecar 方向已有实现。
不应将此描述为完全没有互操作。
但公开 scoreboard 无已接受外部提交，机构采用计数为零，治理 council 无成员，
独立认证主体缺失、徽章暂停。

基础设施价值来自稳定对象契约、兼容/迁移、被外部维护者使用和共同治理。
优先让一个外部工作流维护者在原流程不变的前提下接受一个产物级侧车，再逐步共同维护。
不要要求实验室先迁入新的平台，也不要把维护者自行移植成三种语言称为独立组织验证。

## 缺口八：部分产品语言强于实际度量

`debt.py:300` 的优先排序是影响声明数乘严重度权重。
因此文档的“70x”不是实测风险下降，也不是考虑成本、成功概率和实验依赖后的最优实验设计。
它可以作为有解释的排序提示，但应显示公式和适用边界，去掉实证收益暗示。
修复一个依赖也不能在没有新证据时自动保证后续声明升级。

同样，VALIDATED、CALIBRATED、CONFORMANT 等词需始终带对象和证据类别。
正确限制已在很多地方实现，但顶层摘要和旧叙事仍可能被用户或宿主截断读取。

## 建议投入顺序与验收门槛

以下为建议试点设计，不是既有行业认证标准或已达到的承诺。

| 阶段 | 工作 | 可审查的验收 |
|---|---|---|
| 先修阻断项 | 统一声明类别与专用评估；修复注释绕过、布尔正向授权、LIMS 缺失值和出口遗漏 | 本报告反例及其语义等价变体在支持版本上通过；顶层和分层结果一致；mock 不能伪装真实成功 |
| 冻结一个试点版本 | 精简审计安装、固定依赖、完整发布检查、报告语义绑定和可恢复升级 | 新机器从发行包独立复现；无需维护者修改源码；当前证据索引唯一且可追溯 |
| 历史案例盲评 | 2–3 个合作实验室，先收集约 30–50 个真实分析包；量足与否由独立统计评审决定 | 专家先于工具给出判断；记录误报/漏报、未知及处理时间；按研究拆分、给出不确定性 |
| 前瞻使用 | 4–6 周观察真实工作，先 advisory，再决定有限门禁 | 与实验室原有审核流程比较；收益超过安装、误报和维护成本；保留负结果和退出理由 |
| 扩大资格 | 非作者复现、一个外部维护的适配、批准第一个窄范围校准 profile | 有外部原始记录、签字及责任人；冻结的版本与数据可重放；范围外继续未评估 |

暂缓扩大多组学/药物设计/模型封装、全平台式调度和更多自有标准。
BioNexus 最值得形成的优势是：经过独立裁决的失败案例、跨工具的证据契约、
能降低复核负担的工作流，以及可持续的外部维护关系。

## 外部对照依据

- [nf-core pipeline specifications](https://nf-co.re/docs/specifications/pipelines/overview)：
  关注有边界的流程、依赖可复现、测试及社区协作。此处用于基础设施工程对照，不声称 BioNexus 必须成为 nf-core pipeline。
- [scverse mission](https://scverse.org/about/mission/) 与
  [roles and decisions](https://scverse.org/about/roles/)：稳定 API、共享数据结构、维护责任和社区治理。
- [Workflow Run RO-Crate profiles](https://www.researchobject.org/workflow-run-crate/profiles/)：
  区分工具、工作流及步骤级运行来源，说明侧车可以接入已有标准而无需新平台。
- [Squair et al., 2021](https://www.nature.com/articles/s41467-021-25960-2)：
  生物重复与单细胞差异表达假发现的实证基础；不提供通用 N=3 因果许可。
- [Luecken et al., atlas integration benchmark](https://www.nature.com/articles/s41592-021-01336-8)：
  批次去除与生物信息保留需分别评估，支持不把 batch_corrected 当作全部混杂已解决。
- [本次核查的 CI run](https://github.com/HERRY423/BioNexus/actions/runs/34017206520) 与
  [rc.4 prerelease](https://github.com/HERRY423/BioNexus/releases/tag/v1.0.0-rc.4)。
