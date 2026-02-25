#!/usr/bin/env python3
"""
Skills eval runner for mcp-ios-components.

用途：
1) 校验 eval 数据集完整性
2) 基于人工/自动回填结果计算核心指标
3) 可按阈值返回非 0（用于 CI 门禁）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class Metrics:
    trigger_accuracy: float
    false_trigger_rate: float
    evidence_completeness: float
    block_miss_rate: float
    process_compliance: float | None


def read_jsonl(path: Path) -> List[dict]:
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    rows: List[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{i} JSON 解析失败: {e}") from e
    return rows


def write_jsonl(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def validate_dataset(rows: List[dict], required_keys: Tuple[str, ...], name: str) -> None:
    ids = set()
    for idx, row in enumerate(rows, 1):
        for k in required_keys:
            if k not in row:
                raise ValueError(f"{name} 第 {idx} 行缺少字段: {k}")
        if row["id"] in ids:
            raise ValueError(f"{name} 出现重复 id: {row['id']}")
        ids.add(row["id"])


def build_expected_map(pos_rows: List[dict], neg_rows: List[dict]) -> Dict[str, dict]:
    expected: Dict[str, dict] = {}
    for r in pos_rows + neg_rows:
        expected[r["id"]] = {
            "expect_trigger": r["expect_trigger"],
            "input": r.get("input", ""),
        }
    return expected


def init_results(expected: Dict[str, dict], out_path: Path) -> None:
    rows: List[dict] = []
    for cid, v in expected.items():
        rows.append(
            {
                "id": cid,
                "actual_trigger": "",
                "evidence_complete": None,
                "should_block": None,
                "blocked": None,
                "tool_sequence_ok": None,
                "json_search_used": None,
                "search_rounds": None,
                "fallback_handled": None,
                "output_contract_ok": None,
                "api_only_handled": None,
                "notes": "",
            }
        )
    write_jsonl(out_path, rows)


def compute_metrics(expected: Dict[str, dict], results: List[dict]) -> Metrics:
    result_map = {r.get("id"): r for r in results if r.get("id")}

    pos_ids = [k for k, v in expected.items() if v["expect_trigger"] != "none"]
    neg_ids = [k for k, v in expected.items() if v["expect_trigger"] == "none"]

    # trigger accuracy（正样本命中率）
    pos_total = len(pos_ids)
    pos_hit = 0
    for cid in pos_ids:
        actual = (result_map.get(cid, {}).get("actual_trigger") or "").strip()
        expect = expected[cid]["expect_trigger"]
        if actual == expect:
            pos_hit += 1
    trigger_accuracy = (pos_hit / pos_total) if pos_total else 0.0

    # false trigger rate（负样本误触发率）
    neg_total = len(neg_ids)
    neg_false = 0
    for cid in neg_ids:
        actual = (result_map.get(cid, {}).get("actual_trigger") or "").strip()
        if actual and actual != "none":
            neg_false += 1
    false_trigger_rate = (neg_false / neg_total) if neg_total else 0.0

    # evidence completeness
    evidence_values = []
    for cid in pos_ids:
        val = result_map.get(cid, {}).get("evidence_complete")
        if isinstance(val, bool):
            evidence_values.append(val)
    evidence_completeness = (
        sum(1 for v in evidence_values if v) / len(evidence_values)
        if evidence_values
        else 0.0
    )

    # block miss rate
    should_block = []
    miss_count = 0
    for r in results:
        sb = r.get("should_block")
        b = r.get("blocked")
        if isinstance(sb, bool):
            if sb:
                should_block.append(r)
                if b is not True:
                    miss_count += 1
    block_miss_rate = (miss_count / len(should_block)) if should_block else 0.0

    # process compliance（按已回填流程字段统计，字段级通过率）
    process_checks: List[bool] = []
    for cid in pos_ids:
        row = result_map.get(cid, {})

        for key in (
            "tool_sequence_ok",
            "json_search_used",
            "fallback_handled",
            "output_contract_ok",
            "api_only_handled",
        ):
            val = row.get(key)
            if isinstance(val, bool):
                process_checks.append(val)

        rounds = row.get("search_rounds")
        if isinstance(rounds, int):
            process_checks.append(rounds >= 3)

    process_compliance = (
        sum(1 for ok in process_checks if ok) / len(process_checks)
        if process_checks
        else None
    )

    return Metrics(
        trigger_accuracy=trigger_accuracy,
        false_trigger_rate=false_trigger_rate,
        evidence_completeness=evidence_completeness,
        block_miss_rate=block_miss_rate,
        process_compliance=process_compliance,
    )


def print_report(metrics: Metrics) -> None:
    print("=== Skills Eval Report ===")
    print(f"trigger_accuracy      : {metrics.trigger_accuracy:.2%}")
    print(f"false_trigger_rate    : {metrics.false_trigger_rate:.2%}")
    print(f"evidence_completeness : {metrics.evidence_completeness:.2%}")
    print(f"block_miss_rate       : {metrics.block_miss_rate:.2%}")
    if metrics.process_compliance is None:
        print("process_compliance    : N/A (未回填流程字段)")
    else:
        print(f"process_compliance    : {metrics.process_compliance:.2%}")


def enforce_thresholds(metrics: Metrics, args: argparse.Namespace) -> int:
    failed: List[str] = []

    if metrics.trigger_accuracy < args.min_trigger_accuracy:
        failed.append(
            f"trigger_accuracy {metrics.trigger_accuracy:.2%} < {args.min_trigger_accuracy:.2%}"
        )
    if metrics.false_trigger_rate > args.max_false_trigger_rate:
        failed.append(
            f"false_trigger_rate {metrics.false_trigger_rate:.2%} > {args.max_false_trigger_rate:.2%}"
        )
    if metrics.evidence_completeness < args.min_evidence_completeness:
        failed.append(
            f"evidence_completeness {metrics.evidence_completeness:.2%} < {args.min_evidence_completeness:.2%}"
        )
    if metrics.block_miss_rate > args.max_block_miss_rate:
        failed.append(
            f"block_miss_rate {metrics.block_miss_rate:.2%} > {args.max_block_miss_rate:.2%}"
        )
    if (
        metrics.process_compliance is not None
        and metrics.process_compliance < args.min_process_compliance
    ):
        failed.append(
            "process_compliance "
            f"{metrics.process_compliance:.2%} < {args.min_process_compliance:.2%}"
        )

    if failed:
        print("\n[FAIL] 指标未达标：")
        for item in failed:
            print(f"- {item}")
        return 1

    if metrics.process_compliance is None:
        print("\n[WARN] 未回填流程字段，跳过 process_compliance 阈值校验")
    print("\n[PASS] 指标达标")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run skills eval metrics")
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
        "--results",
        default="skills/evals/results/latest.jsonl",
        help="评测结果文件（需包含 actual_trigger 等字段）",
    )
    p.add_argument(
        "--init-results",
        action="store_true",
        help="根据数据集初始化结果模板文件",
    )
    p.add_argument(
        "--allow-missing-results",
        action="store_true",
        help="结果文件缺失时不报错（用于仅做数据校验）",
    )
    p.add_argument(
        "--assert-thresholds",
        action="store_true",
        help="按阈值校验并以非0退出",
    )

    # thresholds
    p.add_argument("--min-trigger-accuracy", type=float, default=0.90)
    p.add_argument("--max-false-trigger-rate", type=float, default=0.10)
    p.add_argument("--min-evidence-completeness", type=float, default=0.95)
    p.add_argument("--max-block-miss-rate", type=float, default=0.05)
    p.add_argument("--min-process-compliance", type=float, default=0.90)

    return p.parse_args()


def main() -> int:
    args = parse_args()
    pos_path = Path(args.positive)
    neg_path = Path(args.negative)
    res_path = Path(args.results)

    pos = read_jsonl(pos_path)
    neg = read_jsonl(neg_path)
    validate_dataset(pos, ("id", "input", "expect_trigger"), "trigger-positive")
    validate_dataset(neg, ("id", "input", "expect_trigger"), "trigger-negative")

    expected = build_expected_map(pos, neg)

    if args.init_results:
        init_results(expected, res_path)
        print(f"已生成结果模板: {res_path}")
        return 0

    if not res_path.exists():
        if args.allow_missing_results:
            print(f"结果文件不存在，跳过指标计算: {res_path}")
            return 0
        print(f"结果文件不存在: {res_path}")
        return 1

    results = read_jsonl(res_path)
    metrics = compute_metrics(expected, results)
    print_report(metrics)

    if args.assert_thresholds:
        return enforce_thresholds(metrics, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
