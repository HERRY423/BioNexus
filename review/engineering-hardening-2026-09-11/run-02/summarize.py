"""Assemble a local evidence report from completed runs, without upgrading authority."""
import hashlib
import json
import platform
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def read(name):
    return json.loads((HERE / name).read_text(encoding='utf-8'))


def results(name):
    suite = ET.parse(HERE / name).getroot().find('testsuite')
    assert suite is not None
    result = {k: int(suite.attrib[k]) for k in ('tests', 'failures', 'errors', 'skipped')}
    result['passed'] = result['tests'] - result['failures'] - result['errors'] - result['skipped']
    result['seconds'] = float(suite.attrib['time'])
    result['skip_reasons'] = [n.attrib.get('message') for n in suite.iter('skipped')]
    assert result['failures'] == result['errors'] == 0, result
    return result


full = results('tests.full.xml')
core = results('core-verified/tests.xml')
de = results('de-verified/tests.xml')
trace = read('de-verified/report.json')
assert trace['test_execution'] == 'PASSED' and not trace['errors']
assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest
           for p, digest in trace['source_sha256'].items())
assert read('wheel-smoke-final.json')['status'] == 'PASS'
assert 'Success: no issues found in 18 source files' in (HERE / 'types.final.log').read_text()
assert 'All checks passed!' in (HERE / 'ruff.final.log').read_text()
floors = json.loads((ROOT / 'quality/coverage-baseline.json').read_text())
coverage = {key.replace('\\', '/'): value['summary'] for key, value in read('core-verified/coverage.json')['files'].items()}
rows = []
for path, floor in floors['files'].items():
    s = coverage[path]
    line = s['covered_lines'] / s['num_statements'] * 100
    branch = s['covered_branches'] / s['num_branches'] * 100
    assert line >= floor['line'] and branch >= floor['branch']
    rows.append(f"| {Path(path).stem} | {line:.2f}% | {branch:.2f}% | {floor['line']:.2f}% / {floor['branch']:.2f}% |")
source_paths = sorted(set(trace['source_sha256']) | {
    'mypy.ini', 'quality/core-tests.json', 'quality/coverage-baseline.json',
    'docs/engineering-quality.md', 'tests/unit/test_core_architecture.py',
    'tests/unit/test_contract_input_boundaries.py', 'tests/unit/test_cli_compatibility.py',
    'tests/unit/test_spec_registry.py', 'tests/unit/test_de_pilot.py'})
source_hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in source_paths}
summary = {'status': 'LOCAL_ENGINEERING_VERIFIED', 'scientific_authorization': 'NONE',
           'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
           'python': platform.python_version(), 'full_unit': full, 'core': core, 'de_requirements': de,
           'typed_modules': 18, 'coverage_protected_modules': 9,
           'cli_lines': len((ROOT / 'src/bionexus/cli.py').read_text(encoding='utf-8').splitlines()),
           'hosted_ci': 'NOT_VERIFIED', 'source_sha256': source_hashes}
(HERE / 'summary.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
total = read('full-coverage.json')['totals']
line = total['covered_lines'] / total['num_statements'] * 100
branch = total['covered_branches'] / total['num_branches'] * 100
report = f'''# 截图剩余工程问题修复 — 第二轮

本轮三个阶段均已完成本地实现与验证。工作基于 `{summary['base_commit']}`，改动留在工作区。截图中的“零覆盖率门禁、零类型检查、大型 CLI”已持续处理；草案状态、独立校准与科学认证不靠工程测试升级。

## 阶段一：扩大门禁并修复真实反例

- 类型检查从 6 个扩至 18 个模块，覆盖输入完整性、规则分类、策略、研究者覆写记录、结果汇总和规范解析。实际接口 `AuditReport` 约束结果写出端的两种呈现方法，独立适配器不需继承审核引擎。
- 修复计数检查漏掉负整数、样本窗口之后的异常以及仅凭 counts/raw 名称通过的问题。完整核对实际矩阵；声明层失败不切换来源，检查失败不形成通过结论。
- 修复未知执行状态和旧格式未知 fidelity 被算成初步结论的问题；预检许可包括 `PERMITTED_WITH_LIMITS`，序列化往返均保留未评估状态。
- 修复共享单一批次的误报、多个独占批次的漏报，以及未使用的细胞分类导致审核崩溃。修复默认规则说明返回元组的类型错误。
- 新反例先复现了 10 个计数案例失败、8 个状态案例失败和 3 个元数据案例失败，再完成修复。这些是参数化案例数量，并非 21 个独立根因。

## 阶段二：完成 CLI 职责拆分与依赖约束

45 个参数注册块移入原有 11 个命令模块，CLI 从上轮 1,349 行降到 **{summary['cli_lines']} 行**。命令顺序、参数、默认值、别名、帮助文本及旧处理函数导入路径通过冻结契约核对。12 个核心模块的静态依赖方向与命令包禁止反向导入 CLI 的规则进入核心测试。

其余领域模块保留已有公共路径。未按文件数量强行改包名，也未为增加 ABC 数量添加继承体系。

## 阶段三：规范登记、执行证据与回归

规范登记新增拒绝重复 YAML 键、非对象、未知 schema、空清单、非法生命周期和越界文件名的检查。25 份规范内容与成熟度未改变。计数审核新增正反例接入已有 BNS-II-001..003 映射；本轮仍是 7 条有界要求测试与 2 条明确缺口，映射外要求不视为通过。

| 验证 | 结果 | 证据 |
|---|---|---|
| 完整本地 unit 配置 | **{full['passed']} passed，{full['skipped']} skipped，1 deselected**；{full['seconds']:.1f} 秒 | [日志](tests.full.log)、[JUnit](tests.full.xml) |
| 固定核心覆盖率门禁 | **{core['passed']} passed，{core['skipped']} skipped**；9 模块逐项门禁通过 | [日志](core-verified.log)、[覆盖率](core-verified/coverage.json) |
| 类型检查 | 18 模块通过 | [日志](types.final.log) |
| DE 要求执行证据 | {de['passed']} passed；7 条有界测试、2 条保留缺口 | [报告](de-verified/report.json)、[收据](de-verified/receipts.json) |
| 真实 AnnData 与输入反例 | 77 passed | [日志](input.final.log) |
| 安装包与旧结果包 | wheel 隔离目录加载、11 模块、冻结参数和旧包限制均通过 | [报告](wheel-smoke-final.json) |
| 静态与注册表检查 | Ruff、规范/镜像漂移、历史结果包契约通过 | [Ruff](ruff.final.log)、[注册表](registry.log)、[契约](bundle-contract.log) |

完整本地配置的全源码行覆盖率为 {line:.2f}%，分支覆盖率为 {branch:.2f}%；它与固定核心门禁的测试范围不同。下表是固定核心测试的实测值，全部原有下限保持或提升：

| 模块 | 行覆盖率 | 分支覆盖率 | 当前行 / 分支下限 |
|---|---:|---:|---:|
{chr(10).join(rows)}

## 证据范围与尚未建立的事项

- 本机 Python {summary['python']}；完整配置排除 `test_scvi_smoke.py` 和 `flagship_data`。7 个跳过是 Windows 符号链接权限 1 个、POSIX Slurm 路径 6 个，未算作通过。托管 CI、Python 3.10–3.12 跨系统矩阵本轮未运行或核验。
- 两次输入整合测试因旧 Numba 缓存路径访问缓慢中断；改用新目录后 77 项通过。单独校准诊断运行中断，不作为完成证据；完整 unit 配置覆盖该测试文件。
- 安装包使用独立目标目录和本机现存依赖，不能声称干净机器安装验收。输入完整扫描增加大矩阵读入和扫描成本，本轮未做大规模性能基准。
- `BNS-EM-007` 独立校准、`BNS-PV-009` 强制不可变及外部锚定追加存储仍未建立。测试只证明已声明工程边界，不证明原始数据来源、外部生产者身份、生物学有效性或科学授权。
- 数值为整数不等于真实原始计数；旧审核状态 `ROBUST_PASS` 的语义范围没有因此扩大。结构接口和本地收据均不授予独立认证。

当前维护方式见 [工程维护说明](../../../docs/engineering-quality.md)。[机器摘要](summary.json) 记录源码哈希与实际跳过原因；[证据哈希](evidence.sha256.json) 绑定本轮主要产物。未覆盖旧报告与结果包，未发布远端版本。
'''
(HERE / 'REPORT.zh-CN.md').write_text(report, encoding='utf-8')
artifacts = ['REPORT.zh-CN.md', 'summary.json', 'tests.full.log', 'tests.full.xml', 'full-coverage.json',
             'core-verified/coverage.json', 'core-verified/tests.xml', 'de-verified/report.json',
             'de-verified/receipts.json', 'types.final.log', 'ruff.final.log', 'registry.log',
             'bundle-contract.log', 'input.final.log', 'wheel-smoke-final.json']
(HERE / 'evidence.sha256.json').write_text(json.dumps({p: hashlib.sha256((HERE / p).read_bytes()).hexdigest()
                                                    for p in artifacts}, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in summary.items() if k != 'source_sha256'}, indent=2))
