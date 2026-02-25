# Skills Evals（mcp-ios-components）

用于回归验证 skills 的触发准确性、功能正确性与防重复造轮子效果。

## 目录

- `trigger-positive.jsonl`：应该触发
- `trigger-negative.jsonl`：不应触发
- `functional-cases.md`：功能与质量检查

## 快速使用

```bash
# 1) 仅校验数据集格式
python3 skills/evals/run_eval.py --allow-missing-results

# 2) 生成结果模板（人工/自动填充 actual_trigger 等）
python3 skills/evals/run_eval.py --init-results --results skills/evals/results/latest.jsonl

# 3) 计算指标并做门禁
python3 skills/evals/run_eval.py \
  --results skills/evals/results/latest.jsonl \
  --assert-thresholds
```

结果文件字段说明：
- `id`: 用例 ID（对应 trigger jsonl）
- `actual_trigger`: 实际触发 skill 名，未触发填 `none`
- `evidence_complete`: 是否提供完整复用证据（search/api/class）
- `should_block` / `blocked`: 审查类用例的应阻塞与实际阻塞结果

## 建议评估流程

1. 先跑 trigger-positive / negative（至少各 10 条）
2. 再跑 functional cases（实现 / 选型 / 迁移 / 审查）
3. 回填 `results/latest.jsonl` 后跑指标门禁
4. 记录指标：
   - 触发准确率
   - 误触发率
   - 复用证据完整率（有无 search/api/class 证据）
   - 重复造轮子拦截率

## 通过门槛（建议）

- 触发准确率 >= 90%
- 误触发率 <= 10%
- 复用证据完整率 >= 95%
- 阻塞级问题漏检率 <= 5%
