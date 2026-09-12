"""One-time, source-preserving registration extraction; keep original order."""
import ast
import re
from pathlib import Path

root = Path(__file__).resolve().parents[3]
path = root / 'src/bionexus/cli.py'
source = path.read_text(encoding='utf-8')
start = source.index('    # 1. create-plugin')
end = source.index('    args = parser.parse_args', start)
section = source[start:end]
headers = list(re.finditer(r'^    # \d+(?:\.\d+)?[a-z]?\.? ([^\n]+)', section, re.M))
groups = {
 'scaffold': 'create-plugin',
 'diagnostics': 'doctor backend-identity list-skills registry',
 'de': 'audit audit-de',
 'validation': 'preflight verify bench prevent eval eval-audit verify-artifacts conformance',
 'standards': 'interop standards capability abi certification',
 'claims': 'failures ledger route audit-claims parse-claim warrant-claim rule',
 'ivn': 'ivn debt',
 'execution': 'run cluster bigdata scfm',
 'experimental': 'closed-loop causal remediate',
 'security': 'security guard cache',
 'lab': 'lims instrument airgap compliance nextflow ga4gh',
}
domain = {label: module for module, labels in groups.items() for label in labels.split()}
dispatch = ast.parse('def remaining():\n' + source[end:source.index('\n\nif __name__', end)])
needed = {n.id for n in ast.walk(dispatch) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
calls = []
additions = {}
for i, match in enumerate(headers):
 label = match.group(1).split()[0]
 module = domain[label]
 block = section[match.start():headers[i+1].start() if i+1 < len(headers) else len(section)].rstrip()
 tree = ast.parse('def register(subparsers):\n' + block)
 assigned = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
 returns = sorted(assigned & needed)
 assert len(returns) <= 1, (label, returns)
 name = 'register_' + label.replace('-', '_') + '_arguments'
 result_type = 'argparse.ArgumentParser' if returns else 'None'
 function = f'\n\ndef {name}(subparsers: argparse._SubParsersAction) -> {result_type}:\n' + block + '\n'
 if returns:
  function += f'    return {returns[0]}\n'
 additions[module] = additions.get(module, '') + function
 prefix = f'{returns[0]} = ' if returns else ''
 calls.append(f'    {prefix}{module}.{name}(subparsers)')
for module, addition in additions.items():
 target = root / f'src/bionexus/commands/{module}.py'
 text = target.read_text(encoding='utf-8')
 if 'Path(' in addition and 'from pathlib import Path' not in text:
  text = text.replace('import argparse\n', 'import argparse\nfrom pathlib import Path\n')
 target.write_text(text.rstrip() + '\n' + addition, encoding='utf-8')
source = source[:start] + '\n'.join(calls) + '\n\n' + source[end:]
source = source.replace('from bionexus.commands.claims import', 'from bionexus.commands import (' + ', '.join(groups) + ')\n\nfrom bionexus.commands.claims import', 1)
path.write_text(source, encoding='utf-8')
print(f'Extracted {len(headers)} registration blocks; CLI now {len(source.splitlines())} lines')
