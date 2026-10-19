#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
# Install the locked build group first; see README.md. Keep the environment
# available for debugging and let actual startup errors fail this script.
"${PYTHON:-.venv/bin/python}" scripts/build.py
dist/WaterCoolerManager --help
"${PYTHON:-.venv/bin/python}" tests/smoke_linux_tray.py --executable dist/WaterCoolerManager
