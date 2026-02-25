---
name: ios-component-selection
description: 用于 iOS 需求评审/技术方案/组件选型阶段，输出可复用组件矩阵、证据和风险；适用于“先评估是否已有组件”“方案设计/selection”；不用于直接编码实现、纯迁移替换、纯 PR review、翻译总结或非 iOS 请求。
metadata:
  author: mcp-ios-components
  version: 1.1.0
  mcp-server: ios-components
  category: architecture
---

# iOS 组件选型评估（证据驱动）

## 目标 / 适用场景

在需求评审或技术方案阶段识别可复用组件，输出候选矩阵、主备方案、风险与落地注意事项，避免开发中途发现重复建设。

## 触发信号（应触发）

- “先做组件化选型/方案评估”
- “这个需求要不要新增组件”
- “给我主方案/备选方案”
- `selection` `architecture` `方案评审` `需求评审`

## 排除信号（不触发）

- 明确要求直接写代码/改代码（应走 `ios-component-implementation`）
- 明确要求替换旧实现/迁移封装（应走 `ios-component-migration`）
- 明确要求 PR 审查（应走 `ios-component-review`）
- 非 iOS 方案、纯总结、纯翻译

## 与其他 skill 的边界

- “先评估再实现”：本 skill 先执行，输出方案后交给 `ios-component-implementation`。
- “review 中讨论更优组件”：若主目标是审查当前改动，仍优先 `ios-component-review`。
- “迁移方案设计”：若包含具体替换批次/回滚策略并以改造为主，优先 `ios-component-migration`。

## 工具调用流程（默认顺序）

1. 工具确认（必要时）
- `get_tool_docs(tool_name="search_component", format="json")`
- `get_tool_docs(tool_name="find_usage_example", format="json")`

2. 需求拆解
- 目标、约束（iOS 版本、性能、稳定性、工期）
- 能力点（网络/UI/图片/存储/路由/监控等）

3. 多轮检索（JSON-first）
- 对每个能力点执行 `search_component(format="json", limit=5)` 3-6 轮
- 使用中文词 / 英文词 / 类名词收敛
- 命中偏离时用更窄词或 `kind`

4. 候选验证
- `get_component_api`：确认公开 API 范围
- `get_class_detail`：确认关键类/协议入口
- `find_usage_example`：至少对顶级候选执行 1 次
- `audit_component_api_quality`（可选）：候选命名/注释质量差异明显时用于“维护风险”评估

5. 方案输出
- 候选矩阵（含证据字段）
- 主方案 / 备选方案 / 不建议方案
- 风险、依赖边界、验证重点

## JSON-first 策略

- 所有检索优先 `format="json"`，便于生成候选矩阵和证据列。
- `find_usage_example` 暂为 text 输出时，摘取最相关引用位置作为证据，不要整段粘贴。

## 失败恢复与回退路径

1. 候选过多：
- 按约束过滤（平台版本、性能、稳定性）
- 优先有使用示例的候选
- 必要时用 `audit_component_api_quality` 辅助风险分层

2. 无明确候选：
- 增补检索轮次并记录范围
- 输出“缺失能力”与新增组件建议边界（仅在证据不足时建议新建）

3. `api_only` 限制：
- 用 `get_component_api` + `get_class_detail` + `find_usage_example` 做替代验证
- 明确标注哪些实现细节无法验证

## 证据最小集（必须满足）

每个进入候选矩阵的“推荐/备选”项至少包含：
- `search_component` 命中关键词
- `get_component_api` 关键 API
- `find_usage_example` 或 `get_class_detail` 佐证

## 输出契约（结构化）

1. `需求背景`
- 目标
- 约束（版本/性能/稳定性/工期）

2. `能力拆解`
- 按能力点分解需求

3. `候选组件矩阵`（必须带证据字段）
- 能力点
- 候选组件
- 关键 API
- 证据（关键词/API/示例）
- 优点
- 风险（可含 API 质量）
- 结论

4. `推荐方案`
- 主方案
- 备选方案
- 不建议方案与原因

5. `落地建议`
- 依赖边界
- 测试重点
- 回滚/降级策略

模板见 `references/output-template.md`。

## 质量门槛 / 阻塞规则

- 只给“可行/不可行”结论，不给证据 -> 不合格
- 未给主/备/不建议三类方案（适用时） -> 不合格
- 无检索证据就建议新建组件 -> 不合格

## 参考资料（什么时候读哪个 references）

- `references/output-template.md`
  - 生成候选矩阵与主备方案时读取
- `references/decision-rules.md`
  - 候选过多、证据冲突、需要决定是否建议新建组件时读取

## 示例（精简）

用户：做一个带分页列表、空态、下拉刷新的页面，先给组件化方案。

执行要点：
1. 拆出分页/列表/空态/刷新能力点
2. 每个能力点多轮 `search_component(format="json", limit=5)`
3. 对顶级候选做 `get_component_api` + `find_usage_example`
4. 输出带证据矩阵与主备方案
