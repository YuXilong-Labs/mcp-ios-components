# 检索关键词策略

## 1. 能力词
- 网络：请求、上传、下载、重试、超时、鉴权
- UI：弹窗、Toast、列表、空态、骨架屏、刷新
- 图片：圆角、裁剪、压缩、缓存、预加载
- 路由：跳转、deep link、open url、参数传递
- 存储：缓存、持久化、Keychain、UserDefaults
- 埋点：曝光、点击、事件、上报

## 2. 英文同义词
- 请求 request / http / api
- 圆角 corner / radius / clip / mask
- 缓存 cache / store / persist
- 跳转 route / router / navigate

## 3. 类名词
- UIImage / UIImageView / UIView / UIButton / URLSession

## 4. 收敛策略
1) 先 broad（语义）
2) 再 narrow（类名 + 动词）
3) 最后文件级验证（`read_source` 小范围）
