#!/bin/bash
set -euo pipefail

SERVICE_ROOT="${MCP_SERVICE_ROOT:-/Users/jenkins/services/mcp-ios-components}"
DATA_ROOT="${MCP_DATA_ROOT:-/Users/jenkins/data/mcp-ios-components}"
ENV_FILE="$SERVICE_ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "[mcp-ios] missing runtime environment: $ENV_FILE" >&2
    exit 1
fi

set -a
source "$ENV_FILE"
set +a

if [[ -z "${GITLAB_URL:-}" && -n "${GIT_LAB_HOST:-}" ]]; then
    if [[ "$GIT_LAB_HOST" == http://* || "$GIT_LAB_HOST" == https://* ]]; then
        export GITLAB_URL="$GIT_LAB_HOST"
    else
        export GITLAB_URL="https://$GIT_LAB_HOST"
    fi
fi
if [[ -z "${GITLAB_TOKEN:-}" && -n "${GIT_LAB_TOKEN:-}" ]]; then
    export GITLAB_TOKEN="$GIT_LAB_TOKEN"
fi

export GIT_ASKPASS="$SERVICE_ROOT/deploy/macos/git-askpass.sh"
export GIT_TERMINAL_PROMPT=0
export GIT_CONFIG_COUNT=1
export GIT_CONFIG_KEY_0=credential.helper
export GIT_CONFIG_VALUE_0=
export IOS_PODS_APP_BASE_DIR="$SERVICE_ROOT"
export IOS_PODS_CONFIG="$SERVICE_ROOT/components.yaml"
export IOS_PODS_CACHE_DIR="$DATA_ROOT/cache"
export NO_PROXY="127.0.0.1,localhost${NO_PROXY:+,$NO_PROXY}"
export no_proxy="$NO_PROXY"

mkdir -p "$DATA_ROOT/pods" "$DATA_ROOT/cache"

exec "$SERVICE_ROOT/.venv/bin/python" "$SERVICE_ROOT/mcp_server.py" \
    --http \
    --host "${MCP_HOST:-127.0.0.1}" \
    --port "${MCP_PORT:-8900}" \
    --watch "${MCP_WATCH_INTERVAL_S:-60}" \
    "$DATA_ROOT/pods"
