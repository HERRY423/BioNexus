"""Lab-grade offline mode (airgapped deployment profile).

Deployment gate for HPC / air-gapped laboratory environments: when
``BIONEXUS_OFFLINE=1`` is set, every network egress is forced to
``OFFLINE_STRICT`` (zero external HTTP, zero hosted MCP endpoints) regardless
of any other configuration, and the core workflow — doctor, replay-provider
evals, local MCP tools, three firewall gates, scale benchmark — must run
without touching the network.

The readiness report (:func:`offline_readiness`) is computed without making
any network request. It verifies deployment-relevant facts:

1. the offline flag is recognized;
2. the egress guard singleton is effectively OFFLINE_STRICT;
3. the replay eval provider is importable (evals run without provider APIs);
4. the local MCP server module is importable (zero-key database tools);
5. no hosted HTTP endpoint is reachable-by-policy (they are refused, never
   attempted).

`bionexus offline-check` (and `bionexus doctor --offline`) runs this report
and exits nonzero when the deployment is not offline-ready — the container
build self-test and the Slurm reference profiles use it as a gate.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

__all__ = [
    "OFFLINE_ENV_VAR",
    "OfflineModeError",
    "is_offline_enforced",
    "offline_readiness",
    "assert_offline_ready",
]

OFFLINE_ENV_VAR = "BIONEXUS_OFFLINE"
_TRUTHY = {"1", "true", "yes", "on"}


class OfflineModeError(RuntimeError):
    """Raised when an offline deployment gate fails."""


def is_offline_enforced() -> bool:
    """True when ``BIONEXUS_OFFLINE`` is set to a truthy value."""
    return os.environ.get(OFFLINE_ENV_VAR, "").strip().lower() in _TRUTHY


def _check_replay_provider() -> str:
    try:
        from evals.host_eval import RealHostEvaluator

        adapter = RealHostEvaluator.get_adapter("replay")
        return f"ok ({type(adapter).__name__})"
    except Exception as exc:  # pragma: no cover - environment dependent
        return f"unavailable ({exc})"


def _check_local_mcp_server() -> str:
    try:
        import importlib.util
        from pathlib import Path

        server = Path(__file__).resolve().parents[2] / "scripts" / "local_mcp_server.py"
        if server.is_file():
            spec = importlib.util.spec_from_file_location("bionexus_local_mcp_probe", server)
            loaded = spec is not None and spec.loader is not None
            return "ok (scripts/local_mcp_server.py present)" if loaded else "unreadable"
        # Installed layouts may not ship scripts/: the fastmcp dependency is
        # the actual requirement for zero-key local database tools.
        import mcp  # noqa: F401

        return "ok (mcp SDK importable; server scripts not packaged)"
    except Exception as exc:  # pragma: no cover - environment dependent
        return f"unavailable ({exc})"


def offline_readiness() -> Dict[str, Any]:
    """Compute the offline deployment readiness report (no network requests).

    Evaluates a fresh guard (environment-authoritative) rather than the
    process singleton, so the gate reflects the deployment environment
    exactly and test/runtime state cannot bleed across evaluations.
    """
    from bionexus.egress_guard import DataGovernanceGuard, EgressMode

    checks: List[Dict[str, str]] = []
    enforced = is_offline_enforced()

    guard_mode = DataGovernanceGuard().mode
    if enforced and guard_mode is not EgressMode.OFFLINE_STRICT:
        # Defense in depth: a fresh guard must honor the flag; if it somehow
        # does not, the gate reports the failure instead of papering over it.
        checks.append(
            {
                "name": "offline_flag_enforcement",
                "ok": False,
                "detail": f"{OFFLINE_ENV_VAR}=1 is set but a fresh egress guard ignored it",
            }
        )
    checks.append(
        {
            "name": "egress_mode_offline_strict",
            "ok": guard_mode is EgressMode.OFFLINE_STRICT,
            "detail": (
                f"egress guard mode is {guard_mode.value}"
                + (f" (forced by {OFFLINE_ENV_VAR}=1)" if enforced else "")
            ),
        }
    )
    replay = _check_replay_provider()
    checks.append(
        {"name": "replay_eval_provider", "ok": replay.startswith("ok"), "detail": replay}
    )
    local_mcp = _check_local_mcp_server()
    checks.append({"name": "local_mcp_tools", "ok": local_mcp.startswith("ok"), "detail": local_mcp})

    blocked = {
        "name": "hosted_endpoints_refused",
        "ok": guard_mode is EgressMode.OFFLINE_STRICT,
        "detail": "every hosted HTTP/MCP endpoint is refused by policy before any "
        "connection attempt while OFFLINE_STRICT is active",
    }
    checks.append(blocked)

    ready = all(check["ok"] for check in checks)
    return {
        "schema_version": "bionexus.offline-readiness.v1",
        "offline_enforced": enforced,
        "offline_ready": ready,
        "egress_mode": guard_mode.value,
        "checks": checks,
        "deployment_note": (
            "Offline mode is a deployment profile for air-gapped labs and HPC "
            "login/compute nodes: core BioNexus workflows run with zero egress. "
            "It disables hosted MCP endpoints and any provider-backed eval; it "
            "never weakens a refusal, a policy gate, or an evidence ceiling."
        ),
    }


def assert_offline_ready() -> Dict[str, Any]:
    """Deployment gate: raise :class:`OfflineModeError` when not offline-ready."""
    report = offline_readiness()
    if not report["offline_ready"]:
        failed = [check["name"] for check in report["checks"] if not check["ok"]]
        raise OfflineModeError("offline deployment gate failed: " + ", ".join(failed))
    return report
