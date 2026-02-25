#!/usr/bin/env python3
"""
初始化 skills/evals/results/latest.jsonl，并打印字段填写说明。

相比直接调用 run_eval.py --init-results，这个脚本会：
1) 生成 latest.jsonl（支持自定义输出路径）
2) 打印字段解释与推荐回填顺序
3) 可选为 notes 字段写入按用例类型的提示
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import run_eval


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Init latest.jsonl template with field guide")
    p.add_argument(
        "--positive",
        default="skills/evals/trigger-positive.jsonl",
        help="正样本数据集",
    )
    p.add_argument(
        "--negative",
        default="skills/evals/trigger-negative.jsonl",
        help="负样本数据集",
    )
    p.add_argument(
        "--out",
        default="skills/evals/results/latest.jsonl",
        help="输出结果模板路径",
    )
    p.add_argument(
        "--overwrite",
        action="store_true",
        help="允许覆盖已存在的输出文件",
    )
    p.add_argument(
        "--with-notes-hints",
        action="store_true",
        help="在 notes 字段写入按用例类型的简短填写提示",
    )
    return p.parse_args()


def load_expected(positive: Path, negative: Path) -> dict:
    pos = run_eval.read_jsonl(positive)
    neg = run_eval.read_jsonl(negative)
    run_eval.validate_dataset(pos, ("id", "input", "expect_trigger"), "trigger-positive")
    run_eval.validate_dataset(neg, ("id", "input", "expect_trigger"), "trigger-negative")
    return run_eval.build_expected_map(pos, neg)


def add_notes_hints(out_path: Path, expected: dict) -> None:
    rows = run_eval.read_jsonl(out_path)
    for row in rows:
        cid = row.get("id", "")
        expect = expected.get(cid, {}).get("expect_trigger", "")
        if expect == "none":
            row["notes"] = "负样本：只需回填 actual_trigger（通常为 none）"
            continue

        if expect == "ios-component-review":
            row["notes"] = (
                "审查样本：回填 actual_trigger/evidence_complete；如涉及阻塞再填 should_block/blocked；"
                "建议补流程字段"
            )
        else:
            row["notes"] = (
                "正样本：回填 actual_trigger/evidence_complete；建议补 search_rounds/json_search_used/"
                "tool_sequence_ok/output_contract_ok"
            )

    run_eval.write_jsonl(out_path, rows)


def print_guide(out_path: Path) -> None:
    print(f"已生成结果模板: {out_path}")
    print("")
    print("字段说明（基础字段）")
    print("- id: 用例 ID（不要改）")
    print("- actual_trigger: 实际触发的 skill；未触发填 none")
    print("- evidence_complete: 是否提供完整复用证据（search/api/class 或替代证据）")
    print("- should_block / blocked: 审查类用例的应阻塞与实际阻塞结果（非审查可留 null）")
    print("- notes: 备注")
    print("")
    print("字段说明（流程合规字段，可选）")
    print("- tool_sequence_ok: 是否遵循推荐工具顺序")
    print('- json_search_used: 是否使用 search_component(format="json")')
    print("- search_rounds: 搜索轮次（正样本通常 >= 3）")
    print("- fallback_handled: 是否正确处理无命中 / api_only / 工具异常")
    print("- output_contract_ok: 输出结构是否满足 skill 契约")
    print("- api_only_handled: 命中 api_only 场景时是否处理正确（非该场景可留 null）")
    print("")
    print("推荐回填顺序")
    print("1. actual_trigger")
    print("2. evidence_complete")
    print("3. review 样本的 should_block / blocked")
    print("4. 流程合规字段（tool_sequence_ok/json_search_used/search_rounds/fallback_handled/output_contract_ok）")
    print("5. 特殊场景再填 api_only_handled")
    print("")
    print("统计命令")
    print(f"python3 skills/evals/run_eval.py --results {out_path}")
    print(f"python3 skills/evals/run_eval.py --results {out_path} --assert-thresholds")


def main() -> int:
    args = parse_args()
    out_path = Path(args.out)

    if out_path.exists() and not args.overwrite:
        print(f"输出文件已存在（未覆盖）: {out_path}")
        print("如需覆盖，请增加 --overwrite")
        return 1

    expected = load_expected(Path(args.positive), Path(args.negative))
    run_eval.init_results(expected, out_path)

    if args.with_notes_hints:
        add_notes_hints(out_path, expected)

    print_guide(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
