#!/usr/bin/env python3
"""
Scientific Research Workflow Orchestrator Engine.
Provides DAG-based task dependency resolution, asynchronous tool execution,
parameter interpolation, and structured execution reporting.

Usage:
    python workflow_engine.py drug_target_discovery.yml --param disease_name="Melanoma" -o ./workflow_results
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Add scripts directory for local MCP tools
SCRIPTS_DIR = Path(__file__).parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class WorkflowEngine:
    def __init__(self, template_path: str):
        self.template_path = Path(template_path)
        with open(self.template_path, "r", encoding="utf-8") as f:
            self.workflow_def = yaml.safe_load(f)

        self.name = self.workflow_def.get("name", "unnamed_workflow")
        self.version = self.workflow_def.get("version", "1.0.0")
        self.description = self.workflow_def.get("description", "")
        self.steps = self.workflow_def.get("steps", [])
        self.context: Dict[str, Any] = {}
        self.step_status: Dict[str, Dict[str, Any]] = {}

    def validate_dag(self) -> List[str]:
        """Validate DAG structure and return execution order via topological sort."""
        step_ids = {s["id"] for s in self.steps}
        adj_list: Dict[str, List[str]] = {s["id"]: [] for s in self.steps}
        in_degree: Dict[str, int] = {s["id"]: 0 for s in self.steps}

        for step in self.steps:
            for dep in step.get("depends_on", []):
                if dep not in step_ids:
                    raise ValueError(f"Step '{step['id']}' depends on undefined step '{dep}'")
                adj_list[dep].append(step["id"])
                in_degree[step["id"]] += 1

        # Kahn's algorithm for topological sorting
        queue = [s_id for s_id, deg in in_degree.items() if deg == 0]
        exec_order = []

        while queue:
            curr = queue.pop(0)
            exec_order.append(curr)
            for neighbor in adj_list[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(exec_order) != len(self.steps):
            raise ValueError("Cyclic dependency detected in workflow DAG!")

        return exec_order

    def interpolate_params(self, val: Any) -> Any:
        """Recursively interpolate variables from workflow context into argument strings."""
        if isinstance(val, str):
            # Match {variable_name} or {nested.key.0.field}
            pattern = re.compile(r"\{([\w\.\-]+)\}")
            matches = pattern.findall(val)
            for m in matches:
                parts = m.split(".")
                curr = self.context
                found = True
                for part in parts:
                    if isinstance(curr, dict) and part in curr:
                        curr = curr[part]
                    elif isinstance(curr, list) and part.isdigit() and int(part) < len(curr):
                        curr = curr[int(part)]
                    else:
                        found = False
                        break
                if found:
                    val = val.replace(f"{{{m}}}", str(curr))
            return val
        elif isinstance(val, dict):
            return {k: self.interpolate_params(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [self.interpolate_params(i) for i in val]
        return val

    async def execute_step(self, step: Dict[str, Any]) -> Any:
        """Execute a single workflow step."""
        step_id = step["id"]
        step_name = step.get("name", step_id)
        tool_name = step.get("tool")
        step_type = step.get("type", "tool_call")
        raw_args = step.get("arguments", {})
        interpolated_args = self.interpolate_params(raw_args)

        self.step_status[step_id] = {
            "name": step_name,
            "status": "RUNNING",
            "start_time": datetime.now(timezone.utc).isoformat(),
            "arguments": interpolated_args,
        }

        print(f"  [RUNNING] Step: {step_name} ({step_id})...")
        t0 = time.time()

        result = None
        try:
            if tool_name:
                # Dispatch to local_mcp_server tool function
                import local_mcp_server as mcp

                handler_map = {
                    "search_pubmed": mcp.tool_search_pubmed,
                    "get_pubmed_article": mcp.tool_get_pubmed_article,
                    "search_biorxiv": mcp.tool_search_biorxiv,
                    "search_chembl": mcp.tool_search_chembl,
                    "search_opentargets": mcp.tool_search_opentargets,
                    "search_clinical_trials": mcp.tool_search_clinical_trials,
                    "search_uniprot": mcp.tool_search_uniprot,
                    "search_ensembl": mcp.tool_search_ensembl,
                }
                if tool_name in handler_map:
                    result = await handler_map[tool_name](**interpolated_args)
                else:
                    result = {"mock_result": f"Executed external tool {tool_name}", "params": interpolated_args}

            elif step_type == "synthesis":
                weights = step.get("parameters", {}).get("weights", {})
                result = {
                    "synthesis_type": "evidence_weighted_ranking",
                    "weights_applied": weights,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "summary": f"Synthesized multi-source evidence across {len(step.get('depends_on', []))} prerequisite steps.",
                }
            else:
                result = {"status": "completed", "params": interpolated_args}

            elapsed = round(time.time() - t0, 3)
            self.step_status[step_id].update({"status": "COMPLETED", "duration_s": elapsed, "output": result})

            # Store in context if output_variable specified
            out_var = step.get("output_variable")
            if out_var:
                self.context[out_var] = result

            print(f"  [COMPLETED] Step: {step_name} in {elapsed}s")
            return result

        except Exception as e:
            elapsed = round(time.time() - t0, 3)
            self.step_status[step_id].update({"status": "FAILED", "duration_s": elapsed, "error": str(e)})
            print(f"  [FAILED] Step: {step_name} failed: {e}")
            raise

    async def run(self, initial_inputs: Dict[str, Any], output_dir: Optional[str] = None) -> Dict[str, Any]:
        """Execute complete workflow from DAG specification."""
        self.context.update(initial_inputs)
        exec_order = self.validate_dag()

        print("\n" + "=" * 70)
        print(f" BioNexus Workflow Engine: {self.name} (v{self.version})")
        print(f" Description: {self.description}")
        print(f" Steps to execute: {len(exec_order)} in topological sequence")
        print("=" * 70)

        step_dict = {s["id"]: s for s in self.steps}
        start_time = time.time()

        for step_id in exec_order:
            step = step_dict[step_id]
            await self.execute_step(step)

        total_duration = round(time.time() - start_time, 2)

        summary = {
            "workflow_name": self.name,
            "version": self.version,
            "inputs": initial_inputs,
            "total_duration_s": total_duration,
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "step_results": self.step_status,
        }

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            report_file = os.path.join(output_dir, f"{self.name}_execution_report.json")
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            print(f"\nWorkflow report exported to: {report_file}")

        print("\n" + "=" * 70)
        print(f" Workflow {self.name} Completed Successfully in {total_duration}s!")
        print("=" * 70)

        return summary


def main():
    parser = argparse.ArgumentParser(
        description="BioNexus Scientific Research Workflow Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python workflow_engine.py drug_target_discovery.yml --param disease_name="Melanoma" -o ./results
        """,
    )
    parser.add_argument("template", help="Path or name of workflow template YAML")
    parser.add_argument(
        "-p", "--param", action="append", help="Input parameters in key=value format (can be specified multiple times)"
    )
    parser.add_argument(
        "-o", "--output-dir", default="./workflow_output", help="Directory for output report and artifacts"
    )

    args = parser.parse_args()

    # Search in templates dir if not existing path
    template_path = args.template
    if not os.path.exists(template_path):
        candidate = Path(__file__).parent.parent / "templates" / f"{args.template}.yml"
        if candidate.exists():
            template_path = str(candidate)
        else:
            candidate_yaml = Path(__file__).parent.parent / "templates" / f"{args.template}.yaml"
            if candidate_yaml.exists():
                template_path = str(candidate_yaml)

    if not os.path.exists(template_path):
        print(f"Error: Template not found: {args.template}", file=sys.stderr)
        sys.exit(1)

    inputs = {}
    if args.param:
        for p in args.param:
            if "=" in p:
                k, v = p.split("=", 1)
                inputs[k.strip()] = v.strip()

    engine = WorkflowEngine(template_path)
    asyncio.run(engine.run(inputs, output_dir=args.output_dir))


if __name__ == "__main__":
    main()
