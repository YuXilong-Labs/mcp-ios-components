# Skills Evals（mcp-ios-components）

用于回归验证 skills 的触发准确性、功能正确性与防重复造轮子效果。

## 目录

- `trigger-positive.jsonl`：应该触发
- `trigger-negative.jsonl`：不应触发
- `functional-cases.md`：功能与质量检查

## 建议评估流程

1. 先跑 trigger-positive / negative（至少各 10 条）
2. 再跑 functional cases（实现 / 选型 / 迁移 / 审查）
3. 记录指标：
   - 触发准确率
   - 误触发率
   - 复用证据完整率（有无 search/api/class 证据）
   - 重复造轮子拦截率

## 通过门槛（建议）

- 触发准确率 >= 90%
- 误触发率 <= 10%
- 复用证据完整率 >= 95%
- 阻塞级问题漏检率 <= 5%
