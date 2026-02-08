# Development

## 测试与提交规则（强制）

- 修改任何代码：必须先跑完整测试集 `./tests/run_unittest.sh`，全部通过后才能提交。
- 新增/修改功能：必须同时新增或更新对应测试用例，并纳入仓库。
- 集成测试（可选）：若本机存在组件库目录，可通过设置 `IOS_PODS_DIR`/`IOS_PODS_INCLUDE` 开启更多覆盖。

## 本地命令

```bash
cd /Users/yuxilong/clawd/mcp-ios-components
./tests/run_unittest.sh

# 可选：带组件库目录跑集成覆盖
IOS_PODS_DIR=/Users/yuxilong/Desktop/code/BaiTuPods IOS_PODS_INCLUDE=BTBaseKit ./tests/run_unittest.sh
```
