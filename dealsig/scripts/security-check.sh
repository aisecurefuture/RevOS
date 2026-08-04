#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
PIP_AUDIT_CACHE_DIR="${PIP_AUDIT_CACHE_DIR:-/tmp/dealsig-pip-audit-cache}"
mkdir -p "$PIP_AUDIT_CACHE_DIR"

echo "[1/4] Static lint and security rules"
"$PYTHON_BIN" -m ruff check app tests

echo "[2/4] Python security scan"
"$PYTHON_BIN" -m bandit -q -r app -c pyproject.toml

echo "[3/4] Dependency vulnerability audit"
"$PYTHON_BIN" -m pip_audit -r requirements.txt --progress-spinner=off --cache-dir "$PIP_AUDIT_CACHE_DIR"

echo "[4/4] Security and application tests"
"$PYTHON_BIN" -m pytest -q
