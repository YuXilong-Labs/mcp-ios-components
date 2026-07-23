#!/bin/bash
set -euo pipefail

SOURCE_ROOT="${1:-${GITHUB_WORKSPACE:-$(pwd)}}"
DEPLOY_ROOT="${MCP_DEPLOY_ROOT:-/Users/jenkins/services/mcp-ios-components}"
DATA_ROOT="${MCP_DATA_ROOT:-/Users/jenkins/data/mcp-ios-components}"
LOG_ROOT="${MCP_LOG_ROOT:-/Users/jenkins/Library/Logs/mcp-ios-components}"
LABEL="${MCP_LAUNCHD_LABEL:-com.baitu.mcp-ios-components}"
PORT="${MCP_PORT:-8900}"
PYTHON_BIN="${PYTHON_BIN:-/opt/homebrew/bin/python3}"
RUN_TESTS="${RUN_TESTS:-1}"
SYNC_COMPONENTS="${SYNC_COMPONENTS:-1}"

if [[ ! -x "$PYTHON_BIN" ]]; then
    PYTHON_BIN="$(command -v python3)"
fi

echo "[deploy] source=$SOURCE_ROOT target=$DEPLOY_ROOT data=$DATA_ROOT"

if [[ "$RUN_TESTS" == "1" ]]; then
    TEST_VENV="${RUNNER_TEMP:-/tmp}/mcp-ios-components-deploy-venv"
    rm -rf "$TEST_VENV"
    "$PYTHON_BIN" -m venv "$TEST_VENV"
    "$TEST_VENV/bin/pip" install -q -r "$SOURCE_ROOT/requirements.txt" pytest
    PYTHONPATH="$SOURCE_ROOT" "$TEST_VENV/bin/python" -m pytest "$SOURCE_ROOT/tests" -q
fi

mkdir -p "$DEPLOY_ROOT" "$DATA_ROOT/pods" "$DATA_ROOT/cache" "$LOG_ROOT"

rsync -a --delete \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude '.env' \
    --exclude 'components.yaml' \
    --exclude '.cache/' \
    --exclude '.pytest_cache/' \
    --exclude '__pycache__/' \
    "$SOURCE_ROOT/" "$DEPLOY_ROOT/"

if [[ ! -f "$DEPLOY_ROOT/.env" ]]; then
    echo "[deploy] missing persistent environment: $DEPLOY_ROOT/.env" >&2
    exit 1
fi
chmod 600 "$DEPLOY_ROOT/.env"
install -m 600 "$DEPLOY_ROOT/deploy/components.production.yaml" "$DEPLOY_ROOT/components.yaml"
chmod 700 "$DEPLOY_ROOT/deploy/macos/run-mcp.sh" "$DEPLOY_ROOT/deploy/macos/git-askpass.sh"

if [[ ! -x "$DEPLOY_ROOT/.venv/bin/python" ]]; then
    "$PYTHON_BIN" -m venv "$DEPLOY_ROOT/.venv"
fi
"$DEPLOY_ROOT/.venv/bin/pip" install -q -r "$DEPLOY_ROOT/requirements.txt"

PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
"$PYTHON_BIN" "$DEPLOY_ROOT/deploy/macos/install_launchd.py" \
    --label "$LABEL" \
    --service-root "$DEPLOY_ROOT" \
    --data-root "$DATA_ROOT" \
    --log-root "$LOG_ROOT" \
    --output "$PLIST"

DOMAIN="gui/$(id -u)"
launchctl bootout "$DOMAIN/$LABEL" >/dev/null 2>&1 || true
sleep 2

BOOTSTRAPPED=0
for ATTEMPT in $(seq 1 10); do
    if launchctl bootstrap "$DOMAIN" "$PLIST"; then
        BOOTSTRAPPED=1
        break
    fi
    echo "[deploy] launchd bootstrap is still settling, retry $ATTEMPT/10" >&2
    sleep 2
done
if [[ "$BOOTSTRAPPED" != "1" ]]; then
    echo "[deploy] launchd bootstrap failed after retries" >&2
    exit 1
fi

launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"

HEALTH_URL="http://127.0.0.1:$PORT/webhook/health"
for _ in $(seq 1 90); do
    if curl --noproxy '*' -fsS "$HEALTH_URL" >/dev/null; then
        break
    fi
    sleep 1
done
curl --noproxy '*' -fsS "$HEALTH_URL"
printf '\n'

CLIENT=("$DEPLOY_ROOT/.venv/bin/python" "$DEPLOY_ROOT/scripts/mcp_http_client.py" --url "http://127.0.0.1:$PORT/mcp")
if [[ "$SYNC_COMPONENTS" == "1" ]]; then
    "${CLIENT[@]}" \
        --tool sync_from_config \
        --arguments "{\"config_path\":\"$DEPLOY_ROOT/components.yaml\"}" \
        --timeout 1200 \
        --fail-sync-errors
fi

"${CLIENT[@]}" --tool list_components --contains BTBaseKit --timeout 120
"${CLIENT[@]}" --tool search_component --arguments '{"keyword":"BTBaseKit","limit":3}' --contains BTBaseKit --timeout 120
"${CLIENT[@]}" --tool watch_status --contains '定时检查' --timeout 120
curl --noproxy '*' -fsS "$HEALTH_URL"
printf '\n[deploy] MCP service deployment verified\n'
