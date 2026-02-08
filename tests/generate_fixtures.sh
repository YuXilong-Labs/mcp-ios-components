#!/usr/bin/env bash
set -euo pipefail

# Generates local fixtures for manual inspection/regression. This is optional and
# depends on having a local Pods repo available.

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PY="$ROOT_DIR/.venv/bin/python"

PODS_DIR=${IOS_PODS_DIR:-/Users/yuxilong/Desktop/code/BaiTuPods}
INCLUDE=${IOS_PODS_INCLUDE:-BTBaseKit}

if [ ! -d "$PODS_DIR" ]; then
  echo "Pods dir not found: $PODS_DIR" >&2
  exit 1
fi

mkdir -p "$ROOT_DIR/tests/fixtures"

# Run via Codex MCP is unnecessary here; we invoke the module directly.
# Note: module import requires the venv (mcp dependency).
OUT_FILE="$ROOT_DIR/tests/fixtures/audit_${INCLUDE//,/__}.json"

IOS_PODS_DIR="$PODS_DIR" IOS_PODS_INCLUDE="$INCLUDE" "$PY" - <<'PY' >"$OUT_FILE"
import os
import importlib

pods_dir = os.environ.get('IOS_PODS_DIR')
include = os.environ.get('IOS_PODS_INCLUDE','')
component = include.split(',')[0].strip() if include else ''

import mcp_server as s
s = importlib.reload(s)

s.PODS_DIR = pods_dir
new_index = s.build_index(pods_dir)
with s.INDEX_LOCK:
    s.INDEX = new_index

print(s.audit_component_api_quality(component_name=component, format='json', limit=50))
PY

echo "Wrote fixture: $OUT_FILE"
