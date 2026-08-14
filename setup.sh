#!/usr/bin/env bash
# ==============================================================================
# Bio-Research Plugin: Linux / macOS One-Click Setup Script
# ==============================================================================
set -e

echo "=============================================================================="
echo " 🧬 Bio-Research Plugin: Linux / macOS One-Click Setup"
echo "=============================================================================="

# Check Python command
if command -v python3 &>/dev/null; then
    PYTHON_BIN=python3
elif command -v python &>/dev/null; then
    PYTHON_BIN=python
else
    echo "[ERROR] Python 3.10+ is required but not found in PATH." >&2
    exit 1
fi

# Create virtual environment if not present
if [ ! -d ".venv" ]; then
    echo "[INFO] Creating Python virtual environment in .venv ..."
    $PYTHON_BIN -m venv .venv
fi

echo "[INFO] Activating virtual environment ..."
source .venv/bin/activate

python scripts/setup_env.py "$@"

echo ""
echo "[DONE] Setup finished. Activate anytime via: source .venv/bin/activate"
