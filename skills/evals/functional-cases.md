# Functional Cases（扩展版）

以下用例用于检查：工具调用顺序、证据完整性、输出契约、失败恢复与阻塞判定。

## Case 1: Implementation - 头像圆角 + 缓存（多义词收敛）
输入：实现头像圆角+缓存加载，优先复用现有组件
期望：
- 至少 3 轮 `search_component(format="json", limit=5)`
- 对 `corner`/`UIImage` 等多义词进行收敛
- 有 `get_component_api` 与 `get_class_detail` 或 `read_source` 证据
- 输出“选型决策表 + 代码实现 + 自检结论”

## Case 2: Implementation - 完全无命中能力
输入：实现一个业务特有协议解析器（组件库可能没有）
期望：
- 仍执行多轮检索并记录关键词范围
- 明确“未命中原因”
- 给出最小新增实现边界，不扩展成基础库

## Case 3: Implementation - `api_only` 组件命中
输入：实现某加密能力，命中受保护组件（`api_only`）
期望：
- `read_source` 被拒绝后能正确降级
- 使用 `get_component_api` / `get_class_detail` / `find_usage_example` 替代
- 输出“证据受限”说明

## Case 4: Selection - 分页列表 + 空态 + 下拉刷新
输入：做一个带分页列表和空态页面的需求评审
期望：
- 输出能力拆解
- 候选组件矩阵完整且包含证据列
- 主/备/不建议方案明确

## Case 5: Selection - 候选能力接近，比较维护风险
输入：评估两个图片组件方案，要求考虑 API 注释/命名质量
期望：
- 使用 `get_component_api` 作为主要证据
- 可选使用 `audit_component_api_quality` 辅助风险判断
- 不把审计结果当作唯一结论

## Case 6: Selection - 建议是否新增组件
输入：先评估是否需要新增一个骨架屏组件
期望：
- 多轮检索后再判断是否缺失能力
- 若建议新建，必须写“已检索范围 + 缺失点 + 边界”

## Case 7: Migration - URLSession + 自定义缓存迁移
输入：将 URLSession + 自定义缓存迁移到基础组件
期望：
- 有旧->新映射表
- 有分批替换计划
- 有验证与回滚策略

## Case 8: Migration - 弹窗/Toast 平行封装迁移
输入：把业务里的自定义弹窗和 Toast 统一替换成基础 UI 组件
期望：
- 使用 `find_usage_example` 查已有接入方式（推荐）
- 给出批次划分与风险等级
- 不建议一次性全量替换

## Case 9: Migration - 无完全匹配组件
输入：迁移一个半定制化缓存策略到基础组件体系
期望：
- 允许“接近组件 + 薄适配层”方案
- 明确哪些差异暂不替换
- 不新增平行基础层

## Case 10: Review - 新增自定义图片下载器（应阻塞）
输入：PR 中新增了自定义图片下载器
期望：
- 识别为重复造轮子风险
- 给出组件证据链与替换建议
- 严重级别 >= 中（通常为高）
- 默认阻塞

## Case 11: Review - 合理豁免（不应直接阻塞）
输入：PR 中暂时自定义封装，声明基础组件缺失关键能力并给后续计划
期望：
- 检查豁免信息是否完整（缺失点/范围/收敛计划）
- 结论通常为“需整改”而非直接阻塞（视证据而定）

## Case 12: Review - 绕过统一 Router
输入：审查这次改动有没有绕过统一路由组件
期望：
- 有 `search_component` + `get_component_api` 证据
- 高优先级风险能被识别
- 给出推荐替换 API 与整改动作
