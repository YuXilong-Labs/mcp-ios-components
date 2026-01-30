# MCP iOS Components Server (Python)

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
