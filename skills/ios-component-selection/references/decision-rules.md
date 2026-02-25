# Selection 决策规则

## 1. 候选排序优先级

1. Category / Extension（调用自然，侵入小）
2. 协议或统一基类（替换成本可控）
3. Helper / Utility（作为兜底）

## 2. 证据优先级

1. `get_component_api` 明确公开 API
2. `find_usage_example` 有真实使用示例
3. `get_class_detail` 可定位关键入口
4. `read_source` 小范围验证细节（非必须，`api_only` 可能不可用）

## 3. 何时使用 `audit_component_api_quality`

建议在以下场景使用（可选）：
- 两个候选能力相近，需要比较维护风险
- 命名/注释明显混乱，担心接入成本
- 方案评审要求给出长期维护判断

注意：`audit_component_api_quality` 是只读启发式清单，不等于最终结论，需结合 API/示例验证。

## 4. 何时建议新增组件

仅当以下条件同时满足：
- 已完成多轮检索（至少 3 轮）
- 候选无法覆盖关键能力或约束
- 已明确“缺失能力”与边界
- 已给出短期替代方案/适配方案（若可行）
