# AGENTS.md

## 项目定位

本仓库是 `mcp-ios-components`：为 iOS CocoaPods 组件库提供 MCP 检索服务，核心目标是“复用优先，减少重复造轮子”。

## 关键文件

- `/Users/yuxilong/clawd/mcp-ios-components/mcp_server.py`：唯一核心实现（索引、MCP 工具、HTTP 模式、同步逻辑）。
- `/Users/yuxilong/clawd/mcp-ios-components/README.md`：功能说明与用户使用文档（中英双语）。
- `/Users/yuxilong/clawd/mcp-ios-components/AGENTS.md.template`：给下游 iOS 项目复制使用的模板。
- `/Users/yuxilong/clawd/mcp-ios-components/components.yaml.example`：组件同步配置示例。
- `/Users/yuxilong/clawd/mcp-ios-components/deploy/`：Docker Compose / Helm / Nginx / systemd 部署文件。

## 本地开发命令

```bash
cd /Users/yuxilong/clawd/mcp-ios-components
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 本地 stdio 模式
python mcp_server.py /path/to/pods

# HTTP 模式
python mcp_server.py --http --port 8900 /path/to/pods
```

## 修改规范（必须遵守）

1. 保持工具名与参数兼容：
   - 现有 MCP 工具（如 `search_component`、`get_component_api`、`read_source`）改名或改签名属于破坏性变更，除非用户明确要求。
2. 修改工具行为时同步文档：
   - 同步更新 `/Users/yuxilong/clawd/mcp-ios-components/README.md` 的工具列表、示例与参数说明。
3. 修改“复用优先”策略时同步模板：
   - 同步更新 `/Users/yuxilong/clawd/mcp-ios-components/AGENTS.md.template`，确保下游项目规则一致。
4. 涉及部署参数（端口、环境变量、鉴权、Webhook）时：
   - 同步检查 `/Users/yuxilong/clawd/mcp-ios-components/deploy/` 下相关文件与 `/Users/yuxilong/clawd/mcp-ios-components/deploy/DEPLOY.md`。
5. 保持输出风格：
   - 用户可见提示优先中文，命令与代码保持原始语法。

## 提交前自检

1. 能启动服务（至少 stdio 或 HTTP 之一）。
2. MCP 工具清单与 README 一致。
3. 新增/修改环境变量后，README 与部署文档已更新。
4. 未提交无关文件与临时调试代码。

## 当前已知待办

以 `/Users/yuxilong/clawd/mcp-ios-components/TODO.md` 为准（多分支索引、依赖图、API 变更追踪等）。
