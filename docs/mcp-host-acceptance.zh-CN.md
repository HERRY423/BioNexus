# MCP 宿主与传输验收

本契约覆盖 `bionexus_warrant_check` 和 `bionexus_host_probe` 的本地工程调用。
它不认证科学事实、宿主或审查者身份，不启动分析，不证明实验室效益。
外部数据库工具的真实服务质量不在本轮验收范围内。

## 返回状态

| 主结果 | MCP isError | 证据解释 |
|---|---|---|
| PERMITTED / PERMITTED_WITH_LIMITS / DEGRADED_ADVISORY | false | 仅声明条件下的路由可行性；以实际 evidence_contract 为准 |
| ABSTAIN 等规则拒绝 | false | 工具完成判断，但不能放行相应主张 |
| NEEDS_DATA | false | 缺信息；不是生物学阴性或零效应 |
| FAILED / TOOL_UNAVAILABLE | true | 参数、执行、序列化或工具可用性失败；没有正向科学结论 |
| host_probe RECORDED | false | 一次调用与审计记录；acceptance_verdict 仍为 pending_run_validation |

`content[0].text` 与 `structuredContent.result` 为完全相同的 JSON 字符串。
仅 MCP `isError=false` 不构成科学通过。消费者应检查主状态、证据契约和
嵌套 `claim_warrant_evaluation`，使用 `interpret_positive_output`。路由可行
与宽主张不被支持可以同时成立，不应删除合法的窄结论。

SDK 和 legacy 共用原始 JSON 参数校验。缺必需参数、未知额外参数、非有限数、
错型证据布尔值/重复数、错型/未知/冲突的显式 claim class 都拒绝；不强制转换
`"true"` 或 `1` 为已批准。只允许调用实际公开的工具；隐藏工具不能绕过发现列表。
工具异常只返回错误类别，不回显输入、密钥或私有路径。SDK 启动失败不会静默
切换为另一实现；legacy 需要明确选择。legacy 收到 EOF 时等待已受理请求完成。

## 运行身份与回执

`runtime_identity` 记录服务启动时本地包内 `.py` / `.json` 文件的排序清单摘要、
文件数和 MCP SDK 版本。验收者从冻结安装包独立计算并比较此摘要。
它不是远程密码学证明，不能抵御不可信生产者伪造回执；运行中不得编辑安装包。

MCP host probe 的哈希链事件绑定同一 runtime_identity。名称和审批字段均为
DECLARED；`human_approved=false` 可合法记录且不升级为批准。真实宿主身份
需要外侧启动命令、宿主版本、协议日志和包摘要共同支持，不能仅凭自报名称。
MCP 回调不再扫描 Git；Git 字段为显式配置或 UNKNOWN，不能当作运行包身份。
原有审计记录及其哈希不被改写。

## 复验

`quality/mcp-tests.json` 是本地工程回归集合，包含合成故障与真实子进程。
`scripts/mcp_acceptance.py` 可使用 `--mode sdk|legacy|codex`、`--package-root`
（冻结安装目标，包含 bionexus 目录）和一个尚不存在的 `--out` 路径运行。
Codex 模式使用已安装 `codex` 二进制的真实 app-server；通过其 MCP tool/call
接口调用候选，使用隔离测试配置和 ephemeral 会话，不创建模型轮次或改变用户配置。
它验证真实宿主后端，而非桌面会话已有缓存插件已被更新。

Windows 上需要允许 asyncio 的本机 socketpair/IPC；沙箱内若初始化超时，
记为环境阻断，不能用直接驱动函数协程来替代传输验收。
已测平台、Python、SDK、Codex 版本和原始日志必须随候选一起冻结；没有执行的
SDK 版本、其他操作系统、其他宿主、HTTP/SSE 不计为通过。
