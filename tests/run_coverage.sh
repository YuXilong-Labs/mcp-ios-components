#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PY="$ROOT_DIR/.venv/bin/python"

if [ ! -x "$PY" ]; then
  echo "Missing venv python: $PY" >&2
  exit 1
fi

cd "$ROOT_DIR"

"$PY" -m coverage erase
"$PY" -m coverage run --source=mcp_server,mcp_app -m unittest discover -s tests -p 'test_*.py'
"$PY" -m coverage report -m --fail-under=98
