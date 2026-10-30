#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo '[Codex] Setting up workspace'
if [ -f requirements.txt ] || [ -f pyproject.toml ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  if [ -f requirements.txt ]; then .venv/bin/python -m pip install -r requirements.txt; fi
  if [ -f pyproject.toml ]; then .venv/bin/python -m pip install -e .; fi
fi
if [ -f package.json ]; then
  if [ -f package-lock.json ]; then npm ci; else npm install; fi
fi
echo '[Codex] Setup complete'
