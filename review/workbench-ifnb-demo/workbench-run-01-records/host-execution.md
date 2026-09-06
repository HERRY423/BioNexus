# 本次宿主执行记录

运行目录：`C:\Plugin\BioNexus\review\workbench-ifnb-demo\workbench-run-01`

记录目录：`C:\Plugin\BioNexus\review\workbench-ifnb-demo\workbench-run-01-records`

## 宿主与授权

- 实际宿主：Codex desktop，当前本地任务；项目目录 `C:\Plugin\BioNexus`。
- 当前任务 ID：`01a06d31-f669-72c3-9d02-d8d036f5d744`，来源为本次 `open_in_codex` 工具返回。
- 宿主版本：
- 模型精确版本：
- 用户明确批准六步探索性分析及文献、审计和草稿整理；批准不代表人工确认生物学结论，不授权发布。
- 旧计划文件仍保存原来的待批准状态，作为历史快照；后续授权单独保存在 `authorization.json` 和本任务用户消息中。
- 运行性质：宿主调用本地 Python；未执行 NGS 注册工作流。未调用 FASTQ、STARsolo、Nextflow 或 Snakemake 工作流。

## 实际命令与时间

解释器：`C:\Users\13264\anaconda3\python.exe`，Python 3.13.9。

工作目录：`C:\Plugin\BioNexus`。

```text
python scripts/doctor.py
python review/workbench-ifnb-demo/fetch_inputs.py
python -u review/workbench-ifnb-demo/run_analysis.py --out review/workbench-ifnb-demo/workbench-run-01
```

完整 argv、UTC 起止时间与退出码见 `commands.json`。分析开始 `2026-09-04T16:30:48.185386+00:00`，结束 `2026-09-04T16:31:06.496100+00:00`，退出码 0（本地时间 09:30:48–09:31:06 PDT）。

宿主工具证据：`functions.exec → exec_command` 初始返回 shell session ID `43266`、chunk `26c685`；`write_stdin` 返回完成 chunk `dea3e8`、exit_code 0。这些只是当前会话中的执行引用，不是独立第三方签名。

`analysis.stdout.log`、`analysis.stderr.log` 保留模型执行输出；其中记录 0 个 outlier genes 被替换。`fetch-inputs.stdout.log` 保留三个输入的 MATCH 散列。

## 环境与来源

- `environment.json`：Python、Windows 与工作目录信息。
- `python-packages.stdout.log`：运行时完整包版本清单；主要包 PyDESeq2 0.5.4、AnnData 0.13.1、NumPy 2.3.5、pandas 2.3.3、SciPy 1.16.3、Matplotlib 3.10.6。
- `doctor.stdout.log`：BioNexus 1.0.0-rc.4，tier=full；不等于所有可选后端就绪或科学认证。
- `input-sha256.json`：实际输入散列；`initial-output-sha256.json` 包含初始输出和 manifest 散列。
- `git-head.stdout.log`、`git-status.stdout.log`：已有修改的仓库状态。
- `source-snapshot/`、`source-sha256.json`：运行前实际分析入口与 BioNexus Python 源码快照及散列。
- 主入口直接导入 `C:\Plugin\BioNexus\src\bionexus`；此源码身份与安装插件名称、版本、MCP 后端身份分开记录。
- `verification.json`：完成结果的配对、设计、过滤范围、表格、散列检查；不是外部科学复现。

## 实际插件贡献

| 插件 | 安装版本 | 实际使用 | 证据 |
|---|---|---|---|
|NGS Analysis Workbench|0.2.16|读取并应用 understand-ngs-data、design-ngs-analysis；实时 list_workflows/list_compute_targets|前一轮记录，已复制到 audit/preflight-*；12 个注册工作流不覆盖本次起点/终点|
|Life Sciences Literature|0.1.5|PubMed DOI 搜索、efetch、PMC 元数据技能脚本；解析返回全文链接|literature/ 中请求、原始返回、失败及成功记录|
|BioNexus Reliability|1.0.0-rc.4|前一轮 MCP 预执行 warrant；本次 doctor、入口内身份审计、external-evidence-audit、完成后本地关联主张规则检查|audit/、analysis_manifest.json、doctor 日志|

NGS 的 inspect_compute_target/get_runtime_environment 在前一轮未返回可用结果；不能据此宣称 NGS 运行就绪。Literature 初始网络错误与成功重试均保留。BioNexus 源码审计不等同于安装 MCP 代码认证。

## 审计状态与人类决定

- 预执行 `NEEDS_DATA`：首次有效请求未使用接口要求的供者数量字段；并非本地实际缺少供者。
- 补充已核验数据后的 `PERMITTED`：可运行性；同一预执行返回的结论层仍为 `ABSTAIN` / `NOT_WARRANTED`。原返回未修改。
- 本次身份审计 `TENTATIVE`：来源标签缺少独立身份证据与校准。
- 完成后的两个封装审计 `VALID`：仅内容和声明上下文完整；`DECLARED_NOT_AUTHENTICATED`、`UNASSESSED`、`accepted_for_claim_support=false` 均保留。
- 本地 `DeterministicWarrantEngine` 完成后关联检查返回 `WARRANTED` / `SUPPORTED`：针对当前队列的限定关联句，输入为本次已检查的事实。它不是外部证据 Ledger 的已批准支持边，也不是人工裁决。
- 条件与文库混杂未消除；机制、因果、细胞身份与临床主张不在该关联检查认可范围内。
- Human Scientific Adjudication：`PENDING`；没有填入研究者姓名、审稿者、人工签名或最终接受记录。

## 图与截图

本次已通过 view_image 实际检查新生成的 `showcase_figure.png`。`open_in_codex` 返回 `queued`，表示打开请求已排队，不把它写成已确认窗口显示。图还将在会话中直接展示。

真实截图路径目前为空；用户请求的是四张截图的具体取景建议，见 `SCREENSHOT_GUIDE.zh-CN.md`。不将图文件、说明文档或渲染截图伪装成宿主历史截图。

保留原 manifest 状态 `COMPLETED_LOCAL_REHEARSAL_NOT_WORKBENCH_EVIDENCE`；本文件提供额外会话记录，不将该字段改写为 Workbench 集成认证。
