---
name: ios-component-implementation
description: 基于 mcp-ios-components 执行 iOS 功能实现，自动完成组件检索、选型、代码落地与自检。用于用户提出“实现页面/功能/接口”“按组件化规范开发”“避免重复造轮子”等请求。
metadata:
  author: mcp-ios-components
  version: 1.0.0
  mcp-server: ios-components
  category: ios-engineering
---

# iOS 组件化实现工作流

## 目标

将“直接写代码”改为“先检索复用，再实现”，默认避免重复造轮子。

## 强制执行规则

1. 任何实现前，先调用 `search_component` 至少 3 轮（中英关键词 + 类名）
2. 命中候选后，必须调用 `get_component_api`
3. 关键类必须调用 `get_class_detail` 或 `read_source` 做签名确认
4. 找不到组件时，需明确说明“已检索关键词列表 + 未命中原因”，再给出最小新实现

## 标准流程

### Step 1: 拆解需求

把用户需求拆成能力清单：网络、UI、路由、图片、存储、埋点、工具方法。

### Step 2: 组件检索（多轮）

每类能力最少 3 轮检索：

- 语义关键词：如“圆角、缓存、请求、路由、埋点”
- 英文同义词：corner/cache/request/router/track
- 类名关键词：UIImage/UIView/URLSession/UIButton 等

必要时先调用：
- `get_tool_docs(tool_name="search_component", format="json")`

### Step 3: 选型确认

对命中候选输出“选型说明”：

- 组件名
- 推荐 API
- 选择理由
- 不选其他候选的原因

### Step 4: 落地实现

只用已确认的组件 API 编写代码。禁止再手搓同类基础能力。

### Step 5: 实现后自检

至少检查：

- 是否绕过基础组件
- 是否新增重复工具类
- 是否缺失错误处理或边界处理
- 是否有可替换为组件 API 的代码

## 输出格式（默认）

1. 检索摘要（关键词 + 命中组件）
2. 选型决策（推荐 API）
3. 代码实现
4. 自检结论（是否仍存在重复造轮子风险）

## 常见问题

### 问题：搜索结果很多但不确定

处理：缩小到类名和动词组合继续搜，例如：
- UIImage + clip
- UIView + skeleton
- request + upload

### 问题：只有相似能力，没有完全匹配

处理：优先复用最接近组件，补小适配层，不直接重写整套能力。

## 示例

用户：实现头像圆角并缓存加载

动作：
1. 检索关键词：圆角/corner/UIImage/cache
2. 确认 `XXImageKit` 相关 API
3. 使用现有扩展方法实现
4. 自检确保没有出现 `UIGraphicsBeginImageContext` 的重复实现
