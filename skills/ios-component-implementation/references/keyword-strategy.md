# 检索关键词策略（JSON-first）

## 1. 基本策略

默认使用：`search_component(format="json", limit=5)`，多轮小样本收敛。

顺序建议：
1. 语义词（中文）
2. 同义词（英文）
3. 类名/类型词
4. 动词 + 类名组合
5. 必要时 `kind` 收敛

## 2. 能力词库（示例）

### 图片
- 中文：圆角、裁剪、压缩、缩放、滤镜、缓存、预加载、下载
- 英文：corner、radius、clip、crop、resize、cache、download
- 类名：`UIImage` `UIImageView` `CALayer`

### 网络
- 中文：请求、上传、下载、重试、超时、鉴权、WebSocket
- 英文：request、http、upload、download、retry、timeout、auth
- 类名：`URLSession` `NSURLSession`

### UI
- 中文：弹窗、Toast、空态、骨架屏、刷新、分页、列表
- 英文：alert、toast、empty、skeleton、refresh、pager、list
- 类名：`UIView` `UIButton` `UITableView` `UICollectionView`

### 存储/工具
- 中文：缓存、持久化、Keychain、日期、字符串、JSON、日志
- 英文：cache、persist、store、keychain、date、string、json、log
- 类名：`NSUserDefaults` `NSString` `NSDate`

## 3. 多义词收敛示例（圆角头像）

问题：`corner` 可能命中大量 `UIView` 圆角，偏离 `UIImage` 裁剪需求。

收敛步骤：
1. `圆角`
2. `corner`
3. `UIImage`
4. `clip`
5. `avatar`
6. 必要时 `kind="method"`

## 4. 何时扩大 `limit`

仅在以下情况扩大到 `10-20`：
- 小 `limit` 下命中太少且疑似漏掉关键候选
- 组件命名混乱，需要更大样本观察前缀/模式
- 需要做候选对比矩阵

不建议一开始就 `limit=50+`。
