#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
echo 'Codex environment diagnostics'
git --version
if command -v python3 >/dev/null; then python3 --version; fi
if command -v node >/dev/null; then node --version; fi
if command -v npm >/dev/null; then npm --version; fi
test -f AGENTS.md
test -d projects
echo 'PASS: workspace configuration is present'
