# Implementation Checklist（防重复造轮子）

## 使用时机

- 开发前：确认检索动作和证据准备齐全
- 开发后：做重复实现与边界处理自检

## 开发前

- [ ] 需求已拆成能力点（网络/UI/图片/存储/路由/埋点/工具）
- [ ] 已调用 `get_tool_docs`（首次接入或工具语义不清时）
- [ ] 每个关键能力点至少 3 轮 `search_component`
- [ ] 检索采用 `format="json"`、`limit=5` 小步收敛
- [ ] 至少覆盖：中文词 + 英文词 + 类名/类型词
- [ ] 至少 1 个候选做 `get_component_api`
- [ ] 关键类做 `get_class_detail` 或 `read_source(20-40行)`
- [ ] 命名/注释可疑时评估是否加 `audit_component_api_quality`

## 开发中

- [ ] 代码只使用已确认组件 API
- [ ] 未新增平行基础封装（网络/图片缓存/Toast/Router 等）
- [ ] 关键错误路径有处理（失败/超时/空数据/权限）
- [ ] 若能力缺失，仅增加薄适配层，未重写整套基础能力

## 开发后

- [ ] 输出关键词轮次矩阵（检索摘要）
- [ ] 输出证据链（search/api/class 或 source/example）
- [ ] 输出选型理由（为何选 A，不选 B）
- [ ] 输出风险与限制（含 `api_only` / 无示例 / 注释不足）
- [ ] 自检是否仍存在可复用但未复用的代码

## `api_only` 组件补充检查

- [ ] 记录 `read_source/find_usage_example` 的访问限制（如被拒绝）
- [ ] 用 `get_component_api` + `get_class_detail` 进行替代验证
- [ ] 在结论中标注“证据受限”与未确认项
