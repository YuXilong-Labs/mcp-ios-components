# Development

## 测试与提交规则（强制）

- 修改任何代码：必须先跑完整测试集 `./tests/run_unittest.sh`，全部通过后才能提交。
- 新增/修改功能：必须同时新增或更新对应测试用例，并纳入仓库。
- 集成测试（可选）：若本机存在组件库目录，可通过设置 `IOS_PODS_DIR`/`IOS_PODS_INCLUDE` 开启更多覆盖。
- Commit message：必须清晰描述变更范围（优先 `测试：...` / `增强：...` / `修复：...`），避免含糊词。
- 提交自检：每次提交前在描述中明确写出“新增/修改的测试文件路径”，便于 review/回溯（例如 `tests/test_search_component.py`）。

## 本地命令

```bash
cd /Users/yuxilong/clawd/mcp-ios-components
./tests/run_unittest.sh

# 可选：带组件库目录跑集成覆盖
IOS_PODS_DIR=/Users/yuxilong/Desktop/code/BaiTuPods IOS_PODS_INCLUDE=BTBaseKit ./tests/run_unittest.sh
```
