# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

iOS CocoaPods 组件库 MCP Server — 为 AI 代码助手提供组件检索、API 抽取与跨组件引用搜索服务。核心理念：复用优先，拒绝重复造轮子。

## Architecture

- `mcp_server.py` — 兼容入口（CLI + import）
- `mcp_app/` — 核心实现
  - `bootstrap.py` — 应用启动与依赖组合
  - `config.py` — 配置加载与访问控制
  - `indexing/` — 组件发现、ObjC/Swift 解析、索引构建
  - `services/` — 查询、读取、审计服务
  - `integrations/` — Git、GitLab、API Key 集成
- `deploy/` — Docker Compose / Helm / Nginx / systemd 部署
- `skills/` — AI 技能包（给下游 iOS 项目使用）
- `tests/` — pytest 单元/集成测试

## Commands

```bash
# 安装依赖
pip install -r requirements.txt

# 运行测试（需要 PYTHONPATH=. 以解析模块导入）
PYTHONPATH=. pytest

# 运行单个测试
PYTHONPATH=. pytest tests/test_search_component.py -k 'test_name'

# 启动服务（stdio 模式）
python mcp_server.py /path/to/pods

# 启动服务（HTTP 模式）
python mcp_server.py --http --port 8900 /path/to/pods
```

## Modification Rules (MUST follow)

1. **MCP 工具兼容性**：现有工具名与参数签名（`search_component`、`get_component_api`、`read_source` 等）改名或改签名属于破坏性变更，除非用户明确要求
2. **文档同步**：修改工具行为时必须同步更新 `README.md` 的工具列表、示例与参数说明
3. **模板同步**：修改"复用优先"策略时必须同步更新 `AGENTS.md.template`
4. **部署同步**：涉及部署参数（端口、环境变量、鉴权）时检查 `deploy/` 下相关文件与 `deploy/DEPLOY.md`
5. **输出风格**：用户可见提示优先中文，命令与代码保持原始语法

## Environment Variables

@deploy/.env.example

## CI

- `skills-eval` workflow：PR 修改 `skills/**` 时自动校验评测数据集，门禁阈值见 `.github/workflows/skills-eval.yml`

## Pre-commit Checklist

1. 服务能启动（至少 stdio 或 HTTP 之一）
2. MCP 工具清单与 README 一致
3. 新增/修改环境变量后，README 与部署文档已更新
4. 未提交无关文件与临时调试代码

## Subdirectory Instructions

对于 `skills/` 和 `deploy/` 等独立关注点的子目录，可添加子目录 CLAUDE.md 提供模块级指导。
