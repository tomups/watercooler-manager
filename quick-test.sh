#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
exec "${PYTHON:-.venv/bin/python}" scripts/check_linux.py
