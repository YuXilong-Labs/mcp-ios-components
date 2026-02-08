# MCP iOS Components - 计划与 TODO

本文件用于记录后续增强计划（不影响当前可用功能）。

## 已落地（当前阶段）

### 1) 检索兜底（Search-First, Multi-Query Fallback）
- 目标：在基础组件 API 命名不规范 / 注释不齐全时，仍然能通过多轮检索稳定命中可复用能力，避免重复造轮子。
- 现状：
  - `search_component(..., format="json", limit=...)` 支持结构化输出，方便 agent 反复迭代检索与自动化断言。
  - smoke 脚本已固化“先 get_tool_docs，再多轮 search_component（小 limit）”的流程。
- 建议的 agent 检索策略：
  - 先用类名/类型切入：`UIImage`/`UIView`/`CALayer`/`MASConstraint`/`NSURLSession` 等。
  - 再补同义词/动词：`clip/crop/mask/avatar/radius/border`、`cache/request/serialize` 等。
  - 中文/英文混合：`圆角/corner/round`、`裁剪/clip` 等。
  - 如果泛词命中大量 UI 圆角（UIView）而非图片处理（UIImage），追加定向词 `clip`/`mask`/`tm_`/`imageWith` 等。

## TODO（后续增强，先不做）

### 2) API 质量清单（Audit Output Only, No Code Changes）
- 新增工具：`audit_component_api_quality(component_name, format="json", limit=...)`
- 输出内容（JSON 结构，便于后续自动化）：
  - `missing_comment`: 公共 API 无注释/注释过短
  - `suspicious_naming`: 命名不符合约定（缩写/大小写/拼写/语义不清）
  - `weak_discoverability`: 明显功能但关键词难以检索（建议添加别名/注释关键词）
- 目标：让“命名不规范/注释缺失”可量化、可追踪、可逐步收敛。

### 3) AI 辅助治理方案（Patch Generation + Human Review）
- 目标：批量补齐注释、补规范别名、保留兼容性，降低维护成本。
- 流程建议（分阶段、可审计）：
  - Phase 0：定义命名/注释规范（ObjC/Swift 各一套）
  - Phase 1：AI 生成治理提案（基于 `search_component` 命中 + 小范围 `read_source`）
  - Phase 2：AI 生成 patch（只新增/不破坏；旧 API 可选 deprecated）
  - Phase 3：编译/静态检查/小范围试点 -> 扩大覆盖
- 风险控制：
  - 每次 PR 限制改动量（例如 30-80 个符号）
  - 强制 evidence：每个改动必须引用 `file:line` 命中项
  - 默认只补注释；命名治理先“新增别名”再“deprecated 旧 API”

## 备注
- 本仓库职责：提供可检索的“活文档（索引）”与 agent 友好的工具接口。
- 业务组件命名/注释问题的根治仍需回到组件仓库通过 PR 修复；本仓库可以提供清单与建议来驱动治理。
