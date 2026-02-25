# Skills Evals（mcp-ios-components）

用于回归验证 skills 的触发准确性、功能正确性、复用证据完整度与流程合规率（JSON 检索/多轮检索/失败恢复/输出契约）。

## 目录

- `trigger-positive.jsonl`：应触发（含边界样本）
- `trigger-negative.jsonl`：不应触发（含 iOS 干扰样本）
- `functional-cases.md`：功能与质量检查（实现/选型/迁移/审查）
- `results/*.jsonl`：评测结果回填文件
- `run_eval.py`：指标计算与门禁脚本

## 快速使用

```bash
# 1) 生成 latest.jsonl 模板（推荐，附带字段说明）
python3 skills/evals/init_latest_results.py --with-notes-hints --overwrite

# 2) 仅校验数据集格式
python3 skills/evals/run_eval.py --allow-missing-results

# 3) 生成结果模板（兼容旧方式）
python3 skills/evals/run_eval.py --init-results --results skills/evals/results/latest.jsonl

# 4) 计算指标并做门禁
python3 skills/evals/run_eval.py \
  --results skills/evals/results/latest.jsonl \
  --assert-thresholds
```

## 结果文件字段（兼容扩展）

基础字段（原有）：
- `id`: 用例 ID（对应 trigger jsonl）
- `actual_trigger`: 实际触发 skill 名，未触发填 `none`
- `evidence_complete`: 是否提供完整复用证据（search/api/class）
- `should_block` / `blocked`: 审查类用例的应阻塞与实际阻塞结果
- `notes`: 备注

新增可选字段（用于流程合规率；缺省可不填）：
- `tool_sequence_ok`: 是否遵循推荐工具顺序
- `json_search_used`: 是否使用 `search_component(format="json")`
- `search_rounds`: 搜索轮次（正样本通常应 >= 3）
- `fallback_handled`: 是否正确处理无命中/`api_only`/工具失败等回退路径
- `output_contract_ok`: 输出结构是否满足 skill 契约
- `api_only_handled`: 命中 `api_only` 场景时是否处理正确（非该场景可留空）

## 指标说明

- `trigger_accuracy`: 正样本触发准确率
- `false_trigger_rate`: 负样本误触发率
- `evidence_completeness`: 正样本复用证据完整率
- `block_miss_rate`: 审查类应阻塞问题漏检率
- `process_compliance`: 基于已回填流程字段统计的流程合规率（无数据时显示 `N/A`）

## 建议评估流程（四轮自优化）

1. Round 1（触发层）
- 先跑 trigger-positive / negative
- 目标：提升触发准确率与误触发率

2. Round 2（工作流层）
- 重点跑 `functional-cases.md`
- 回填证据完整与输出契约相关字段

3. Round 3（渐进披露与兼容）
- 检查技能触发/证据指标不退化
- 检查 `agents/openai.yaml` 与 SKILL 一致性

4. Round 4（文档闭环与最终门禁）
- 回填流程字段，观察 `process_compliance`
- 使用 `--assert-thresholds` 做最终门禁

## 通过门槛（建议）

- 触发准确率 >= 95%
- 误触发率 <= 5%
- 复用证据完整率 >= 98%
- 阻塞级问题漏检率 <= 2%
- 流程合规率 >= 90%（有流程字段数据时）
