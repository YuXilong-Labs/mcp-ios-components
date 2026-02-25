---
name: ios-component-implementation
description: 用于 iOS 功能实现/页面开发/接口落地时强制执行“先检索组件再编码”，适用于 implement/build/coding/按组件化规范开发/避免重复造轮子；不用于纯选型评审、纯迁移改造、纯 PR review、纯翻译总结或非 iOS 请求。
metadata:
  author: mcp-ios-components
  version: 1.1.0
  mcp-server: ios-components
  category: ios-engineering
---

# iOS 组件化实现工作流（复用优先）

## 目标 / 适用场景

在实现页面、功能、接口、交互时，先用 `mcp-ios-components` 检索现成能力，再落地代码，输出可审计的复用证据，避免重复造轮子。

适用请求示例：
- “实现头像圆角缓存加载，优先复用现有组件”
- “按组件化规范做这个列表页”
- “实现上传接口，不要再封装一层网络”

## 触发信号（应触发）

命中以下表达时应优先触发本 skill：
- 实现/开发/编码/build 某个 iOS 页面、功能、接口、组件
- 明确提到“复用现有组件 / 不要重复造轮子 / 按组件化规范”
- 要求产出代码（而非仅方案）

关键词信号（中英混合）：
- `实现` `开发` `写代码` `落地` `接入`
- `implement` `build` `code` `integrate`
- `iOS` `Objective-C` `Swift`

## 排除信号（不触发）

以下情况不应触发本 skill：
- 纯方案评审/选型（应走 `ios-component-selection`）
- 纯迁移/替换既有实现（应走 `ios-component-migration`）
- 纯 PR 审查/发布前检查（应走 `ios-component-review`）
- 纯翻译、总结、算法题、非 iOS 技术问题

## 与其他 skill 的边界

- 同时出现“先评估方案再实现”：优先 `ios-component-selection`，待方案确认后再进入本 skill。
- 同时出现“review + 给修复建议”：优先 `ios-component-review`；若用户明确要求直接改实现，再切回本 skill。
- 同时出现“替换旧封装到基础组件”：优先 `ios-component-migration`。

## 工具调用流程（默认顺序）

### 0) 工具确认（首次接入或工具语义不清时）

- `get_tool_docs(tool_name="search_component", format="json")`
- 必要时再看：`get_tool_docs(tool_name="read_source", format="json")`

### 1) 拆解需求能力点

将需求拆成能力清单（示例）：
- 网络 / 上传下载
- UI 组件 / 列表 / 空态 / 刷新
- 图片处理 / 缓存
- 存储 / 工具方法 / 埋点

### 2) 多轮检索（JSON-first，3-6 轮）

默认规则：
- 使用 `search_component(format="json", limit=5)` 小步收敛
- 至少 3 轮：中文语义词 + 英文同义词 + 类名/类型词
- 结果偏离时，用 `kind` 或更窄关键词收敛

示例组合：
- `圆角` -> `corner` -> `UIImage` -> `clip` -> `avatar`
- `请求` -> `request` -> `URLSession` -> `upload`

### 3) 候选确认（证据必须落地到 API）

- 对候选组件执行 `get_component_api(component_name)`
- 对关键类执行 `get_class_detail(component_name, classname)`
- 仅在需要确认细节实现或边界时，小范围 `read_source`（20-40 行）
- 命名/注释质量可疑时，补 `audit_component_api_quality(component_name, format="json")`

### 4) 实现落地

- 只使用已确认组件 API 编码
- 禁止再手写同类基础能力（网络层、图片缓存、Toast、Router 等）
- 若组件能力缺少一小段功能：优先补薄适配层，不重写整套能力

### 5) 实现后自检

至少核对：
- 是否绕过基础组件
- 是否新增平行封装
- 错误处理/空态/超时/边界是否覆盖
- 是否仍有代码可替换为现有组件 API

## JSON-first 策略

- 默认 `search_component(..., format="json", limit=5)`，便于记录命中证据与后续自动化评估。
- 仅在人工阅读阶段或需要展示时再切换 `format="text"`。
- 不建议单次 `limit` 很大；先小样本多轮检索，避免“误判无结果/误选错误组件”。

## 失败恢复与回退路径

1. 无命中：
- 追加同义词、类名词、动词词再搜（至少补 2 轮）
- 明确输出“已检索关键词列表 + 未命中范围”
- 再给最小新增实现（边界清楚，避免变成基础库重写）

2. 命中很多但不确定：
- 用更窄关键词（类名 + 动词）
- 使用 `kind` 限制（如 `method` / `interface`）
- 对前 2-3 个候选做 `get_component_api` 对比，不盲选

3. `api_only` 组件无法 `read_source`：
- 记录访问限制
- 使用 `get_component_api` + `get_class_detail` + `find_usage_example` 替代
- 在结论中标注“证据受限”与未确认项

4. 工具缺失或返回异常：
- 优先调用 `get_tool_docs` 确认参数/格式
- 降级为 text 格式检索并说明限制
- 不可虚构 API 签名，必要时向用户要更多上下文

## 证据最小集（必须满足）

每个关键能力点至少包含：
- 1 组 `search_component` 命中证据（关键词 + 命中项）
- 1 次 `get_component_api` 证据
- 1 次 `get_class_detail` 或 `read_source`（`api_only` 时可改 `find_usage_example`）

## 输出契约（结构化）

默认输出顺序：
1. `检索摘要`
- 能力点拆解
- 关键词轮次矩阵（轮次/关键词/命中组件）
- 收敛结果与未命中点

2. `证据链`
- `search_component` 关键命中
- `get_component_api` 关键 API
- `get_class_detail` / `read_source` / `find_usage_example` 佐证

3. `选型决策表`
- 能力点
- 推荐组件/API
- 选择理由
- 不选候选原因

4. `代码实现`
- 最终代码（仅使用已确认 API）
- 必要注释（边界/错误处理）

5. `自检结论`
- 是否仍存在重复造轮子风险
- 风险与限制（含 `api_only`、证据不足项）
- 后续动作

详细模板见 `references/output-contract.md`。

## 质量门槛 / 阻塞规则

- 未进行多轮检索（<3 轮） -> 不合格
- 未提供 `get_component_api` 证据 -> 不合格
- 直接手写已有基础能力 -> 不合格
- 无命中却未说明检索范围 -> 不合格

## 参考资料（什么时候读哪个 references）

- `references/keyword-strategy.md`
  - 需要扩展关键词、处理多义词、收敛检索时读取
- `references/checklist.md`
  - 开发前/开发后自检时读取
- `references/output-contract.md`
  - 需要按固定结构输出证据与代码时读取

## 示例（精简）

用户：实现头像圆角并缓存加载，优先复用现有组件。

执行要点：
1. 拆解为“图片圆角 + 图片缓存加载”
2. `search_component(format="json", limit=5)` 至少 3 轮（`圆角`/`corner`/`UIImage`/`cache`）
3. `get_component_api` 确认 API，再 `get_class_detail` 或小范围 `read_source`
4. 用现有组件实现并输出证据链 + 自检结论
