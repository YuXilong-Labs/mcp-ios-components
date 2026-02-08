#!/usr/bin/env bash
set -euo pipefail

# Smoke test: Codex CLI uses MCP server to decide if an existing implementation exists.
# Important: we must sanitize env vars injected by OpenClaw (OPENAI_BASE_URL/CRS_OAI_KEY/etc.),
# otherwise Codex may be forced onto an incompatible proxy.

WORKDIR=${WORKDIR:-/tmp/codex-mcp-test}
# Default to a small allowlist index (faster + avoids context bloat).
MCP_NAME=${MCP_NAME:-ios-components-core5}

mkdir -p "$WORKDIR"
cd "$WORKDIR"
if [ ! -d .git ]; then
  git init -q
fi

PROMPT=$'你现在有一个 MCP 服务器 '"${MCP_NAME}"' 用于查询 iOS 组件库 API。\n\n任务：判断 BTBaseKit 是否已经提供了 UIImage 圆角/圆形裁剪相关的现成功能，避免重复造轮子。\n\n要求：\n1) 必须先调用 get_tool_docs(tool_name="search_component", format="json") 查看工具说明。\n2) 然后至少调用 3 次 search_component，关键词分别用："圆角"、"corner"、"UIImage"，每次都用 format="json"，limit=5。\n3) 如果找到了相关 API：输出一段 JSON（不要额外文本），结构：{found:true, hits:[{component,kind,name,file,line,declaration,comment_preview}]}; hits 来自 search_component 的 results。\n4) 如果没找到：输出 {found:false, reason:"..."}。\n\n注意：不允许读取大量源码；不要调用 read_source。只做检索判断。'

# Unset env vars that break Codex connectivity in this environment.
exec env \
  -u OPENAI_BASE_URL \
  -u OPENAI_API_KEY \
  -u CRS_OAI_KEY \
  -u ANTHROPIC_BASE_URL \
  -u ANTHROPIC_AUTH_TOKEN \
  -u GEMINI_API_KEY \
  -u GEMINI_MODEL \
  -u GOOGLE_GEMINI_BASE_URL \
  codex exec "$PROMPT"
