#!/usr/bin/env python3
"""iOS 基础库 API 文档自动生成脚本。

从 mcp-ios-components 索引缓存读取组件数据，
生成包含 API 列表、注释说明、调用示例的 Markdown 文档。

Created by yuxilong on 2026/03/25

用法:
    python tools/generate_api_docs.py --pods-dir /path/to/Pods
    python tools/generate_api_docs.py --pods-dir /path/to/Pods --ai-fill
    python tools/generate_api_docs.py --pods-dir /path/to/Pods --component BTBaseKit
    python tools/generate_api_docs.py --pods-dir /path/to/Pods --ai-fill --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logger = logging.getLogger(__name__)


class IndexLoadError(RuntimeError):
    """索引加载失败。"""


def load_index(cache_path: str) -> dict:
    """加载索引缓存。"""
    if not os.path.exists(cache_path):
        raise IndexLoadError(
            f"索引缓存不存在: {cache_path}\n"
            "请先运行 MCP Server 构建索引（python mcp_server.py /path/to/pods）"
        )

    with open(cache_path, encoding="utf-8") as f:
        data = json.load(f)

    components = data.get("components", {})
    if not components:
        raise IndexLoadError("索引中没有组件数据")

    logger.info("已加载索引：%d 个组件", len(components))
    return components


def is_source_file(f: str) -> bool:
    """判断是否为源文件。"""
    return f.endswith((".h", ".m", ".mm", ".swift"))


def find_usage_examples(
    index: dict, component_name: str, pods_dir: str, max_files: int = 5, max_lines: int = 10
) -> list[dict]:
    """查找其他组件对目标组件的使用示例。"""
    comp = index.get(component_name)
    if not comp:
        return []

    resolved_name = comp.get("name", component_name)
    import_patterns = [
        f"import {resolved_name}",
        f"@import {resolved_name}",
        f"#import <{resolved_name}/",
        f'#import "{resolved_name}/',
    ]

    results = []
    for other_name, other_comp in index.items():
        if other_name == component_name or other_name == resolved_name:
            continue
        if len(results) >= max_files:
            break

        other_dir = os.path.join(pods_dir, other_comp.get("dir") or other_name)
        source_files = [f for f in other_comp.get("files", []) if is_source_file(f)]

        for rel in source_files:
            if len(results) >= max_files:
                break
            full_path = os.path.join(other_dir, rel)
            try:
                with open(full_path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue

            if not any(p in content for p in import_patterns):
                continue

            relevant = []
            for j, line in enumerate(content.split("\n")):
                if any(p in line for p in import_patterns) or resolved_name in line:
                    relevant.append(f"L{j + 1}: {line.strip()}")
                    if len(relevant) >= max_lines:
                        break

            if relevant:
                results.append({
                    "source": f"{other_name}/{rel}",
                    "lines": relevant,
                })

    return results


def generate_component_doc(
    comp: dict,
    index: dict,
    pods_dir: str,
    ai_results: dict | None = None,
) -> str:
    """为单个组件生成 Markdown 文档。"""
    name = comp["name"]
    summary = comp.get("summary", "")
    description = comp.get("description", "")

    lines = [f"# {name}"]
    if summary:
        lines.append(f"\n> {summary}")
    if description:
        lines.append(f"\n{description}")

    # 统计信息
    api_count = len(comp.get("apis", []))
    source_count = comp.get("source_count", 0)
    lines.append(f"\n**API 数量：** {api_count} | **源文件数：** {source_count}")
    lines.append("\n---\n")

    # 按文件分组 API
    apis = comp.get("apis", [])
    if not apis:
        lines.append("*该组件未发现公开 API 声明。*")
    else:
        lines.append("## API 列表\n")
        by_file: dict[str, list] = {}
        for api in apis:
            file_key = api.get("file", "<unknown>")
            by_file.setdefault(file_key, []).append(api)

        for file_path in sorted(by_file.keys()):
            file_apis = by_file[file_path]
            lines.append(f"### 📄 {file_path}\n")

            for api in file_apis:
                kind = api.get("kind", "")
                api_name = api.get("name", "")
                declaration = api.get("declaration", "")
                comment = (api.get("comment") or "").strip()

                # 标题：kind + name
                kind_label = _kind_label(kind)
                lines.append(f"#### {kind_label} `{api_name}`\n")

                # 声明代码块
                lang = "swift" if file_path.endswith(".swift") else "objc"
                lines.append(f"```{lang}\n{declaration}\n```\n")

                # 注释/说明
                if comment:
                    cleaned = _clean_comment(comment)
                    lines.append(f"{cleaned}\n")
                elif ai_results and name in ai_results and api_name in ai_results[name]:
                    ai_text = ai_results[name][api_name]
                    lines.append(f"> *AI 生成*\n>\n> {_indent_blockquote(ai_text)}\n")
                else:
                    lines.append("*暂无说明*\n")

                lines.append("---\n")

    # 调用示例
    examples = find_usage_examples(index, name, pods_dir)
    if examples:
        lines.append("\n## 调用示例\n")
        for ex in examples:
            lines.append(f"### 来自 `{ex['source']}`\n")
            lines.append("```")
            for line in ex["lines"]:
                lines.append(line)
            lines.append("```\n")

    # 页脚
    lines.append(f"\n---\n*文档自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return "\n".join(lines)


def generate_index_page(components: dict) -> str:
    """生成组件目录页。"""
    lines = [
        "# iOS 基础库 API 文档\n",
        f"> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}，共 {len(components)} 个组件\n",
        "## 组件列表\n",
        "| 组件名 | 描述 | API 数量 | 源文件数 |",
        "|--------|------|----------|----------|",
    ]

    for comp in sorted(components.values(), key=lambda c: c["name"]):
        name = comp["name"]
        summary = comp.get("summary", "") or "—"
        api_count = len(comp.get("apis", []))
        source_count = comp.get("source_count", 0)
        lines.append(f"| [{name}](./{name}.md) | {summary} | {api_count} | {source_count} |")

    return "\n".join(lines)


def _kind_label(kind: str) -> str:
    """将 kind 转换为中文标签。"""
    mapping = {
        "interface": "📦 类",
        "protocol": "📋 协议",
        "class": "📦 类",
        "struct": "📦 结构体",
        "enum": "📦 枚举",
        "method": "🔧 方法",
        "func": "🔧 函数",
        "property": "📌 属性",
        "var": "📌 变量",
        "let": "📌 常量",
        "typealias": "🏷️ 类型别名",
        "init": "🔧 初始化",
    }
    return mapping.get(kind, f"📎 {kind}")


def _clean_comment(comment: str) -> str:
    """清理注释中的 /// 和 /** */ 标记，并将 @param/@return 转换为 Markdown 格式。"""
    raw_lines = comment.split("\n")
    cleaned = []
    params = []
    return_desc = ""

    for line in raw_lines:
        line = line.strip()
        if line.startswith("///"):
            line = line[3:].strip()
        elif line.startswith("/**"):
            line = line[3:].strip()
        elif line.startswith("*/"):
            continue
        elif line.startswith("*"):
            line = line[1:].strip()

        # 解析 @param 和 @return
        if line.startswith("@param "):
            rest = line[7:].strip()
            parts = rest.split(None, 1)
            if len(parts) == 2:
                params.append(f"- `{parts[0]}` — {parts[1]}")
            elif parts:
                params.append(f"- `{parts[0]}`")
        elif line.startswith("@return ") or line.startswith("@returns "):
            parts = line.split(None, 1)
            return_desc = parts[1] if len(parts) > 1 else ""
        elif line:
            cleaned.append(line)

    result = "\n".join(cleaned).strip()
    if params:
        result += "\n\n**参数：**\n" + "\n".join(params)
    if return_desc:
        result += f"\n\n**返回值：** {return_desc}"
    return result


def _indent_blockquote(text: str) -> str:
    """将多行文本格式化为 blockquote 内的内容。"""
    return "\n> ".join(text.split("\n"))


def main():
    parser = argparse.ArgumentParser(description="iOS 基础库 API 文档自动生成")
    parser.add_argument("--index-cache", default="", help="索引缓存 JSON 路径（默认自动检测）")
    parser.add_argument("--pods-dir", default="", help="Pods 源码目录")
    parser.add_argument("--output-dir", default="docs/api", help="输出目录（默认 docs/api/）")
    parser.add_argument("--ai-fill", action="store_true", help="启用 AI 补全缺注释的 API")
    parser.add_argument("--dry-run", action="store_true", help="仅统计缺注释数量，不生成文档")
    parser.add_argument("--component", default="", help="指定单个组件名（可选）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    # 确定索引缓存路径
    cache_path = args.index_cache
    if not cache_path:
        cache_path = os.path.join(PROJECT_ROOT, ".cache", "index.json")

    # 加载索引
    try:
        index = load_index(cache_path)
    except IndexLoadError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)

    # AI 补全
    ai_results = None
    if args.ai_fill or args.dry_run:
        from tools.ai_doc_filler import fill_missing_comments

        # --ai-fill 需要 pods-dir，--dry-run 不需要
        if args.ai_fill and not args.pods_dir:
            print("错误：使用 --ai-fill 时必须指定 --pods-dir", file=sys.stderr)
            sys.exit(1)

        result = fill_missing_comments(
            index, args.pods_dir or "", component_name=args.component, dry_run=args.dry_run
        )

        if args.dry_run:
            print("\n=== AI 补全预估 ===")
            print(f"总计需要补全: {result['total']} 个 API")
            print("\n按组件分布:")
            for name, count in sorted(result["by_component"].items()):
                print(f"  {name}: {count}")
            return

        ai_results = result.get("results", {})
        if ai_results:
            total = sum(len(v) for v in ai_results.values())
            logger.info("AI 补全完成: %d 个 API", total)

    # 确定输出目录
    output_dir = args.output_dir
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(PROJECT_ROOT, output_dir)
    os.makedirs(output_dir, exist_ok=True)

    pods_dir = args.pods_dir or ""
    generated = 0

    # 生成每个组件的文档
    for comp in sorted(index.values(), key=lambda c: c["name"]):
        name = comp["name"]
        if args.component and name != args.component:
            continue

        doc = generate_component_doc(comp, index, pods_dir, ai_results)
        out_path = os.path.join(output_dir, f"{name}.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(doc)
        generated += 1
        logger.info("  ✓ %s → %s", name, out_path)

    # 生成目录页
    if not args.component:
        index_doc = generate_index_page(index)
        index_path = os.path.join(output_dir, "index.md")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_doc)
        logger.info("  ✓ 目录页 → %s", index_path)

    logger.info("\n完成！共生成 %d 个组件文档，输出目录: %s", generated, output_dir)


if __name__ == "__main__":
    main()
