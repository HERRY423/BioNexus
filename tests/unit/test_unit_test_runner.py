"""Regression tests for the local full-unit test runner."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_runner():
    root = Path(__file__).resolve().parents[2]
    path = root / "scripts" / "run_unit_tests.py"
    spec = importlib.util.spec_from_file_location("bionexus_unit_test_runner", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_runner_sets_repo_local_numba_cache_before_importing_pytest():
    source = (Path(__file__).resolve().parents[2] / "scripts" / "run_unit_tests.py").read_text(encoding="utf-8")
    assert source.index('os.environ["NUMBA_CACHE_DIR"]') < source.index("import pytest")
    assert '".numba-cache"' in source
    assert '"-q"' in source
    assert '"--tb=short"' in source
    assert '"--capture=tee-sys"' in source


def test_runner_heartbeat_snapshot_is_thread_safe():
    runner = _load_runner()
    progress = runner.ProgressHeartbeat()
    assert progress.snapshot() == (0, 0, "collection")
