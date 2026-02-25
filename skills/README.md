# mcp-ios-components 技能包（生产版）

本目录提供与 `mcp-ios-components` 配套的 Agent Skills，目标是把“可查询组件”升级为“可执行工作流”，以证据驱动的方式减少重复造轮子。

## Skills 列表

- `ios-component-implementation`
  - 用途：实现需求时执行“检索组件 -> 选型确认 -> 代码落地 -> 自检”。
- `ios-component-selection`
  - 用途：需求评审/方案阶段做组件选型、风险评估与主备方案输出。
- `ios-component-migration`
  - 用途：将已有重复实现迁移到基础组件，输出映射表、分批改造与回滚策略。
- `ios-component-review`
  - 用途：PR/变更审查时检查是否绕过组件或重复造轮子，输出证据链与阻塞建议。

## 推荐组合启用策略

1. 日常开发：`implementation` + `review`
2. 需求评审前置：加 `selection`
3. 历史治理/收敛：加 `migration`

## 一键安装 Skills（Claude / Codex）

仓库提供安装脚本：`/Users/yuxilong/clawd/mcp-ios-components/scripts/install_skills.py`

常用命令：

```bash
# 同时安装到 Codex + Claude（默认 all）
python3 scripts/install_skills.py

# 仅安装到 Codex（默认目录：$CODEX_HOME/skills 或 ~/.codex/skills）
python3 scripts/install_skills.py --target codex

# 仅安装到 Claude（自动探测常见目录；探测不到时请显式指定）
python3 scripts/install_skills.py --target claude --claude-dir ~/.claude/skills

# 指定两个目标目录并自动覆盖（无交互）
python3 scripts/install_skills.py --target all \
  --codex-dir ~/.codex/skills \
  --claude-dir ~/.claude/skills \
  --yes
```

脚本特性：
- 自动展示源版本与目标已安装版本（版本提示）
- 发现已存在技能时交互确认覆盖（或使用 `--yes`）
- 安装后校验 `SKILL.md` / frontmatter / `agents/openai.yaml`
- 支持 `--dry-run` 和 `--include <skill-name>`（只装指定技能）

## 配套要求（MCP 能力）

必须先连接 `mcp-ios-components` 服务，并优先保证以下工具可用：
- `search_component`
- `get_component_api`
- `get_class_detail`
- `find_usage_example`
- `read_source`
- `get_tool_docs`
- `audit_component_api_quality`（可选但推荐）

推荐在业务仓库根目录配置 `AGENTS.md`，强化“复用优先”规则。

## 与 MCP 工具的最佳配合方式（JSON-first）

- 首次接入或工具语义不清：先用 `get_tool_docs(..., format="json")`
- 检索默认：`search_component(format="json", limit=5)` 多轮小步收敛
- 命中后：`get_component_api` -> `get_class_detail` -> 必要时 `read_source(20-40 行)`
- `api_only` 组件：使用 `get_component_api` / `get_class_detail` / `find_usage_example` 替代源码验证
- 只有在需要人工展示时才使用 `format="text"`

## 渐进披露设计（Progressive Disclosure）

- `SKILL.md`：只保留触发边界、流程、失败恢复、输出契约
- `references/`：存放词表、模板、判定规则、执行手册
- `agents/openai.yaml`：为 Codex/Claude UI 提供展示与默认提示信息（双兼容）

## 参考资料与评测

- 每个 skill 下的 `references/` 包含生产实践模板与执行手册
- `evals/` 提供触发与功能回归用例：
  - `trigger-positive.jsonl`
  - `trigger-negative.jsonl`
  - `functional-cases.md`
  - `run_eval.py`（指标计算与门禁脚本）

## 评测闭环流程（建议）

1. 先跑触发评测（正负样本）
2. 再跑功能用例（实现 / 选型 / 迁移 / 审查）
3. 回填 `results/latest.jsonl`（含证据字段与流程字段）
4. 运行 `run_eval.py --assert-thresholds` 做门禁
5. 根据指标迭代 skill 文案与 references

## 验收建议（最终目标）

- 触发准确率：>= 95%
- 误触发率：<= 5%
- 复用证据完整率：>= 98%
- 阻塞级问题漏检率：<= 2%
- 流程合规率：>= 90%（有流程字段数据时）
