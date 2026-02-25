# Functional Cases

## Case 1: Implementation
输入：实现头像圆角+缓存
期望：
- 至少 3 轮 search_component
- 有 get_component_api 证据
- 代码未出现手写重复基础能力

## Case 2: Selection
输入：做一个带分页列表和空态页面的需求评审
期望：
- 输出能力拆解
- 候选组件矩阵完整
- 主/备选方案明确

## Case 3: Migration
输入：将 URLSession + 自定义缓存迁移到基础组件
期望：
- 有旧->新映射表
- 有分批替换计划
- 有验证与回滚策略

## Case 4: Review
输入：PR 中新增了自定义图片下载器
期望：
- 识别为重复造轮子风险
- 给出组件证据与替换建议
- 严重级别 >= 中（通常应为高）
