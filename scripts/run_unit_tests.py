#!/usr/bin/env python3
"""Run the complete local unit suite with visible progress and safe caches."""

from __future__ import annotations

import argparse
import os
import threading
import time
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]


class ProgressHeartbeat:
    """Small pytest plugin whose state is reported while a test is running."""

    def __init__(self) -> None:
        self.completed = 0
        self.current = "collection"
        self.total = 0
        self._lock = threading.Lock()

    def pytest_collection_finish(self, session) -> None:
        with self._lock:
            self.total = len(session.items)
            self.current = "collection complete"

    def pytest_runtest_logstart(self, nodeid: str, location) -> None:
        del location
        with self._lock:
            self.current = nodeid

    def pytest_runtest_logreport(self, report) -> None:
        if report.when == "call":
            with self._lock:
                self.completed += 1

    def snapshot(self) -> tuple[int, int, str]:
        with self._lock:
            return self.completed, self.total, self.current


def _heartbeat_loop(stop: threading.Event, progress: ProgressHeartbeat, interval: float, started: float) -> None:
    while not stop.wait(interval):
        completed, total, current = progress.snapshot()
        elapsed = time.monotonic() - started
        print(
            f"[unit-test-heartbeat] elapsed={elapsed:.0f}s completed={completed}/{total or '?'} current={current}",
            flush=True,
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--heartbeat-seconds", type=float, default=30.0)
    parser.add_argument("--test-path", default="tests/unit", help="Use tests for the complete repository suite")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.heartbeat_seconds <= 0:
        parser.error("--heartbeat-seconds must be positive")

    cache_dir = (REPO_ROOT / ".numba-cache").resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["NUMBA_CACHE_DIR"] = str(cache_dir)
    os.environ.setdefault("PYTHONUNBUFFERED", "1")

    pytest_args = [
        args.test_path,
        "-q",
        "-p",
        "no:cacheprovider",
        "--capture=tee-sys",
        "--tb=short",
        "--durations=50",
    ]
    extra_args = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
    pytest_args.extend(extra_args)

    # Import pytest only after the safe Numba cache is established. Third-party
    # pytest plugins can import Numba before tests/conftest.py is evaluated.
    import pytest

    progress = ProgressHeartbeat()
    stop = threading.Event()
    started = time.monotonic()
    heartbeat = threading.Thread(
        target=_heartbeat_loop,
        args=(stop, progress, args.heartbeat_seconds, started),
        daemon=True,
        name="bionexus-unit-test-heartbeat",
    )
    heartbeat.start()
    print(f"[unit-test-runner] NUMBA_CACHE_DIR={cache_dir}", flush=True)
    print(f"[unit-test-runner] pytest {' '.join(pytest_args)}", flush=True)
    try:
        return int(pytest.main(pytest_args, plugins=[progress]))
    finally:
        stop.set()
        heartbeat.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
