#!/usr/bin/env bash
# Benchmark launcher — activates venv, sets PYTHONPATH, forwards args to run.py

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

VENV_ACTIVATE="backend/venv/bin/activate"
if [ -f "$VENV_ACTIVATE" ]; then
    # shellcheck disable=SC1090
    source "$VENV_ACTIVATE"
fi

export PYTHONPATH=backend
python benchmark/run.py "$@"
