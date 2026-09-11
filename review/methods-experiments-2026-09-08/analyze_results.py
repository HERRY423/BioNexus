"""Render saved data; add reporting checks, never change frozen experimental outcomes."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

import figure_style as style
import run_experiments as study

HERE = Path(__file__).resolve().parent


def load(path):
    return json.loads((HERE / path).read_text(encoding='utf-8'))


def verify():
    frozen = study.verify_freeze()
    checks = []
    for stage in ['simulate', 'real-null', 'paired', 'challenge']:
        assert load(f'run-01/{stage}/execution-end.json')['status'] == 'COMPLETE'
        checks.append(f'{stage}: completed, with all outputs retained')
    raw = pd.read_csv(HERE / 'run-01/simulate/dataset-outcomes.csv')
    assert len(raw) == 1600 and raw.seed.nunique() == 800
    assert not raw.duplicated(['seed', 'method']).any()
    assert raw.pvalue_nonfinite.sum() == 0
    assert (raw.discoveries == raw.true_positive + raw.false_positive).all()
    np.testing.assert_allclose(raw.fdp, raw.false_positive / raw.discoveries.clip(lower=1))
    checks.append('800 unique simulation seeds, 1600 paired method results; FDP denominators and finite p values verified')
    rng = np.random.default_rng(442)
    p = rng.uniform(size=1000)
    np.testing.assert_allclose(study.bh(p), stats.false_discovery_control(p, method='bh'))
    checks.append('BH checked against SciPy implementation on 1000 independent random p values')
    matrix = pd.read_csv(HERE / 'run-01/real-null/donor-logmeans.csv', index_col=0)
    source = pd.read_csv(HERE / 'run-01/real-null/gene-outcomes.csv.gz')
    saved = source[(source.partition == 0) & (source.method == 'exact_donor_randomization')].set_index('gene')
    # Independent SciPy exhaustive 70-assignment calculation, not the runner enumeration.
    genes = matrix.columns[:25]
    result = stats.permutation_test((matrix.iloc[:4][genes].to_numpy(), matrix.iloc[4:][genes].to_numpy()),
                                    lambda a, b, axis: np.mean(a, axis=axis) - np.mean(b, axis=axis),
                                    permutation_type='independent', alternative='two-sided', n_resamples=np.inf, axis=0)
    # SciPy doubles the smaller tail. For balanced complementary assignments this equals the absolute-tail test.
    np.testing.assert_allclose(result.pvalue, saved.loc[genes, 'pvalue'], atol=1e-10)
    checks.append('Exact donor permutation checked against SciPy exhaustive 70 assignments for 25 genes')
    repeated = []
    for p in sorted((HERE / 'run-01/paired').glob('*.csv')):
        q = HERE / 'reproducibility-02/paired' / p.name
        assert study.digest(p) == study.digest(q), p.name
        repeated.append(p.name)
    checks.append(f'Independent second local execution reproduced {len(repeated)} CSV artifacts byte-for-byte')
    case_defs = load('run-01/challenge/case-definitions.json')
    assert len(case_defs) == 54
    for case in case_defs:
        p = HERE / 'run-01/challenge/cases' / case['case_id']
        assert study.digest(p / 'de.csv') == case['result_sha256']
        if case['family'] in {'valid_positive', 'valid_negative', 'valid_limited', 'valid_table_presence'}:
            receipt = json.loads((p / 'receipt.json').read_text(encoding='utf-8'))
            assert study.digest(p / 'de.csv') == receipt['result_sha256']
            assert study.digest(p / 'metadata.csv') == receipt['sample_metadata_sha256']
            assert study.digest(p / 'design.csv') == receipt['design_matrix_sha256']
    checks.append('All 54 case result hashes verified; all 12 valid cases match result, metadata and design receipt hashes')
    for rel, h in frozen['source_hashes'].items():
        path = study.REPO / 'src' / rel if rel != 'scrna_deseq.py' else study.REPO / 'skills/single-cell-rna-qc/scripts/scrna_deseq.py'
        assert study.digest(path) == h, f'Product source changed: {rel}'
    checks.append('Current product source still matches pre-execution snapshot; no product fixes mixed into comparison')
    expert = pd.read_csv(HERE / 'reviewer-packet/expert-ratings-BLANK.csv')
    assert (expert.status == 'PENDING').all() and expert.rating.isna().all()
    checks.append('Reviewer packet contains only pending blank ratings; zero external review evidence')
    study.write_json(HERE / 'VERIFICATION.json', {'status': 'PASS', 'checks': checks, 'reproduced_csv_files': repeated,
                                               'verification_type': 'LOCAL_COMPUTATIONAL_NOT_INDEPENDENT_LAB_VALIDATION'})
    # Supplementary Wilson intervals avoid degenerate percentile intervals at binary boundaries.
    rows = []
    for keys, group in raw.groupby(['grid_id', 'method']):
        n, hits = len(group), int(group.any_false_positive.sum())
        z = stats.norm.ppf(.975)
        point = hits / n
        center = (point + z*z/(2*n))/(1+z*z/n)
        half = z*np.sqrt(point*(1-point)/n+z*z/(4*n*n))/(1+z*z/n)
        rows.append(dict(grid_id=keys[0], method=keys[1], n=n, false_positive_datasets=hits,
                         any_false_positive=point, wilson_lo=max(0, center-half), wilson_hi=min(1, center+half)))
    pd.DataFrame(rows).to_csv(HERE / 'simulation-wilson-supplement.csv', index=False)


def figures():
    style.apply_publication_style(style.FigureStyle(font_size=11, axes_linewidth=1.2))
    folder = HERE / 'plots'
    folder.mkdir(exist_ok=True)
    simulation = pd.read_csv(HERE / 'run-01/simulate/summary.csv')
    selected = simulation[(simulation.donor_sd == .8) & (simulation.nonnull_fraction == .2)]
    fig, axes = style.create_subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    categories = [(4, 20), (4, 100), (8, 20), (8, 100)]
    colors = {'cell_welch': '#B74444', 'donor_mean_welch': '#2768A0'}
    labels = {'cell_welch': 'Cell-level Welch', 'donor_mean_welch': 'Donor-mean Welch'}
    for axis, metric, title in [(axes[0], 'fdp', 'A  False discoveries under donor heterogeneity'),
                                (axes[1], 'sensitivity', 'B  True-signal retention under the same conditions')]:
        for offset, method in [(-.18, 'cell_welch'), (.18, 'donor_mean_welch')]:
            subset = selected[selected.method == method].set_index(['donors_per_group', 'cells_per_donor']).loc[categories]
            mean, low, high = (subset[x].to_numpy() for x in [metric, metric + '_lo', metric + '_hi'])
            axis.bar(np.arange(4) + offset, mean, .34, color=colors[method], label=labels[method],
                     yerr=np.stack([mean-low, high-mean]), capsize=3)
        axis.set_xticks(range(4), ['4 / 20', '4 / 100', '8 / 20', '8 / 100'])
        axis.set_xlabel('Donors per group / cells per donor')
        axis.set_ylim(0, 1.05)
        axis.set_title(title, loc='left', fontsize=12)
        axis.set_ylabel('Mean FDP' if metric == 'fdp' else 'Sensitivity')
    axes[0].axhline(.05, color='#777777', linestyle=':', linewidth=1)
    axes[0].legend(loc='upper right', fontsize=9)
    partitions = pd.read_csv(HERE / 'run-01/real-null/partition-outcomes.csv')
    for offset, method, color in [(-.13, 'cell_welch', '#B74444'), (0, 'donor_mean_welch', '#2768A0'), (.13, 'exact_donor_randomization', '#478461')]:
        group = partitions[partitions.method == method]
        x = {'cell_welch': 0, 'donor_mean_welch': 1, 'exact_donor_randomization': 2}[method]
        jitter = np.linspace(-.14, .14, len(group))
        axes[2].scatter(x+jitter, group.discoveries, color=color, s=15, alpha=.65)
        axes[2].plot([x-.2, x+.2], [group.discoveries.median()]*2, color='black', lw=2)
    axes[2].set_xticks(range(3), ['Cell Welch', 'Donor Welch', 'Exact donor'])
    axes[2].set_ylabel('Genes rejected at BH q < 0.05')
    axes[2].set_title('C  Real control-only null: 35 overlapping partitions', loc='left', fontsize=12)
    points = [(0, 0, 'Frozen BioNexus = reject-all', '#2768A0', (.05,.08)),
              (1, 33/42, 'Deterministic checklist', '#B74444', (.46,.86)),
              (.75, 24/42, 'Heuristic advisory (exploratory)', '#C58127', (.16,.65)),
              (1, 1, 'Accept-all', '#777777', (.63,.98))]
    for x, y, label, color, textpos in points:
        axes[3].scatter(x, y, s=65, color=color, zorder=5)
        axes[3].annotate(label, (x,y), xytext=textpos, textcoords='data', fontsize=9,
                         arrowprops=dict(arrowstyle='-', color=color, lw=.7))
    axes[3].set(xlim=(-.04,1.08), ylim=(-.04,1.08), xlabel='Valid-case retention (12 cases)', ylabel='Unsupported acceptance (42 cases)')
    axes[3].set_title('D  Audit challenge: safety and retention jointly', loc='left', fontsize=12)
    style.finalize_figure(fig, folder / 'figure-1-operating-characteristics', formats=['png', 'pdf', 'svg'], dpi=300)

    model = load('run-01/paired/summary.json')
    signature = pd.read_csv(HERE / 'run-01/paired/cross-cohort-signature.csv')
    scores = pd.read_csv(HERE / 'run-01/paired/parse-donor-signature-scores.csv')
    fig, axes = style.create_subplots(1, 3, figsize=(14, 4), constrained_layout=True)
    for i, row in enumerate(model['model_comparisons']):
        axes[0].bar(i-.17, row['significant_unpaired'], .32, color='#999999', label='Condition only' if i == 0 else None)
        axes[0].bar(i+.17, row['significant_paired'], .32, color='#2768A0', label='Donor + condition' if i == 0 else None)
    axes[0].set_xticks([0,1], ['GSE96583 (8 donors)', 'Parse (12 donors)'])
    axes[0].set_ylabel('Significant genes in 2,000-gene panel')
    axes[0].set_title('A  Design sensitivity', loc='left')
    axes[0].legend(fontsize=9)
    axes[1].scatter(signature.kang_log2fc, signature.parse_log2fc, color='#2768A0', alpha=.7, s=16)
    axes[1].axhline(0, color='#999999', lw=.8)
    axes[1].axvline(0, color='#999999', lw=.8)
    axes[1].set(xlabel='GSE96583 paired log2 fold change', ylabel='Parse paired log2 fold change')
    axes[1].set_title('B  Discovery top-100: 95% sign agreement', loc='left')
    axes[2].scatter(range(len(scores)), scores.score, color='#2768A0', s=25)
    axes[2].axhline(0, color='#999999', lw=.8)
    axes[2].set(xticks=range(len(scores)), xticklabels=[str(i+1) for i in range(len(scores))], xlabel='Parse donor (opaque order)', ylabel='Direction-aligned mean log-CPM change')
    axes[2].set_title('C  Exploratory signature diagnostic', loc='left')
    style.finalize_figure(fig, folder / 'figure-2-paired-reanalysis', formats=['png', 'pdf', 'svg'], dpi=300)


def report():
    full = load('run-01/challenge/summary.json')
    exploratory = load('exploratory-01/summary.json')
    frame = pd.read_csv(HERE / 'run-01/simulate/summary.csv')
    snapshot = load('FREEZE.json')
    # Derived table deliberately avoids treating blanket rejection as issue localization.
    group = pd.read_csv(HERE / 'exploratory-01/original-check-localization.csv')
    families = ['wrong_result_hash', 'changed_result', 'failed_fit', 'wrong_design']
    n_bad_binding_assessed = int((group[group.family.isin(families)].original_binding_status == 'ASSESSED').sum())
    body = f'''# BioNexus 方法学实验：实际完成结果与投稿边界

**结论：本轮已完成本地可执行的统计对照、真实数据重分析、审计挑战和机制消融。当前数据不支持“BioNexus 已实现低错误率且保留有效结论”的产品优越性主张。** 实验最有价值的发现是把下一步缺口定位为可复现的具体失败机制，而不是再增加抽象规范。

受测对象是 `{snapshot['git_head']}` 加当时尚未提交的本地改动，实际导入冻结副本；不是公开 rc.5 发布包、不是未见数据上的外部评测。冻结时间：{snapshot['created_utc']}。原始代码、输入、协议和执行器均有 SHA-256 记录。原始结果未被修复覆盖。

## 1. 完成了哪些真正的实验

| 实验 | 实际执行量 | 核心结果 | 能支持的结论 |
|---|---:|---|---|
| 已知真值模拟 | 800 数据集、1,600 次方法评估、320,000 条基因结果 | 存在供体异质性时，细胞检验的平均 FDP 为 70.8%–78.1%（有信号各层）；供体均值检验约 0%–2.7% | 统计单位错误确有严重后果；不能把它当 BioNexus 的独有创新 |
| 真实对照组空效应分组 | 2,155 个对照 CD14+ 单核细胞、8 供体、1,000 基因、35 种独特分组 | 细胞检验 35/35 有发现，中位 229 基因；供体 Welch 为 1/35；精确供体检验为 0/35 | 忽略供体可在人工分组中产生大量发现；35 个分组不是独立研究 |
| 两队列配对模型 | GSE96583 8 供体和 Parse 12 供体；共同 2,000 基因；4 个 PyDESeq2 模型 | 加入供体后显著基因数分别 1,044→1,219、964→1,516 | 模型设计会实质改变结果；更多显著基因不等于更真实 |
| 实际结果审计挑战 | 18 错误/正确家族 × 3 改写 × 6 对照臂 = 324 次判定 | 原始 BioNexus 错误案例放行 0/42，但有效案例保留 **0/12** | “全部拦住”不能证明净收益 |
| 事后机制消融 | 同一 54 案例 × 2 实验臂 = 108 次判定 | 仅将极小 P 值提示降为建议：有效保留 **9/12**，错误放行 **24/42** | 放宽启发式会暴露更深的绑定与陈述核对缺口 |

模拟每层仅 50 个随机种子，区间是 Monte Carlo 不确定性，不能外推真实研究分布。尤其在供体异质性为 0.8 时，供体均值 Welch 的真信号敏感度只有 0.1%–1.25%；它的低 FDP 部分伴随很大功效代价。论文必须同时展示错误率和有用结论保留。无供体异质性的条件是同样保留的阳性控制，见全量 CSV，不能只挑最有利的场景。

![统计、真实空效应及审计结果](plots/figure-1-operating-characteristics.png)

## 2. 哪些失败最影响投稿

**极小 P 值启发式造成有效结果误拦。** 实际供体配对 PyDESeq2 表含 18 个 P<1e-100 的基因、没有 P=0。BFA-001c 对所有案例给出高影响问题，掩盖了其他机制是否工作。报告文字虽然说不能仅凭小 P 值否定供体结果，执行状态却确实阻止了通过。

**“执行绑定已核查”并不等于执行绑定真的成立。** 错误结果哈希、结果被改动、fit_status=FAILED、公式与实际设计矩阵冲突四个家族共 {n_bad_binding_assessed}/12 个案例仍被标为 `analysis_execution_binding=ASSESSED`。首轮顶层拒绝源于无关的小 P 值提示，不是成功识别这些破坏。不能据此声称有真实 artifact-binding 消融证据。

**具体结果陈述尚未与表格核对。** 不存在的基因、未显著基因被声称显著、显著基因被否定、全表被错误写成零显著等案例，定向声明检查仍给出 ASSESSED。相反，实际正效应的 IL1RN “upregulated”陈述被解析为因果请求而拒绝；错误的“downregulated”也以因果问题被拒绝，不能算正确核对了方向。

**配对关系尚未贯穿现有包装器。** 受测 `scrna_deseq.py` 的实际模型为 `~ condition`。本轮使用官方 PyDESeq2 直接拟合 `~ donor + condition` 作诊断比较，未冒充包装器已经修复。两个 GSE96583 模型都记录了离散度趋势拟合切换到均值趋势的警告，未隐去。

`case-outcomes.csv` 原始字段 `issue_identified` 表示机械高风险/拒绝标志，**不能用作正确定位准确率**：拒绝所有的边界对照也会有该标志。正确定位应读取每案例具体规则与证据；原始检查级结果已另存 `original-check-localization.csv`。没有给不存在的基因检查、哈希检查或人类判断补造成功标签。

## 3. 正向结果应该如何写

在预先限定的 2,000 个共同高丰度基因中，GSE96583 配对模型的前 100 个基因在 Parse 中有 **95%** 方向一致。Parse 的 12 个供体方向对齐签名分数，4,096 种符号翻转的双侧诊断 p=**0.0009765625**。这是两个已经使用过的公开数据集上的探索性一致性，基因筛选还用到了两队列的丰度信息；不是独立盲法验证，不能替换旧的预注册端点或其阴性结果。

Parse 输入来自此前 725,031 个细胞的聚合；本轮实际读入的是 24 行 pseudobulk，没有重新下载并重算 725,031 个细胞。原提取记录中的 **30,634 个细胞元数据/表达条目数量差异**及 PASS_WITH_RETAINED_SOURCE_METADATA_COUNT_DISCREPANCIES 状态保留。两队列都是混合 PBMC，细胞组成变化不能被本轮结果排除。签名诊断使用 2,000 基因面板内的 library normalization，符号翻转还依赖零假设下供体分数的符号可交换性。

![配对模型与跨队列诊断](plots/figure-2-paired-reanalysis.png)

## 4. 下一步只应收敛到一个可证伪承诺

> 对已完成的多供体差异表达分析，BioNexus 核验声明引用的基因、比较方向、显著性与实际执行证据；证据不能闭合时明确返回未评估，并让科学负责人裁决。本轮尚未证明其优于常规审阅或可节省实验室时间。

优先顺序：① 真正核验结果/counts/样本表/设计矩阵和拟合状态的绑定；② 表格字段与逐条陈述核对、正确处理否定与范围；③ 在这些证据核验成立后降低小 P 值启发式的误拦；④ 支持实际配对模型与不可辨识设计检查；⑤ 冻结修复版本并在外部未见任务上比较真实 LLM/清单/人工流程。这些失败例可作为回归集，但回归通过不再算独立确认实验。

## 5. 已交付和不能声称完成的部分

已有 `PROTOCOL.md`、`FREEZE.json`、冻结源码、完整随机种子与基因级结果、四个模型的矩阵/结果/回执、54 个逐案输入和审计输出、消融结果、两张 PNG/PDF/SVG 图、英文方法与结果补充材料、盲评交接包和空白时间记录表。第二次独立本地执行的 **14 个 CSV 文件逐字节一致**，BH 与精确置换分别通过 SciPy 对照核验。

真实模型四臂比较 **NOT_RUN**（无配置 API 凭据）；外部专家评审、实验室净收益、盲法外部复制 **NOT_ESTABLISHED**。没有联系外部人员，没有投稿、发布或改写公开认证。这些实验推进了计算证据和缺陷定位，**尚未补齐 SCI 一区方法学论文的全部主要缺口**。

复现：在原仓库、冻结依赖版本环境运行 `python review/methods-experiments-2026-09-08/run_experiments.py <stage> --run-id <新的目录名>`；stage 为 simulate / real-null / paired / challenge，challenge 的 `--real-run-id` 指向已有 paired 结果目录。既有目录会拒绝覆盖。数据来源和位置见 FREEZE.json；原始两数据文件必须可用且哈希一致。这是本地可复现证明，尚无跨机器重现结论。
'''
    (HERE / 'REPORT.zh-CN.md').write_text(body, encoding='utf-8')
    arm_rows = []
    for row in full['arms']:
        arm_rows.append(f"| {row['arm']} | {row['invalid_accepted']}/42 | {row['valid_retained']}/12 |")
    for row in exploratory['arms']:
        arm_rows.append(f"| {row['arm']} (post-outcome) | {row['invalid_accepted']}/42 | {row['valid_retained']}/12 |")
    english = '''# Computational methods and results supplement — BN-METHODS-20260908

Draft based on executed local experiments; not an independently validated submission-ready manuscript.

## Study design and reproducibility

The evaluated software was a snapshot of working-tree BioNexus based on commit bdf38e1942ff4f517ae696c3c413bf481d8ebac4, including uncommitted pre-existing changes. Source files, data, analysis protocol and runner were hashed before execution; the copied source was imported during evaluation. This was a prospective local analysis freeze, not public preregistration. Authors had previously inspected both software and historical data. The original source was not changed during the experiment. Python/package versions are in FREEZE.json. No observations or failed cases were excluded from the completed stages.

## Controlled simulations

Eight hundred independently seeded negative-binomial datasets represented the factorial combination of 4/8 donors per group, 20/100 cells per donor, donor log-expression SD 0/0.8, and 0/20% non-null genes (50 datasets per stratum; 200 genes each). Baseline gene means followed a lognormal distribution (log mean 1.5, SD 0.6); donor-specific log shifts were shared across cells. Count dispersion was 0.3. Non-null genes had balanced positive/negative log effects of ln(2). Two-sided Welch tests were applied either to log1p cell counts or to donor means of the same transformed counts. BH adjustment was applied separately within each table at 0.05. This intentionally simple comparison isolates statistical-unit effects; it is neither a comprehensive benchmark of DE packages nor an evaluation of BioNexus-specific statistical innovation.

Mean FDP, false-positive dataset frequency and sensitivity were computed with all seeds retained; FDP was zero in the absence of discoveries. Sensitivity was undefined in all-null datasets. Within-stratum 95% percentile intervals used 2,000 bootstrap resamples of datasets, not genes. Fifty replicates imply coarse Monte Carlo precision. Supplementary post-outcome Wilson intervals were added for binary frequencies to avoid degenerate bootstrap intervals at the boundaries. Under donor heterogeneity and non-zero signal, cell tests yielded mean FDP 0.708–0.781. Donor-mean tests yielded 0–0.027, with sensitivity only 0.001–0.0125 under these difficult settings. Reduced errors therefore coexisted with considerable loss of power. All zero-heterogeneity and all-null controls are retained in the source data.

## Public-data negative control

The real-data negative control used 2,155 control-condition CD14+ monocytes from eight GSE96583 donors. The 1,000 most abundant genes with total counts >=10 were selected before generating artificial donor-group labels. Counts were normalized to 10,000 total counts per cell and log1p transformed. All 35 unique balanced 4-versus-4 donor partitions were enumerated; complementary assignments gave identical two-sided results. Cell-level Welch, donor-mean Welch, and exact donor-label randomization tests were BH-adjusted separately. Individual-cell tests produced discoveries in 35/35 partitions (median 229 genes, maximum 348); donor Welch in 1/35 (one gene); exact donor randomization in 0/35. These overlapping partitions support conditional assignment diagnostics, not 35 independent studies. The artificial-assignment null does not deny actual between-donor biological variation. The exact two-sided minimum p=1/35 and multiple-testing adjustment limit power.

## Paired public-cohort reanalysis

GSE96583 PBMC counts were summed by donor and condition (16 samples, eight donors). The existing Parse-10M pseudobulk artifact contained 24 samples from 12 donors; its extraction metadata reported 725,031 source cells. This study reanalyzed the aggregate artifact rather than re-extracting those cells. Its recorded output hash was verified; metadata/expression-count discrepancies involving 30,634 cells were retained. Genes required >=10 counts in >=4 samples in each cohort. The 2,000 common genes with greatest mean library-normalized abundance pooled across the cohorts formed a fixed comparison universe. This restriction is an analysis limitation and not an unseen validation holdout.

Official PyDESeq2 0.5.4 models used either ~condition or ~donor+condition, refit_cooks=True, alpha=0.05 and two CPUs. Model matrices, ranks, residual degrees of freedom, native adjusted p values, and BH adjustment over all finite raw p values were exported. Residual degrees of freedom changed from 14 to 7 in GSE96583 and 22 to 11 in Parse. Significant-gene counts changed from 1,044 to 1,219 and from 964 to 1,516, respectively. The corresponding set Jaccard indices were 0.844 and 0.635; numbers of effect-direction changes were 15 and 32. Increased discovery counts alone cannot establish improved accuracy. Both GSE96583 fits reported failure of the parametric dispersion trend and the library's fallback to a mean trend; these warnings were retained.

A fixed signature of the 100 smallest paired-model p values in GSE96583 exhibited 95% effect-direction agreement in Parse. For each Parse donor, the mean direction-aligned log2(CPM+1) difference across this signature was computed using panel-normalized libraries. Exhaustive two-sided donor sign flipping (4,096 assignments) yielded p=0.0009765625. This exploratory diagnostic assumes independent donor scores and sign exchangeability under the null. Mixed PBMC composition, panel normalization, prior use of these data and cross-cohort abundance selection limit interpretation. It does not supersede historical preregistered endpoints or establish independent replication.

## Audit challenge and controlled ablations

The real GSE96583 paired-model table, recorded design matrix and actual execution receipt provided 54 cases in 18 prespecified families with three correlated English phrasings. Twelve cases contained bounded valid statements; 42 contained contradictory table statements, absent genes, causal/clinical overclaims or deliberately damaged evidence. Labels were author-defined logical/consistency labels, not expert ground truth. The four genuine-record valid families retained matching table, metadata and design hashes. The full audit, two input-omission ablations, a transparent deterministic checklist and accept-all/reject-all boundary controls were evaluated. None was described as a live LLM or human comparator.

| Arm | Unsupported cases accepted | Valid cases retained |
|---|---:|---:|
''' + '\n'.join(arm_rows) + '''

The frozen audit rejected all cases, yielding zero valid retention. All cases triggered the extreme-p heuristic BFA-001c because the actual donor-model table contained 18 p values below 1e-100 (none equal to zero). A post-outcome in-memory ablation changed only that finding's severity to advisory, retaining the finding and unchanged input data. This retained 9/12 valid cases while accepting 24/42 invalid cases. The post-outcome analysis is explicitly exploratory and not a shipped product revision.

The original binding check nevertheless marked all 12 cases with wrong output hashes, altered results, failed fit status or a conflicting model formula ASSESSED. Several false gene-level statements were also marked ASSESSED. Conversely, the valid IL1RN upregulation sentence was classified as a causal request. The original case-outcome field named issue_identified is only a mechanical rejection/high-severity flag, including a flag in the reject-all control; it is **not a correctly localized error measure**. Generic rejection cannot be credited with detecting an unrelated altered artifact. Check-level results and all raw findings are supplied for audit.

## Verification, limits and remaining studies

An independent second local execution reproduced all 14 model/input/signature CSV artifacts byte-for-byte. BH was checked against scipy.stats.false_discovery_control and the exact null calculation against SciPy's exhaustive 70-assignment test for 25 genes. All 800 simulation seeds and 1,600 method records were checked for completeness, finite p values and correct denominators. This is computational verification within one environment, not independent laboratory validation or proof of biological truth.

No live model calls were made because no provider API credentials were configured. External expert labels, human-time savings, independent laboratory adoption and blinded external replication remain unestablished. A randomized-ID reviewer packet and blank expert/time forms are provided for a future study; there are zero completed ratings. These findings support concrete engineering priorities and bounded statistical-mechanism conclusions. They do not establish BioNexus superiority, scientific certification, clinical validity or readiness for acceptance in a Q1 journal.

## Figure legends

Figure 1. Joint operating characteristics. A–B: mean FDP and sensitivity at donor SD 0.8 and 20% non-null genes, 50 independent datasets per stratum; error bars are 95% percentile bootstrap intervals over 2,000 resamples. All other strata are in source CSV. C: numbers of discoveries in each of 35 dependent artificial donor partitions; horizontal segments show medians. D: unsupported acceptance plotted jointly with valid retention in developer-authored cases. The advisory point is an explicitly post-outcome ablation; the frozen product coincides with reject-all.

Figure 2. Paired-design sensitivity and exploratory cross-cohort consistency. A: significant genes in the fixed 2,000-gene panel; counts are not accuracy measures. B: effects for the 100 discovery-ranked genes, with 95% directional agreement. C: 12 Parse donor signature scores; donors, not genes, form the sign-flip units. These are already-known public datasets, and no independent blinded labels were obtained.

## References

1. Squair JW et al. Confronting false discoveries in single-cell differential expression. Nature Communications 12, 5692 (2021). https://www.nature.com/articles/s41467-021-25960-2
2. PyDESeq2 0.5.4 official documentation. https://pydeseq2.readthedocs.io/en/stable/auto_examples/plot_minimal_pydeseq2_pipeline.html
3. Nature, Reporting Life Sciences Research. https://www.nature.com/documents/nr-reporting-life-sciences-research.pdf
'''
    (HERE / 'METHODS_RESULTS.md').write_text(english, encoding='utf-8')


if __name__ == '__main__':
    verify()
    figures()
    report()
    print('Verification, figures and results documents complete.')
