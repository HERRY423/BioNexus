"""One-time, AST-bounded extraction; the frozen input is retained alongside it."""
import ast
from pathlib import Path

root = Path(__file__).resolve().parents[3]
source_path = root / "src/bionexus/cli.py"
source = source_path.read_text(encoding="utf-8")
lines = source.splitlines(keepends=True)
tree = ast.parse(source)
nodes = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
imports = "\n".join(ast.get_source_segment(source, n) for n in tree.body
                    if isinstance(n, (ast.Import, ast.ImportFrom)))
groups = {
    "scaffold": ["_to_snake_case", "_to_kebab_case", "handle_create_plugin"],
    "diagnostics": ["handle_backend_identity", "handle_doctor", "handle_list_skills", "handle_registry"],
    "de": ["handle_audit_de", "handle_audit_de_summary", "handle_audit_de_verify", "handle_audit"],
    "validation": ["handle_conformance", "handle_preflight", "handle_verify", "handle_bench", "handle_prevent", "handle_eval_audit", "handle_eval"],
    "standards": ["handle_interop", "handle_standards", "handle_capability", "handle_abi", "handle_certification"],
    "claims": ["handle_failures", "handle_ledger", "handle_route", "handle_audit_claims", "handle_parse_claim", "handle_warrant_claim", "handle_rule"],
    "execution": ["handle_run", "handle_cluster", "handle_bigdata", "handle_scfm"],
    "experimental": ["handle_closed_loop", "handle_causal", "handle_remediate"],
    "security": ["handle_security", "handle_guard", "handle_cache"],
    "ivn": ["handle_debt", "handle_ivn"],
    "lab": ["_emit_cli_payload", "handle_lims", "handle_ga4gh", "handle_instrument", "handle_airgap", "handle_compliance", "handle_nextflow"],
}
assigned = [n for group in groups.values() for n in group]
assert len(assigned) == len(set(assigned))
assert set(nodes) - set(assigned) == {"_configure_console_streams", "main"}
destination = root / "src/bionexus/commands"
destination.mkdir(exist_ok=False)
(destination / "__init__.py").write_text('"""Command handlers grouped by responsibility; public entry remains bionexus.cli."""\n', encoding="utf-8")
exports = []
for group, names in groups.items():
    parts = [f'"""{group.title()} command handlers, extracted without changing command semantics."""\n', imports, "\n"]
    if group == "scaffold":
        for node in tree.body:
            if isinstance(node, ast.Assign):
                parts.append(ast.get_source_segment(source, node))
                names_to_export = [t.id for t in node.targets if isinstance(t, ast.Name)]
                exports.extend(f"from bionexus.commands.scaffold import {n} as {n}" for n in names_to_export)
    for name in names:
        segment = "".join(lines[nodes[name].lineno - 1:nodes[name].end_lineno])
        # Only this handler uses its physical module location. Template strings
        # in scaffold describe generated files and must retain their own paths.
        if name == "handle_bench":
            segment = segment.replace("Path(__file__).resolve().parents[2]", "Path(__file__).resolve().parents[3]")
        parts.append(segment)
        exports.append(f"from bionexus.commands.{group} import {name} as {name}")
    (destination / f"{group}.py").write_text("\n\n".join(parts) + "\n", encoding="utf-8")
doc = ast.get_source_segment(source, tree.body[0])
console = ast.get_source_segment(source, nodes["_configure_console_streams"])
main = ast.get_source_segment(source, nodes["main"])
source_path.write_text(doc + "\n\n" + imports + "\n\n# Compatibility exports: existing handler imports remain valid.\n"
                       + "\n".join(exports) + "\n\n" + console + "\n\n" + main
                       + '\n\nif __name__ == "__main__":\n    sys.exit(main())\n', encoding="utf-8")
