---
name: ios-component-selection
description: 用于需求评审和技术方案阶段的 iOS 组件选型。自动检索 mcp-ios-components，输出可复用组件、依赖影响、风险和建议，避免进入开发后才发现重复建设。
metadata:
  author: mcp-ios-components
  version: 1.0.0
  mcp-server: ios-components
  category: architecture
---

# iOS 组件选型评估

## 适用场景

- “这个需求该用哪些现有组件？”
- “做这个页面要不要新增基础库能力？”
- “给我一个组件化方案”

## 工作流

1. 解析需求目标与约束（平台版本、性能、稳定性）
2. 对每个能力点执行多轮 `search_component`
3. 通过 `get_component_api` 和 `find_usage_example` 验证可行性
4. 输出选型结论和风险

## 输出模板

### 1) 需求能力拆解
- 能力 A
- 能力 B

### 2) 候选组件矩阵
- 组件名
- 关键 API
- 优点
- 风险
- 适用性结论

### 3) 推荐方案
- 主方案
- 备选方案
- 不建议方案及原因

### 4) 落地注意事项
- 依赖边界
- 迁移成本
- 测试重点

## 参考资料

- 输出模板：`references/output-template.md`

## 规则

- 禁止只给“可行”结论，不给组件/API 证据
- 禁止在无检索证据时建议新建组件
- 如建议新建，必须说明“已检索范围”和“缺失能力”
