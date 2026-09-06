# 原论文核对记录

核对日期：2026-09-04。所有请求和真实返回保存在本目录。

## 检索实际经过

1. Life Sciences Literature 0.1.5 的 `ncbi-entrez-skill/scripts/ncbi_entrez.py` 首次 DOI 检索失败：`ok=false`、`network_error`、`ConnectionError`，进程退出码 1。见 `pubmed-search.response.json`。
2. 经网络权限升级重试成功：DOI `10.1038/nbt.4042` 唯一匹配 PMID `29227470`。见 `pubmed-search-retry.response.json` 及未改写的原始返回。
3. 同一 PubMed 技能 efetch 成功，保存原始 XML、结构化返回、请求、时间和命令。原始 XML 包含完整摘要，结构化预览中的省略号不代表全文缺失。
4. Life Sciences Literature 的 `ncbi-pmc-skill` 成功返回 PMC5784859 版本 1 元数据：作者手稿、公开可读、license_code=TDM、is_retracted=false。此为该元数据记录的状态，不是对所有更正影响的认证。
5. 通过插件返回的 HTTPS XML URL 下载原文，保存 `PMC5784859.1.raw.xml` 与下载散列记录。首次控制台打印遇到 GBK 编码错误；原始 XML 已成功保存，随后本地解析成功。
6. 浏览工具尝试 PMC 网页遇到浏览器挑战；全文阅读依据上述公开 PMC XML，不声称该网页访问成功。

## 已核实的设计与方法

原论文为 Kang et al., *Multiplexed droplet single-cell RNA-sequencing using natural genetic variation*, Nature Biotechnology 36, 89–94 (2018)，在线发表于 2017-12-11。[PubMed](https://pubmed.ncbi.nlm.nih.gov/29227470/) · [PMC 全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC5784859/) · [DOI](https://doi.org/10.1038/nbt.4042)

全文确认 8 位狼疮患者的 PBMC 分成配对 aliquot，IFN-β 100 U/mL 处理 6 小时或不处理，然后分别汇入刺激池和对照池。由此支持供者配对设计，也保留条件与池/文库混杂这一限制。

原文用解复用后的个体作为生物学重复，对每位个体的原始基因计数求和并用 DESeq2 分析。原文提及 qvalue 计算 FDR；本次明确使用 PyDESeq2 0.5.4、`~ donor + condition`、固定 count 过滤和 BH。因此本次不是原论文分析流程的逐项复现，也不将原文其他细胞类型的基因数与本次 CD14+ 子集结果直接比较。

本次 ISG15、IFIT1、MX1、STAT1 的升高与原文报道的广泛 IFN 条件相关转录变化相容。这是研究背景层面的方向核对；没有宣称原文正文逐一验证了本次四个基因的效应量或显著性，也没有重新运行通路富集或机制实验。

论文报告过流式、其他方法或数据的比较；本次没有重新获得或逐项核验这些证据，不能将它们自动升级为本次来源细胞标签的独立确认。

## 更正与证据边界

PubMed 原始返回带有 2020 年 Author Correction：PMID 33057163，DOI 10.1038/s41587-020-0715-9。[更正记录](https://www.nature.com/articles/s41587-020-0715-9)

已确认该更正存在；浏览器返回的出版商页面未提供更正正文，故更正具体范围和对原文方法的影响仍未核实。不能声称更正无关或不影响结果。

文献与本次分析来自同一原始研究，不能算作第二个独立队列或独立复现。BioNexus 对 PubMed 结果封装的 `VALID` 仅表示内容与声明上下文一致。
