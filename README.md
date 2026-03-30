# MCP iOS Components Server

[![Coverage](https://img.shields.io/badge/coverage-98%25-brightgreen)](tests/run_coverage.sh)

[English](#english) | 中文

iOS CocoaPods 组件库 MCP Server，帮助 AI 编码助手发现和复用已有代码，避免重复造轮子。

## 特性

- **自动组件发现** — 扫描 podspec 文件，可配置过滤标记
- **智能 API 提取** — ObjC（`@interface`、`@protocol`、`@property`（含 block 类型）、方法、内联函数）+ Swift（`public/open` 声明）
- **注释提取** — 支持 `///` 和 `/** */` 文档注释，可搜索
- **跨组件使用搜索** — 查找组件在其他组件中的 import 和使用方式
- **SHA256 缓存** — 源文件变更时自动重建索引
- **HTTP 模式 + API Key 鉴权** — 部署到云端，团队共享
- **按行读取源码** — 只读需要的行，节省 token
- **按类聚合视图** — 一览类定义、属性、公开/内部方法

## 架构与目录（轻量分层）

```text
mcp_server.py                 # 兼容入口（CLI + import 兼容）
mcp_app/
  bootstrap.py               # 组装层：MCP tools、main、全局运行态
  config.py                  # 配置与 access_control 加载
  models.py                  # 常量与状态模型
  access_control.py          # 访问控制导出
  state.py                   # AppState 导出
  indexing/                  # 发现、解析、索引构建
  services/                  # 查询/源码读取/同步/更新服务
  integrations/              # git、gitlab、apikey 集成
  transport/                 # 预留传输层拆分
```

说明：
- 对外接口保持不变：`python mcp_server.py ...` 与 MCP 工具签名兼容。
- `mcp_server.py` 仅负责兼容入口，核心逻辑在 `mcp_app/` 分层维护。

## 快速开始

```bash
# 安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install mcp

# 运行（stdio 模式，本地 Claude Code 使用）
python mcp_server.py /path/to/your/pods

# 或通过环境变量指定
IOS_PODS_DIR=/path/to/your/pods python mcp_server.py
```

## 配置 Claude Code

```bash
claude mcp add -s user ios-components -- \
  /path/to/.venv/bin/python /path/to/mcp_server.py /path/to/your/pods
```

验证连接：
```bash
claude mcp list
# ios-components: ... ✓ Connected
```

## 强化组件复用（推荐）

### 方式一：项目规则（AGENTS.md）

将 `AGENTS.md.template` 复制到你的 iOS 项目根目录：

```bash
cp /path/to/mcp-ios-components/AGENTS.md.template /path/to/your/project/AGENTS.md
```

然后编辑 `AGENTS.md`，填写项目特定的组件表。Claude Code 会自动读取并遵循规则，在实现功能前先检查组件库。

### 方式二：生产级 Skill 套件（推荐与 MCP 配套使用）

仓库内置 `skills/` 目录，提供四个可直接上传到 Claude 的技能：

- `ios-component-implementation`：实现需求时强制“先检索再编码”
- `ios-component-selection`：需求评审阶段组件选型
- `ios-component-migration`：把已有重复实现迁移到基础组件
- `ios-component-review`：PR 阶段拦截重复造轮子

建议：先启用 implementation + review，再按需启用 selection/migration。

详见：`skills/README.md`

技能包已按“复用优先 + 证据输出”方式组织，并包含：
- 4 个 `SKILL.md`（触发边界、流程、失败恢复、输出契约）
- `references/`（词表、模板、判定规则，按需加载）
- `agents/openai.yaml`（Claude/Codex UI 元数据兼容）
- `skills/evals/*`（触发、功能与流程合规评测）

### Skills 一键安装（Claude / Codex）

仓库内置安装脚本，可将 `skills/` 下 4 个技能批量安装到本地技能目录（支持覆盖确认、版本提示、安装校验）：

```bash
# 同时安装到 Codex + Claude（默认 all）
python3 scripts/install_skills.py

# 仅安装到 Codex
python3 scripts/install_skills.py --target codex

# 仅安装到 Claude（目录自动探测失败时可显式指定）
python3 scripts/install_skills.py --target claude --claude-dir ~/.claude/skills
```

更多参数见：`python3 scripts/install_skills.py --help`

## 工具列表

| 工具 | 说明 |
|------|------|
| `list_components` | 列出所有已索引组件及统计信息 |
| `search_component(keyword, kind?, format?, limit?)` | 搜索符号、声明、注释（模糊匹配；支持 `format=json` 便于 agent 解析） |
| `audit_component_api_quality(component_name?, format?, limit?)` | 输出 API 质量清单（缺注释/可疑命名等；只读） |
| `get_component_api(component_name)` | 获取组件完整公开 API（按文件分组） |
| `get_tool_docs(tool_name?, format?)` | 返回工具详细说明与最佳实践（推荐 agent 首次接入先调用；建议多轮检索兜底避免误判） |
| `get_class_detail(component_name, classname)` | 类视图：定义、属性、公开/内部方法 |
| `read_source(component_name, file, start?, end?)` | 按行读取源码（支持模糊文件名） |
| `find_usage_example(component_name)` | 搜索其他组件中的使用示例 |
| `refresh_index` | 手动触发检查更新并重建索引 |
| `watch_status` | 查看定时检查状态和更新日志 |
| `sync_from_config(config_path?)` | 根据配置文件同步组件代码 |
| `sync_gitlab_group(group_id, ...)` | 🆕 自动发现并同步 GitLab Group 下的基础组件 |

## Agent 检索模板（强烈推荐）

当基础组件 API 命名不规范或注释不齐全时，单次检索很容易误判“没有现成能力”。

推荐做法：多轮小 `limit` 检索（中英混合 + 类名/动词组合），逐步收敛到目标能力。

建议流程（可直接复制到 agent 指令中）：

```text
1) get_tool_docs(tool_name="search_component", format="json")
2) search_component(format="json", limit=5) x N 次（N>=3，必要时 N>=6）
   - 先类名/类型：UIImage / UIView / CALayer / NSString / NSURLSession
   - 再语义动词：clip / crop / mask / avatar / radius / border
   - 再常见关键词：圆角 / corner / round / cache / request
3) 如果结果偏离（例如 corner 命中大量 UIView 圆角），追加更定向词：clip / mask / imageWith / tm_
4) 仅在命中明确 file:line 后，再小范围 read_source（例如 30 行）验证
5) 若命中 `api_only` 组件无法 read_source，则改用 get_component_api + get_class_detail + find_usage_example
6) 输出时保留证据链（search/api/class 或 source/example），避免只给“有/没有”的结论
```

一个典型的“圆角头像/图片裁剪”检索组合：
- `UIImage` -> `clip` -> `tm_clipImage` -> `corner`

## 配置文件同步组件

支持根据配置文件自动拉取组件代码：

```bash
# 创建配置文件
cp components.yaml.example components.yaml
# 编辑配置...

# 同步组件（克隆/更新）
python mcp_server.py --sync components.yaml /path/to/pods

# 仅同步，不启动服务
python mcp_server.py --sync --sync-only /path/to/pods

# 同步后启动 HTTP 服务
python mcp_server.py --sync --http /path/to/pods
```

配置文件格式（YAML）：
```yaml
components:
  BTBaseKit: git@gitlab.com:ios/BTBaseKit.git  # 简化格式
  BTNetwork:
    repo: git@gitlab.com:ios/BTNetwork.git
    branch: develop  # 指定分支

access_control:
  exclude_from_index:
    - BTRtcEngine
  api_only:
    - BTCryptoKit
    - BTEncryptKit
```

也可以通过 MCP 工具 `sync_from_config` 在运行时触发同步。

## 访问控制配置（核心组件保护）

在 `components.yaml` 里可配置 `access_control`：

- `exclude_from_index`：组件完全不进入 MCP 索引（`list/search` 不可见）
- `api_only`：仅允许 `search_component/get_component_api/get_class_detail`，拒绝 `read_source/find_usage_example`

规则：
- 名称匹配大小写不敏感，支持写 pod 名或目录名
- `exclude_from_index` 优先级高于 `api_only`
- 默认兜底：`BTRtcEngine` 始终会被排除（即使未配置）

生效方式：
- 修改 `components.yaml` 后执行 `refresh_index` 或重启服务

## GitLab Group 自动发现

自动扫描 GitLab Group 下的所有仓库，识别基础组件并同步：

```bash
# 同步指定 Group 下的基础组件
python mcp_server.py --gitlab-group ios-components /path/to/pods

# 自定义 GitLab 服务器
python mcp_server.py --gitlab-group ios-components \
  --gitlab-url https://gitlab.your-company.com \
  /path/to/pods
```

### 基础组件判定规则

Server 会检查每个仓库的 podspec 文件，以下任一条件满足则判定为基础组件：
- **无 SUPPORT_MIXUP 标记** — podspec 中不含业务组件标记
- **dependency 数量 ≤ 3** — 依赖少，说明是底层组件

### 环境变量配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `GITLAB_URL` | GitLab 服务器地址 | `https://gitlab.com` |
| `GITLAB_TOKEN` | GitLab API Token（需要 read_api 权限） | 无 |

### MCP 工具调用

运行时也可通过 `sync_gitlab_group` 工具触发同步：

```
sync_gitlab_group(group_id="ios-components", gitlab_url="", gitlab_token="", use_ssh=true)
```

## 定时检查更新

```bash
# 每 5 分钟自动检查组件仓库更新
python mcp_server.py --watch 300 /path/to/pods

# HTTP 模式 + 定时检查
python mcp_server.py --http --watch 300 /path/to/pods
```

支持单仓库和多仓库（每个组件独立 git 仓库）。检测到更新后自动 git pull + 重建索引。

## HTTP 模式（云端部署）

```bash
# 生成 API Key
python mcp_server.py --gen-key "teammate-name"

# 启动 HTTP 服务
python mcp_server.py --http --port 8900 /path/to/pods

# 局域网访问（监听所有网卡）
python mcp_server.py --http --host 0.0.0.0 --port 8900 /path/to/pods

# 远程 Claude Code 连接
claude mcp add --transport http ios-components http://your-server:8900/mcp \
  --header "Authorization: Bearer sk-xxx"
```

局域网访问说明：

- 使用 `--host 0.0.0.0` 可让同一局域网设备通过 `http://<你的局域网IP>:8900/mcp` 访问
- 存活检查请使用 `http://<你的局域网IP>:8900/webhook/health`，不要用浏览器直接 `GET /mcp`
- `/mcp` 是 MCP Streamable HTTP 端点，客户端应通过 MCP 协议发起初始化，而不是普通 HTTP 探测
- 如启用 API Key，客户端仍需携带 `Authorization: Bearer sk-xxx`
- 当前未提供 OAuth 自动发现端点；若客户端强依赖 `/.well-known/oauth-authorization-server*`，请改为直连 MCP HTTP + Bearer API Key 模式
- 为兼容最新 Codex / OpenAI MCP 客户端，服务会对 `initialize`、`tools/list`、`resources/list`、`prompts/list` 这类发现阶段请求放行；实际工具调用仍可继续走 Bearer 校验
- 若出现 `421 Misdirected Request`，通常是 Host/Origin 头或代理转发配置问题（默认局域网直连场景不应再出现）

### API Key 管理

```bash
python mcp_server.py --gen-key "alice"    # 生成新 Key
python mcp_server.py --list-keys          # 查看已注册 Key（脱敏显示）
```

Key 存储在 `.api-keys` 文件（权限 600）。支持热更新——添加新 Key 无需重启。

也可通过环境变量设置：
```bash
MCP_API_KEYS="key1,key2" python mcp_server.py --http
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `IOS_PODS_DIR` | 组件库根目录 | 当前目录 |
| `IOS_PODS_INCLUDE` | 仅索引指定组件（逗号分隔；适合 smoke test；建议用于多轮检索兜底） | 无 |
| `IOS_PODS_CONFIG` | 组件配置文件路径（用于 `components` 与 `access_control`） | `components.yaml` |
| `IOS_PODS_CACHE_DIR` | 缓存目录 | 脚本旁 `.cache/` |
| `IOS_PODS_KEYS_FILE` | API Key 文件路径 | 脚本旁 `.api-keys` |
| `IOS_PODS_MIXUP_MARKER` | 业务组件过滤标记 | `SUPPORT_MIXUP` |
| `IOS_PODS_WATCH_INTERVAL` | 定时检查间隔（秒） | `0`（禁用） |
| `MCP_API_KEYS` | API Key（逗号分隔） | 无 |
| `GITLAB_URL` | GitLab 服务器地址 | `https://gitlab.com` |
| `GITLAB_TOKEN` | GitLab API Token | 无 |

## 组件发现机制

Server 自动扫描组件目录中包含 `.podspec` 的子目录。默认过滤规则包括：

- podspec 中存在非空 `SUPPORT_MIXUP` / `BETA_SUPPORT_MIXUP`
- `access_control.exclude_from_index` 命中的组件
- 默认安全兜底：`BTRtcEngine`

## API 文档自动生成

内置工具可从索引缓存自动生成每个组件的 Markdown API 文档，包含方法签名、注释说明、调用示例。对缺注释的 API 可选用 AI（Claude Haiku）自动补全说明。

```bash
# 基础生成（需要先有索引缓存 .cache/index.json）
python tools/generate_api_docs.py --pods-dir /path/to/Pods

# 指定单个组件
python tools/generate_api_docs.py --pods-dir /path/to/Pods --component BTBaseKit

# 预估缺注释 API 数量（不生成文档、不调用 AI）
python tools/generate_api_docs.py --dry-run

# 带 AI 补全生成（需要 ANTHROPIC_API_KEY 环境变量）
ANTHROPIC_API_KEY=sk-ant-xxx python tools/generate_api_docs.py --pods-dir /path/to/Pods --ai-fill

# 自定义输出目录
python tools/generate_api_docs.py --pods-dir /path/to/Pods --output-dir ./my-docs
```

参数说明：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--pods-dir` | Pods 源码目录（用于读取源码和查找调用示例） | 无 |
| `--index-cache` | 索引缓存 JSON 路径 | `.cache/index.json` |
| `--output-dir` | 输出目录 | `docs/api/` |
| `--component` | 指定单个组件名 | 全部组件 |
| `--ai-fill` | 启用 AI 补全缺注释的 API（需要 `ANTHROPIC_API_KEY`） | 关闭 |
| `--dry-run` | 仅统计缺注释数量，不生成文档 | 关闭 |

生成的文档结构：
```text
docs/api/
├── index.md                       # 目录页（组件列表 + 链接）
├── BTBaseKit-底层基类、工具类.md    # 组件 API 文档（组件名-简述）
├── BTNetwork-网络请求封装.md
└── ...
```

文件名格式为 `组件名-简述.md`，简述取自 podspec summary 首行，超过 20 字符自动截断；无 summary 时退回 `组件名.md`。

每个组件文档包含：
- 组件概述（来自 podspec summary/description）
- 按类/协议聚合的 API 列表（Category 方法归属宿主类）
- 枚举类型章节（NS_ENUM/NS_OPTIONS 成员表格）
- typedef / block 类型定义
- 废弃 API 标注（NS_DEPRECATED_IOS / @available 等，含迁移建议）
- 注释自动拆分为摘要 + 详细说明
- 跨组件调用示例（自动扫描其他组件的 import/使用）
- AI 生成的说明会标记 `> *AI 生成*` 并附带调用示例代码

### 上传到飞书知识库

支持将文档上传到飞书知识库，使用飞书官方 CLI 工具 [lark-cli](https://github.com/larksuite/cli)。

**前置条件：**
1. 安装 lark-cli：`npm install -g @larksuite/cli`
2. 初始化配置：`lark-cli config init`
3. 登录授权：`lark-cli auth login --recommend`

```bash
# 仅生成飞书格式 JSON（不上传，保留旧方式）
python tools/generate_api_docs.py --format lark --pods-dir /path/to/Pods

# 上传到飞书知识库（通过 lark-cli）
python tools/generate_api_docs.py \
  --upload --space-id 7xxx --parent-node wikcnXxx \
  --pods-dir /path/to/Pods

# 预览上传内容（不实际执行）
python tools/generate_api_docs.py \
  --upload --preview --space-id 7xxx --parent-node wikcnXxx \
  --pods-dir /path/to/Pods

# 上传单个组件
python tools/generate_api_docs.py \
  --upload --space-id 7xxx --parent-node wikcnXxx \
  --pods-dir /path/to/Pods --component BTBaseKit

# 上传本地 Markdown 文件
python tools/generate_api_docs.py \
  --upload --space-id 7xxx --parent-node wikcnXxx \
  --pods-dir /path/to/Pods --component BTBaseKit
```

飞书上传参数：

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--upload` | 上传到飞书知识库（依赖 lark-cli） | 关闭 |
| `--preview` | 预览上传内容，不实际执行 | 关闭 |
| `--space-id` | 知识库 space_id | 无 |
| `--parent-node` | 父节点 token（wikcnXxx 格式） | 无 |
| `--format lark` | 输出飞书 DocX Block JSON（仅本地输出） | `markdown` |

## 缓存机制

索引缓存在 `.cache/index.json`，基于文件路径和修改时间的 SHA256 哈希。源文件变更时自动重建。

## License

MIT

---

<a name="english"></a>

# MCP iOS Components Server

English | [中文](#mcp-ios-components-server)

MCP Server for querying iOS CocoaPods component APIs. Helps AI coding assistants discover and reuse existing code instead of reinventing the wheel.

## Features

- **Auto component discovery** — scans podspec files, filters by configurable marker
- **Smart API extraction** — ObjC (`@interface`, `@protocol`, `@property` (including block types), methods, inline functions) + Swift (`public/open` declarations)
- **Comment extraction** — `///` and `/** */` doc comments, searchable
- **Cross-component usage search** — find how components are imported/used elsewhere
- **SHA256 cache** — auto-rebuilds index only when source files change
- **HTTP mode + API Key auth** — deploy to cloud, share with team
- **Line-range source reading** — read only the lines you need, saves tokens
- **Per-class aggregated view** — see class definition, properties, public/private methods at a glance

## Architecture (Lightweight Layering)

```text
mcp_server.py                 # Compatibility entrypoint (CLI + import compatibility)
mcp_app/
  bootstrap.py               # Composition layer: MCP tools, main, runtime globals
  config.py                  # Config and access_control loading
  models.py                  # Constants and state model
  access_control.py          # Access-control exports
  state.py                   # AppState export
  indexing/                  # Discovery, parsing, index building
  services/                  # Query/source/sync/update services
  integrations/              # git, gitlab, apikey integrations
  transport/                 # Reserved for transport extraction
```

Notes:
- Public behavior is unchanged: `python mcp_server.py ...` and MCP tool signatures remain compatible.
- `mcp_server.py` is now compatibility-only; core logic is maintained in `mcp_app/`.

## Quick Start

```bash
# Install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install mcp

# Run (stdio mode for Claude Code)
python mcp_server.py /path/to/your/pods

# Or set via environment variable
IOS_PODS_DIR=/path/to/your/pods python mcp_server.py
```

## Configure Claude Code

```bash
claude mcp add -s user ios-components -- \
  /path/to/.venv/bin/python /path/to/mcp_server.py /path/to/your/pods
```

Verify:
```bash
claude mcp list
# ios-components: ... ✓ Connected
```

## Enforce Component Reuse (Recommended)

Copy `AGENTS.md.template` to your iOS project root:

```bash
cp /path/to/mcp-ios-components/AGENTS.md.template /path/to/your/project/AGENTS.md
```

Edit `AGENTS.md` to fill in your project-specific component table. Claude Code will automatically follow the rules and check the component library before implementing features.

## Tools

| Tool | Description |
|------|-------------|
| `list_components` | List all indexed components with stats |
| `search_component(keyword, kind?)` | Search symbols, declarations, comments |
| `get_component_api(component_name)` | Full public API grouped by file |
| `get_class_detail(component_name, classname)` | Class view: definition, properties, methods |
| `read_source(component_name, file, start?, end?)` | Read source lines (fuzzy filename match) |
| `find_usage_example(component_name)` | Find imports/usage in other components |
| `refresh_index` | Manually check for updates and rebuild index |
| `watch_status` | View watch status and recent update logs |
| `sync_from_config(config_path?)` | Sync components from config file |
| `sync_gitlab_group(group_id, ...)` | 🆕 Auto-discover and sync base components from GitLab Group |

## Access Control (Protect Sensitive Components)

Configure `access_control` in `components.yaml`:

```yaml
components:
  BTBaseKit: git@gitlab.com:ios/BTBaseKit.git

access_control:
  exclude_from_index:
    - BTRtcEngine
  api_only:
    - BTCryptoKit
    - BTEncryptKit
```

Behavior:
- `exclude_from_index`: component is fully removed from MCP index (`list/search` cannot see it)
- `api_only`: allow `search_component/get_component_api/get_class_detail`, deny `read_source/find_usage_example`
- Name matching is case-insensitive and accepts either pod name or directory name
- Priority: `exclude_from_index` overrides `api_only`
- Safety default: `BTRtcEngine` is always excluded even without config

Apply changes by running `refresh_index` (or restarting server).

## GitLab Group Auto-Discovery

Automatically scan all repos under a GitLab Group and sync base components:

```bash
# Sync base components from a GitLab Group
python mcp_server.py --gitlab-group ios-components /path/to/pods

# Custom GitLab server
python mcp_server.py --gitlab-group ios-components \
  --gitlab-url https://gitlab.your-company.com \
  /path/to/pods
```

### Base Component Detection Rules

The server checks each repo's podspec. A component is considered "base" if either:
- **No SUPPORT_MIXUP marker** — podspec doesn't contain the business component marker
- **≤ 3 dependencies** — few deps indicates a low-level component

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GITLAB_URL` | GitLab server URL | `https://gitlab.com` |
| `GITLAB_TOKEN` | GitLab API Token (needs read_api scope) | (none) |

## HTTP Mode (Cloud Deployment)

```bash
# Generate API key
python mcp_server.py --gen-key "teammate-name"

# Start HTTP server
python mcp_server.py --http --port 8900 /path/to/pods

# Connect from remote Claude Code
claude mcp add --transport http ios-components http://your-server:8900/mcp \
  --header "Authorization: Bearer sk-xxx"
```

LAN notes:

- Use `http://<your-lan-ip>:8900/webhook/health` for liveness checks instead of opening `GET /mcp` in a browser
- `/mcp` is a Streamable HTTP MCP endpoint, so clients should initialize via the MCP protocol instead of plain HTTP probing
- If API keys are enabled, clients must send `Authorization: Bearer sk-xxx`
- OAuth auto-discovery endpoints are not exposed; clients that require `/.well-known/oauth-authorization-server*` should use direct MCP HTTP with Bearer auth instead
- To better align with current Codex / OpenAI MCP clients, discovery-stage methods such as `initialize` and `tools/list` are allowed without auth while actual tool execution can still require a Bearer token

### API Key Management

```bash
python mcp_server.py --gen-key "alice"    # Generate new key
python mcp_server.py --list-keys          # List all keys (masked)
```

Keys are stored in `.api-keys` file (chmod 600). Supports hot-reload — add new keys without restart.

You can also set keys via environment variable:
```bash
MCP_API_KEYS="key1,key2" python mcp_server.py --http
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `IOS_PODS_DIR` | Path to pods directory | Current directory |
| `IOS_PODS_INCLUDE` | Only index specific components (comma-separated; useful for smoke tests) | (none) |
| `IOS_PODS_CONFIG` | Components config path (for `components` + `access_control`) | `components.yaml` |
| `IOS_PODS_CACHE_DIR` | Cache directory | `.cache/` next to script |
| `IOS_PODS_KEYS_FILE` | API keys file path | `.api-keys` next to script |
| `IOS_PODS_MIXUP_MARKER` | Marker to filter business components | `SUPPORT_MIXUP` |
| `MCP_API_KEYS` | Comma-separated API keys | (none) |
| `GITLAB_URL` | GitLab server URL | `https://gitlab.com` |
| `GITLAB_TOKEN` | GitLab API Token | (none) |

## Component Discovery

The server scans subdirectories with `.podspec` files and applies default filters:

- Non-empty `SUPPORT_MIXUP` / `BETA_SUPPORT_MIXUP` in podspec
- Components matched by `access_control.exclude_from_index`
- Safety default component: `BTRtcEngine`

## API Documentation Generator

Built-in tool to auto-generate Markdown API docs from the index cache, including method signatures, comments, and usage examples. Optionally uses AI (Claude Haiku) to fill in missing comments.

```bash
# Basic generation (requires .cache/index.json)
python tools/generate_api_docs.py --pods-dir /path/to/Pods

# Single component
python tools/generate_api_docs.py --pods-dir /path/to/Pods --component BTBaseKit

# Estimate missing comments count (no docs generated, no AI calls)
python tools/generate_api_docs.py --dry-run

# With AI fill (requires ANTHROPIC_API_KEY)
ANTHROPIC_API_KEY=sk-ant-xxx python tools/generate_api_docs.py --pods-dir /path/to/Pods --ai-fill
```

| Flag | Description | Default |
|------|-------------|---------|
| `--pods-dir` | Pods source directory | (none) |
| `--index-cache` | Index cache JSON path | `.cache/index.json` |
| `--output-dir` | Output directory | `docs/api/` |
| `--component` | Generate for a single component | all |
| `--ai-fill` | Use AI to fill missing comments (needs `ANTHROPIC_API_KEY`) | off |
| `--dry-run` | Only count missing comments, skip generation | off |

### Upload to Lark Wiki

Upload docs to a Lark wiki space using the official [lark-cli](https://github.com/larksuite/cli) tool.

**Prerequisites:**
1. Install lark-cli: `npm install -g @larksuite/cli`
2. Initialize config: `lark-cli config init`
3. Login: `lark-cli auth login --recommend`

```bash
# Generate Lark DocX JSON locally (no upload, legacy mode)
python tools/generate_api_docs.py --format lark --pods-dir /path/to/Pods

# Upload to Lark Wiki (via lark-cli)
python tools/generate_api_docs.py \
  --upload --space-id 7xxx --parent-node wikcnXxx \
  --pods-dir /path/to/Pods

# Preview upload (dry-run, no actual upload)
python tools/generate_api_docs.py \
  --upload --preview --space-id 7xxx --parent-node wikcnXxx \
  --pods-dir /path/to/Pods

# Upload single component
python tools/generate_api_docs.py \
  --upload --space-id 7xxx --parent-node wikcnXxx \
  --pods-dir /path/to/Pods --component BTBaseKit
```

| Flag | Description | Default |
|------|-------------|---------|
| `--upload` | Upload to Lark Wiki (requires lark-cli) | off |
| `--preview` | Preview upload content without executing | off |
| `--space-id` | Wiki space ID | (none) |
| `--parent-node` | Parent node token (wikcnXxx format) | (none) |
| `--format lark` | Output Lark DocX Block JSON (local only) | `markdown` |

## Caching

Index is cached in `.cache/index.json` with SHA256 hash based on file paths and modification times. Cache is automatically rebuilt when source files change.

## License

MIT
