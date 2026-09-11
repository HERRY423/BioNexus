# 稳定边界与可持续维护：实施记录

本轮已落实到源码、兼容测试、安装包和发布配置；尚未发布新版本，也未执行 GitHub 托管 CI。

## 已实现

1. **只读离线核验入口**：`bionexus audit-de-verify DIRECTORY`，以及标准库独立读取器 `src/bionexus/de_bundle.py`。输出区分 CONSISTENT、INVALID、UNSUPPORTED_SCHEMA、LEGACY_LIMITED；不会运行分析、联网、修改输入或授权科学结论。
2. **可读报告与机器结果共同绑定**：新 v1 审阅包新增完整性字段，对 audit.json、audit-full.md、REVIEW.md 的实际字节做 SHA-256 绑定。人工评审文件保留可编辑，不伪装成经过身份认证的评审证据。
3. **历史兼容**：原有 schema、audit_sha256 和 CLI 参数保留。旧包返回 LEGACY_LIMITED，明确缺少可读报告哈希，不自动迁移或补写。历史合成示例保存为字节冻结的兼容夹具；Git 属性阻止换行转换破坏原始哈希。
4. **拒绝含糊输入**：未知 schema、profile 和审计状态不会成为成功；重复 JSON 键、非有限数值、文件越界、缺失文件、状态矛盾和过大的报告会明确失败。可选外部 manifest 摘要用于检测相对交接记录的改动；摘要本身不认证生产者。
5. **持续兼容检查**：源码 CI 和构建后安装包均接入离线兼容检查。发布流程从指定标签检出源码，核对标签对应提交，并使用同一标签创建 Release，避免手动发布时混用当前分支。
6. **可执行维护约定**：MAINTENANCE.md、兼容契约、支持文档和 PR 模板明确维护范围、真实责任人、科学规则变更、依赖更新、迁移及回退。SECURITY.md 移除了过时的稳定版本表和无实际保障的响应时限，说明出网守卫只覆盖经过其接口的调用。

## 验证结果

- 定向测试 **65 通过、1 跳过**。跳过原因是本机无法创建符号链接；不宣称该场景已在 Windows 实测通过。
- 新增和修改的 Python 文件通过 Ruff；`git diff --check` 通过。
- canonical registry 与插件镜像检查通过；镜像通过标准编译器同步，未手工编辑生成副本。
- 实际构建 wheel，并安装至隔离目标目录；核验器、调用入口及两个 schema 与源码字节一致。
- 安装包通过历史包读取、完整报告核验、报告改动检测、未知 schema 拒绝及无科学授权边界检查。
- 安装包教学示例仍为 NEEDS_REVISION，文件核验为 CONSISTENT；汇总纳入案例数为 0，净收益仍为 NOT_ESTABLISHED。
- wheel SHA-256：`f2839bceccb3c80b40a6436ce621b12682735616cb57ad43a9f9153b8331ad20`。

核验明细见 [VERIFICATION.json](VERIFICATION.json)。安装使用 `--no-deps --no-index --target`，复用了现有依赖，因此不是全新机器安装证明。构建保留了既有 license 元数据格式弃用警告，见 build-output.txt。

## 边界与后续

文件一致性不证明统计拟合完成、不验证原始数据内容、不认证外部生产者，也不替代科学负责人裁决。此前方法学实验暴露的执行事实绑定、逐条声明核对和有效结论误拦问题，不属于本轮维护接口改动，原实验结果保留。

本轮新增功能属于开发源码中的 Unreleased 改进，尚未进入公开 rc.5 安装包。GitHub CI、跨机器安装、重新安装到真实宿主及正式发布仍需相应执行证据。文档规定每项工作需指定实际责任人，没有编造已成立的维护团队或独立专家委员会。

入口文档：[维护政策](../../MAINTENANCE.md)、[兼容契约](../../docs/de-bundle-compatibility.md)、[支持说明](../../SUPPORT.md)。
