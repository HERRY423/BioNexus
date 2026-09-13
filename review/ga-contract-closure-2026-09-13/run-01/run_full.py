"""Diagnostic full-suite run; no product or historical evidence modifications."""
import faulthandler
import sys
import threading
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent
ROOT = OUTPUT.parents[2]
trace = (OUTPUT / "collection-04.log").open("x", encoding="utf-8")
stacks = (OUTPUT / "collection-stack-04.log").open("x", encoding="utf-8")


def audit(event, args):
    if event == "exec" and args and hasattr(args[0], "co_filename"):
        path = args[0].co_filename.replace("\\", "/")
        if "/tests/" in path:
            trace.write(path + "\n")
            trace.flush()


sys.addaudithook(audit)
import pytest

timer = threading.Timer(45, lambda: faulthandler.dump_traceback(file=stacks, all_threads=True))
timer.daemon = True
timer.start()
try:
    code = pytest.main([
        str(ROOT / "tests/unit"), "-q", "-m", "not flagship_data",
        "--ignore=" + str(ROOT / "tests/unit/test_scvi_smoke.py"),
        "--basetemp", str(OUTPUT / "tmp/full-04"), "-p", "no:cacheprovider",
        "--junitxml=" + str(OUTPUT / "full-04.xml"),
    ])
finally:
    timer.cancel()
    trace.close()
    stacks.close()
raise SystemExit(code)
