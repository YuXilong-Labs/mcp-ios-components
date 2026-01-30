# MCP iOS Components Server

[English](#english) | 中文

iOS CocoaPods 组件库 MCP Server，帮助 AI 编码助手发现和复用已有代码，避免重复造轮子。

## 特性

- **自动组件发现** — 扫描 podspec 文件，可配置过滤标记
- **智能 API 提取** — ObjC（`@interface`、`@protocol`、`@property`、方法、内联函数）+ Swift（`public/open` 声明）
- **注释提取** — 支持 `///` 和 `/** */` 文档注释，可搜索
- **跨组件使用搜索** — 查找组件在其他组件中的 import 和使用方式
- **SHA256 缓存** — 源文件变更时自动重建索引
- **HTTP 模式 + API Key 鉴权** — 部署到云端，团队共享
- **按行读取源码** — 只读需要的行，节省 token
- **按类聚合视图** — 一览类定义、属性、公开/内部方法

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

## 工具列表

| 工具 | 说明 |
|------|------|
| `list_components` | 列出所有已索引组件及统计信息 |
| `search_component(keyword, kind?)` | 搜索符号、声明、注释（模糊匹配） |
| `get_component_api(component_name)` | 获取组件完整公开 API（按文件分组） |
| `get_class_detail(component_name, classname)` | 类视图：定义、属性、公开/内部方法 |
| `read_source(component_name, file, start?, end?)` | 按行读取源码（支持模糊文件名） |
| `find_usage_example(component_name)` | 搜索其他组件中的使用示例 |

## HTTP 模式（云端部署）

```bash
# 生成 API Key
python mcp_server.py --gen-key "teammate-name"

# 启动 HTTP 服务
python mcp_server.py --http --port 8900 /path/to/pods

# 远程 Claude Code 连接
claude mcp add --transport http ios-components http://your-server:8900/mcp \
  --header "Authorization: Bearer sk-xxx"
```

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
| `IOS_PODS_CACHE_DIR` | 缓存目录 | 脚本旁 `.cache/` |
| `IOS_PODS_KEYS_FILE` | API Key 文件路径 | 脚本旁 `.api-keys` |
| `IOS_PODS_MIXUP_MARKER` | 业务组件过滤标记 | `SUPPORT_MIXUP` |
| `MCP_API_KEYS` | API Key（逗号分隔） | 无 |

## 组件发现机制

Server 自动扫描组件目录中包含 `.podspec` 的子目录。podspec 中含有 `SUPPORT_MIXUP` 标记的组件会被过滤（可通过 `IOS_PODS_MIXUP_MARKER` 配置）。

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
- **Smart API extraction** — ObjC (`@interface`, `@protocol`, `@property`, methods, inline functions) + Swift (`public/open` declarations)
- **Comment extraction** — `///` and `/** */` doc comments, searchable
- **Cross-component usage search** — find how components are imported/used elsewhere
- **SHA256 cache** — auto-rebuilds index only when source files change
- **HTTP mode + API Key auth** — deploy to cloud, share with team
- **Line-range source reading** — read only the lines you need, saves tokens
- **Per-class aggregated view** — see class definition, properties, public/private methods at a glance

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

## Tools

| Tool | Description |
|------|-------------|
| `list_components` | List all indexed components with stats |
| `search_component(keyword, kind?)` | Search symbols, declarations, comments |
| `get_component_api(component_name)` | Full public API grouped by file |
| `get_class_detail(component_name, classname)` | Class view: definition, properties, methods |
| `read_source(component_name, file, start?, end?)` | Read source lines (fuzzy filename match) |
| `find_usage_example(component_name)` | Find imports/usage in other components |

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
| `IOS_PODS_CACHE_DIR` | Cache directory | `.cache/` next to script |
| `IOS_PODS_KEYS_FILE` | API keys file path | `.api-keys` next to script |
| `IOS_PODS_MIXUP_MARKER` | Marker to filter business components | `SUPPORT_MIXUP` |
| `MCP_API_KEYS` | Comma-separated API keys | (none) |

## Component Discovery

The server automatically discovers components by scanning the pods directory for subdirectories containing `.podspec` files. Components with `SUPPORT_MIXUP` marker in their podspec are filtered out (configurable via `IOS_PODS_MIXUP_MARKER`).

## Caching

Index is cached in `.cache/index.json` with SHA256 hash based on file paths and modification times. Cache is automatically rebuilt when source files change.

## License

MIT
