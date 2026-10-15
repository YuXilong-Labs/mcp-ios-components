#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/.tmp"
fixture="$(mktemp -d "$ROOT/.tmp/macos-env.XXXXXX")"
trap 'rm -rf "$fixture"' EXIT
mkdir -p "$fixture/.venv/bin" "$fixture/zsh"
cat > "$fixture/.env" <<'ENV'
GITLAB_TOKEN=old-file-token
MCP_API_KEY=retained-api-key
ENV
cat > "$fixture/.venv/bin/python" <<'SH'
#!/bin/bash
set -euo pipefail
[[ "$GITLAB_TOKEN" == "$EXPECTED_TOKEN" ]]
[[ "$MCP_API_KEY" == retained-api-key ]]
SH
chmod +x "$fixture/.venv/bin/python"
cat > "$fixture/zsh/.zshrc" <<'SH'
echo 'profile output must not contaminate the token'
export GIT_LAB_TOKEN='host-token-$with-special-chars'
SH

run_case() {
    env -i PATH=/usr/bin:/bin HOME="$fixture" ZDOTDIR="$fixture/zsh" \
        MCP_SERVICE_ROOT="$fixture" MCP_DATA_ROOT="$fixture/data" \
        "$@" /bin/bash "$ROOT/deploy/macos/run-mcp.sh"
}

run_case EXPECTED_TOKEN=process-token GITLAB_TOKEN=process-token GIT_LAB_TOKEN=alias-token
run_case EXPECTED_TOKEN=alias-token GIT_LAB_TOKEN=alias-token
run_case 'EXPECTED_TOKEN=host-token-$with-special-chars'
printf '' > "$fixture/zsh/.zshrc"
run_case EXPECTED_TOKEN=old-file-token
printf 'export GITLAB_TOKEN=shell-canonical\nexport GIT_LAB_TOKEN=shell-alias\n' > "$fixture/zsh/.zshrc"
run_case EXPECTED_TOKEN=shell-canonical
printf 'exit 1\n' > "$fixture/zsh/.zshrc"
run_case EXPECTED_TOKEN=old-file-token
echo 'macOS Token precedence: 6 checks passed'
