# mcp-ios-components 技能包（生产版）

本目录提供与 `mcp-ios-components` 配套的 Agent Skills，目标是把“可查询组件”升级为“可执行工作流”，从源头减少重复造轮子。

## Skills 列表

- `ios-component-implementation`
  - 用途：在实现需求时，自动完成“检索组件 -> 选型 -> 落地代码 -> 自检”。
- `ios-component-selection`
  - 用途：需求评审/方案阶段做组件选型与风险评估。
- `ios-component-migration`
  - 用途：把已有重复实现迁移到基础组件。
- `ios-component-review`
  - 用途：PR/代码审查时检查是否绕过组件、是否重复造轮子。

## 推荐启用顺序

1. 先启用 `ios-component-implementation`
2. 再启用 `ios-component-review`
3. 按需启用 `selection` 与 `migration`

## 配套要求

- 必须先连接 MCP 服务，并可用以下工具：
  - `search_component`
  - `get_component_api`
  - `get_class_detail`
  - `find_usage_example`
  - `read_source`
  - `get_tool_docs`
- 推荐在业务仓库根目录配置 `AGENTS.md`，强化“复用优先”规则。

## 参考资料与评测

- 每个 skill 下的 `references/` 包含生产实践模板与执行手册
- `evals/` 提供触发与功能回归用例：
  - `trigger-positive.jsonl`
  - `trigger-negative.jsonl`
  - `functional-cases.md`
  - `run_eval.py`（指标计算与门禁脚本）
- CI 模板：`.github/workflows/skills-eval.yml`

## 验收建议

- 触发准确率：>= 90%
- 组件复用率：显著提升（建议统计周报）
- PR 中重复造轮子问题：持续下降
