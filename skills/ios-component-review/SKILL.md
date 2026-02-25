---
name: ios-component-review
description: 用于 iOS PR/变更审查阶段检查是否重复造轮子或绕过基础组件，输出证据链、严重级别和整改建议；不用于直接编码实现、纯方案选型、纯迁移计划、翻译总结或非 iOS 请求。
metadata:
  author: mcp-ios-components
  version: 1.1.0
  mcp-server: ios-components
  category: code-review
---

# iOS 组件复用审查（证据链审查）

## 目标 / 适用场景

在 PR review / 变更审查 / 发布前质量门禁中识别“可复用却未复用”的改动，给出组件证据链、严重级别和整改建议，必要时阻塞合入。

## 触发信号（应触发）

- “review 这个 PR，检查是否重复造轮子/绕过基础组件”
- “发布前审查是否有平行封装”
- `PR review` `code review` `审查改动` `质量门禁`

## 排除信号（不触发）

- 明确要求直接实现功能（应走 `ios-component-implementation`）
- 明确要求设计方案/选型（应走 `ios-component-selection`）
- 明确要求迁移改造计划（应走 `ios-component-migration`）
- 非 iOS、纯总结/翻译

## 与其他 skill 的边界

- “review + 顺便给迁移建议”：主目标是审查则优先本 skill；整改方案可引用 `ios-component-migration` 风格输出。
- “review 后直接改代码”：先给审查结论，再进入 `ios-component-implementation` 或 `ios-component-migration`。

## 工具调用流程（默认顺序）

1. 提取疑似重复点
- 从 PR diff/变更描述中识别网络、图片、路由、弹窗、缓存等基础能力改动

2. 多轮检索复用证据（JSON-first）
- `search_component(format="json", limit=5)` 至少 3 轮
- 使用语义词/英文词/类名词收敛

3. 组件证据确认
- `get_component_api`：确认已有公开 API
- `get_class_detail`：确认关键类或方法入口
- 必要时 `read_source(20-40行)`：确认语义/边界
- 可补 `find_usage_example`：提供替换参考写法

4. 输出审查结论
- 问题项（位置、描述、证据链、修复建议、严重级别）
- 是否阻塞
- 豁免条件（如适用）

## JSON-first 策略

- 检索阶段默认 `format="json"`，便于记录证据与评测。
- `read_source` 只截取必要范围；避免大量源码搬运影响审查可读性。

## 失败恢复与回退路径

1. 搜索命中不稳定：
- 补同义词与类名词，缩小 `limit` 做收敛
- 对前 2 个候选做 API 对比，避免误判“已有组件”

2. `api_only` 限制：
- 记录限制并改用 `get_component_api` + `get_class_detail` + `find_usage_example`
- 在审查结论中标注证据完整度（完整/受限）

3. 用户提供信息不足（无 diff / 无代码片段）：
- 先给审查检查框架与所需最小上下文
- 不虚构文件位置或 API 证据

## 证据最小集（必须满足）

每个中高风险问题项至少包含：
- `search_component` 命中证据
- `get_component_api` 对应 API 证据
- `get_class_detail` 或 `read_source` / `find_usage_example` 佐证

## 输出契约（结构化）

1. `审查结论`
- 通过 / 需整改 / 阻塞
- 总体风险摘要

2. `问题项`（逐条）
- 文件位置
- 问题描述
- 组件证据链（search/api/class/source 或 example）
- 修复建议（推荐 API）
- 严重级别（高/中/低）
- 是否阻塞

3. `豁免项`（如有）
- 当前组件缺失点
- 临时方案范围
- 收敛计划（责任人 + 时间）

4. `建议动作`
- 必改项
- 可延后项

模板见 `references/review-template.md`，严重级别规则见 `references/severity-rubric.md`。

## 质量门槛 / 阻塞规则

- 只说“重复造轮子”但无证据 -> 不合格
- 中高风险问题无替换建议 -> 不合格
- 阻塞判定不符合 `severity-rubric.md` -> 不合格
- 拒绝替换但无豁免说明（证据充分） -> 默认阻塞

## 参考资料（什么时候读哪个 references）

- `references/severity-rubric.md`
  - 判定严重级别与阻塞/豁免时读取
- `references/review-template.md`
  - 输出审查结论与问题项结构时读取

## 示例（精简）

用户：帮我 review 这个 PR，重点检查有没有自定义图片下载器。

执行要点：
1. 提取图片下载/缓存相关改动点
2. 多轮 `search_component(format="json", limit=5)` 检索现有能力
3. 用 `get_component_api` + `get_class_detail` 确认证据
4. 输出问题项、严重级别与替换建议（必要时阻塞）
