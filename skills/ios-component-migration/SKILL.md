---
name: ios-component-migration
description: 用于将已有 iOS 重复实现迁移到基础组件，适用于替换自造网络层/图片缓存/路由/弹窗等迁移改造请求；不用于纯新功能编码、纯方案选型、纯 PR review、翻译总结或非 iOS 请求。
metadata:
  author: mcp-ios-components
  version: 1.1.0
  mcp-server: ios-components
  category: refactor
---

# iOS 重复实现迁移到基础组件（分批改造）

## 目标 / 适用场景

识别业务中的重复基础能力实现，建立“旧实现 -> 组件 API”映射，按批次替换并给出验证与回滚策略，避免大爆改。

## 触发信号（应触发）

- “把自定义 URLSession/图片缓存/弹窗/Router 替换成基础组件”
- “迁移到基础网络组件/统一 UI 组件”
- `migration` `replace legacy wrapper` `统一替换`

## 排除信号（不触发）

- 纯新增功能实现（应走 `ios-component-implementation`）
- 纯方案评审（应走 `ios-component-selection`）
- 纯 PR 审查（应走 `ios-component-review`）
- 非 iOS 请求、翻译总结

## 与其他 skill 的边界

- “先评估是否有组件再迁移”：可先用 `ios-component-selection` 做选型，再回到本 skill 输出分批迁移计划。
- “review 一个 PR 发现重复实现”：若重点是审查当前 PR，优先 `ios-component-review`；若用户要求给完整替换方案，再切本 skill。

## 工具调用流程（默认顺序）

1. 识别重复实现点
- 从用户提供的代码/描述中提取能力点与调用面
- 标注影响范围（模块/调用点/核心路径）

2. 多轮检索目标组件（JSON-first）
- 对每类重复能力执行 `search_component(format="json", limit=5)` 3-6 轮
- 命中后 `get_component_api` 确认可替换能力范围
- `get_class_detail` 确认关键入口或适配点

3. 建立迁移映射
- 旧能力 -> 新组件/API
- 参数/返回值/线程/错误处理差异
- 风险等级与迁移批次

4. 识别已有迁移模式（推荐）
- `find_usage_example(component_name)` 查看其他组件使用方式
- 优先复用已有接入模式，避免二次封装风格分叉

5. 输出分批替换计划 + 验证/回滚

## JSON-first 策略

- 检索阶段统一 `search_component(..., format="json", limit=5)`，便于沉淀映射证据。
- `find_usage_example` / `read_source` 仅摘录关键位置，不要贴大量源码。

## 失败恢复与回退路径

1. 无完全匹配组件：
- 优先选择最接近能力的组件 + 薄适配层
- 明确哪些差异暂不替换，禁止新建平行基础层

2. `api_only` 限制：
- 使用 `get_component_api` + `get_class_detail` + `find_usage_example` 替代
- 在风险中标注“实现细节未验证”

3. 改造风险过高：
- 拆分批次（内部页面 -> 非核心流程 -> 核心流程）
- 先做兼容适配层，再逐步替换调用点

## 证据最小集（必须满足）

每个迁移目标至少包含：
- `search_component` 命中证据
- `get_component_api` 目标 API 证据
- `find_usage_example` 或 `get_class_detail` 作为接入方式佐证

## 输出契约（结构化）

1. `重复实现识别结果`
- 重复点清单（能力类型、位置、影响范围）

2. `迁移映射表`（必须）
- 旧能力/旧调用
- 目标组件/API
- 差异点（参数、返回、线程、错误处理）
- 风险等级
- 迁移批次

3. `分批改造计划`
- 批次目标
- 改造步骤
- 验证项
- 回滚触发条件

4. `风险与限制`
- `api_only`、无示例、兼容性未知项

模板见 `references/migration-playbook.md` 与 `references/mapping-template.md`。

## 质量门槛 / 阻塞规则

- 无映射表直接建议全量替换 -> 不合格
- 无验证与回滚策略 -> 不合格
- 引入新的平行基础层 -> 不合格
- 功能语义变化未说明 -> 不合格

## 参考资料（什么时候读哪个 references）

- `references/migration-playbook.md`
  - 输出迁移阶段、批次策略、验证与回滚时读取
- `references/mapping-template.md`
  - 建立“旧 -> 新”映射表时读取

## 示例（精简）

用户：把业务里的 URLSession + 自定义缓存迁移到基础网络组件。

执行要点：
1. 识别“请求封装 + 缓存逻辑”重复点
2. 检索网络/缓存组件并确认 API
3. 建立映射表（差异与风险）
4. 给出分批替换、验证与回滚条件
