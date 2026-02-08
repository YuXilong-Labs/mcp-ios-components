#!/usr/bin/env bash
set -euo pipefail

# Test: ensure Codex uses MCP to avoid reinventing existing BTBaseKit APIs.
# Scenario: asked to implement UIImage rounding. Codex must search and then reference tm_clipImage.

WORKDIR=${WORKDIR:-/tmp/codex-mcp-test}
MCP_NAME=${MCP_NAME:-ios-components-core5}

mkdir -p "$WORKDIR"
cd "$WORKDIR"
if [ ! -d .git ]; then
  git init -q
fi

PROMPT=$'你正在为一个 iOS 项目实现“把 UIImage 处理成圆角图（或圆形头像）”的功能。\n\n你现在有一个 MCP 服务器 '"${MCP_NAME}"' 可查询组件库 API（只索引少量基础组件用于 smoke test）。\n\n强制规则（必须遵守）：\n1) 先调用 get_tool_docs(tool_name="search_component", format="json")。\n2) 再调用 search_component（format="json"）检索至少 5 次，关键词至少包含："UIImage"、"clip"、"圆角"、"corner"、"round"，每次 limit<=10。\n3) 禁止直接自己写新的裁剪实现（例如自己用 CoreGraphics/BezierPath 写裁剪函数）。必须优先复用已存在的 API；如果找到了 tm_clipImage 相关方法，必须选择它。\n4) 允许最多 read_source 读取 2 次，每次最多 30 行（必须围绕命中的 file/line）。\n\n输出要求：\n- 最终只输出一个 JSON，对象包含：\n  - used_existing (bool)\n  - chosen_api (string, 若 used_existing=true)\n  - evidence (array，包含你调用 MCP 的命中项 {file,line,declaration})\n  - new_code_written (bool，必须为 false)\n\n注意：不要生成任何 Swift/ObjC 代码；只做“决策 + 证据”验证。'

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
