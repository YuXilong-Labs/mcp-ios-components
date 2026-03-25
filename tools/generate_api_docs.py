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
    """为单个组件生成 Markdown 文档（按类/协议聚合展示）。"""
    name = comp["name"]
    summary = comp.get("summary", "")
    description = comp.get("description", "")

    lines = [f"# {name}"]
    if summary:
        lines.append(f"\n> {summary}")
    if description:
        lines.append(f"\n{description}")

    # 统计信息
    apis = comp.get("apis", [])
    api_count = len(apis)
    source_count = comp.get("source_count", 0)
    lines.append(f"\n**API 数量：** {api_count} | **源文件数：** {source_count}")
    lines.append("\n---\n")

    if not apis:
        lines.append("*该组件未发现公开 API 声明。*")
    else:
        # 按类/协议聚合
        class_groups, enums, typedefs, standalone = _group_apis_by_class(apis)

        # 类/协议章节
        for class_name in sorted(class_groups.keys()):
            group = class_groups[class_name]
            _render_class_section(lines, class_name, group, name, ai_results)

        # 枚举章节
        if enums:
            lines.append("## 枚举类型\n")
            for enum_info in enums:
                _render_enum_section(lines, enum_info)

        # typedef 章节
        if typedefs:
            lines.append("## 类型定义\n")
            for td in typedefs:
                _render_api_entry(lines, td, name, ai_results)

        # 独立函数/其他
        if standalone:
            lines.append("## 函数与其他\n")
            for api in standalone:
                _render_api_entry(lines, api, name, ai_results)

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


def _group_apis_by_class(apis: list) -> tuple[dict, list, list, list]:
    """将 API 列表按类/协议聚合。

    返回 (class_groups, enums, typedefs, standalone)：
    - class_groups: {类名: {"definition": api|None, "categories": {cat_name: [apis]}, "members": [apis]}}
    - enums: [{"definition": api, "members": [apis]}]
    - typedefs: [api]
    - standalone: [api]（不属于任何类的独立函数等）
    """
    class_groups: dict[str, dict] = {}
    enums: list[dict] = []
    enum_map: dict[str, dict] = {}  # enum_name -> {"definition": api, "members": []}
    typedefs: list[dict] = []
    standalone: list[dict] = []

    for api in apis:
        kind = api.get("kind", "")
        host_class = api.get("host_class", "")
        category = api.get("category", "")
        enum_type = api.get("enum_type", "")

        if kind == "enum":
            enum_map[api["name"]] = {"definition": api, "members": []}
            continue

        if kind == "enum_case":
            if enum_type in enum_map:
                enum_map[enum_type]["members"].append(api)
            continue

        if kind == "typedef":
            typedefs.append(api)
            continue

        if kind in ("interface", "protocol"):
            cls_name = api["name"]
            if cls_name not in class_groups:
                class_groups[cls_name] = {"definition": None, "categories": {}, "members": []}
            if category:
                class_groups[cls_name]["categories"].setdefault(category, [])
            else:
                class_groups[cls_name]["definition"] = api
            continue

        # 有宿主类的成员
        if host_class:
            if host_class not in class_groups:
                class_groups[host_class] = {"definition": None, "categories": {}, "members": []}
            if category:
                class_groups[host_class]["categories"].setdefault(category, []).append(api)
            else:
                class_groups[host_class]["members"].append(api)
            continue

        # 独立函数
        if kind in ("func",):
            standalone.append(api)
            continue

        # 其他无宿主类的方法/属性 — 也归到独立区域
        standalone.append(api)

    enums = list(enum_map.values())
    return class_groups, enums, typedefs, standalone


def _render_class_section(lines: list, class_name: str, group: dict, comp_name: str, ai_results: dict | None):
    """渲染单个类/协议的文档章节。"""
    definition = group.get("definition")
    categories = group.get("categories", {})
    members = group.get("members", [])

    # 类标题
    if definition:
        kind_label = _kind_label(definition.get("kind", "interface"))
        deprecated_tag = _deprecated_tag(definition)
        lines.append(f"## {kind_label} `{class_name}` {deprecated_tag}\n")

        # 声明
        file_path = definition.get("file", "")
        lang = "swift" if file_path.endswith(".swift") else "objc"
        lines.append(f"```{lang}\n{definition['declaration']}\n```\n")

        # 注释
        comment = (definition.get("comment") or "").strip()
        if comment:
            abstract, discussion = _split_abstract_discussion(comment)
            lines.append(f"**{abstract}**\n")
            if discussion:
                lines.append(f"{discussion}\n")
        lines.append(f"📄 `{file_path}`\n")
    else:
        lines.append(f"## 📦 `{class_name}`\n")

    # 直属成员
    if members:
        props = [m for m in members if m.get("kind") in ("property", "var", "let")]
        methods = [m for m in members if m.get("kind") not in ("property", "var", "let")]

        if props:
            lines.append("### 属性\n")
            for p in props:
                _render_api_entry(lines, p, comp_name, ai_results, heading_level=4)

        if methods:
            lines.append("### 方法\n")
            for m in methods:
                _render_api_entry(lines, m, comp_name, ai_results, heading_level=4)

    # Category 成员
    for cat_name, cat_apis in sorted(categories.items()):
        if not cat_apis:
            continue
        cat_label = cat_name or "匿名"
        lines.append(f"### Category: {cat_label}\n")
        for api in cat_apis:
            _render_api_entry(lines, api, comp_name, ai_results, heading_level=4)

    lines.append("---\n")


def _render_enum_section(lines: list, enum_info: dict):
    """渲染枚举章节。"""
    definition = enum_info["definition"]
    members = enum_info["members"]
    deprecated_tag = _deprecated_tag(definition)

    lines.append(f"### 📦 枚举 `{definition['name']}` {deprecated_tag}\n")
    lines.append(f"```objc\n{definition['declaration']}\n```\n")

    comment = (definition.get("comment") or "").strip()
    if comment:
        abstract, discussion = _split_abstract_discussion(comment)
        lines.append(f"**{abstract}**\n")
        if discussion:
            lines.append(f"{discussion}\n")

    if members:
        lines.append("| 成员 | 说明 |")
        lines.append("|------|------|")
        for m in members:
            mc = _clean_comment(m.get("comment", "")).split("\n")[0] if m.get("comment") else "—"
            lines.append(f"| `{m['name']}` | {mc} |")
        lines.append("")

    lines.append("---\n")


def _render_api_entry(lines: list, api: dict, comp_name: str, ai_results: dict | None, heading_level: int = 4):
    """渲染单个 API 条目。"""
    kind = api.get("kind", "")
    api_name = api.get("name", "")
    declaration = api.get("declaration", "")
    comment = (api.get("comment") or "").strip()
    file_path = api.get("file", "")

    kind_label = _kind_label(kind)
    deprecated_tag = _deprecated_tag(api)
    heading = "#" * heading_level
    lines.append(f"{heading} {kind_label} `{api_name}` {deprecated_tag}\n")

    lang = "swift" if file_path.endswith(".swift") else "objc"
    lines.append(f"```{lang}\n{declaration}\n```\n")

    if comment:
        abstract, discussion = _split_abstract_discussion(comment)
        if discussion:
            lines.append(f"**{abstract}**\n")
            rest = _clean_comment("\n".join(comment.split("\n")[1:]))
            if rest:
                lines.append(f"{rest}\n")
        else:
            lines.append(f"{_clean_comment(comment)}\n")
    elif ai_results and comp_name in ai_results and api_name in ai_results[comp_name]:
        ai_text = ai_results[comp_name][api_name]
        lines.append(f"> *AI 生成*\n>\n> {_indent_blockquote(ai_text)}\n")
    else:
        lines.append("*暂无说明*\n")


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


def _deprecated_tag(api: dict) -> str:
    """从 API 记录中生成废弃标签。"""
    dep = api.get("deprecated")
    if not dep:
        return ""
    parts = ["⚠️ 已废弃"]
    if dep.get("since") and dep.get("until"):
        parts.append(f"(iOS {dep['since']}–{dep['until']})")
    if dep.get("message"):
        parts.append(f"— {dep['message']}")
    if dep.get("replacement"):
        parts.append(f"→ `{dep['replacement']}`")
    return " ".join(parts)


def _split_abstract_discussion(comment: str) -> tuple[str, str]:
    """将注释拆分为摘要（第一段）和详细讨论（后续段落）。

    摘要为注释清理后的第一个非空行，讨论为其余内容。
    """
    # 先清理注释标记
    raw_lines = comment.split("\n")
    cleaned = []
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
        cleaned.append(line)

    text = "\n".join(cleaned).strip()
    if not text:
        return "", ""

    # 按空行或首个换行拆分
    parts = text.split("\n", 1)
    abstract = parts[0].strip()
    discussion = parts[1].strip() if len(parts) > 1 else ""
    return abstract, discussion


def _kind_label(kind: str) -> str:
    """将 kind 转换为中文标签。"""
    mapping = {
        "interface": "📦 类",
        "protocol": "📋 协议",
        "class": "📦 类",
        "struct": "📦 结构体",
        "enum": "📦 枚举",
        "enum_case": "📎 枚举值",
        "method": "🔧 方法",
        "func": "🔧 函数",
        "property": "📌 属性",
        "var": "📌 变量",
        "let": "📌 常量",
        "typedef": "🏷️ 类型定义",
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
    parser.add_argument(
        "--format", default="markdown", choices=["markdown", "lark"],
        help="输出格式：markdown（默认）或 lark（飞书 DocX Block JSON）",
    )
    parser.add_argument("--upload", action="store_true", help="上传到飞书知识库（需配合 --space-id --parent-node）")
    parser.add_argument("--space-id", default="", help="飞书知识库 space_id")
    parser.add_argument("--parent-node", default="", help="飞书知识库父节点 token")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    # 参数校验
    if args.upload and not args.space_id:
        print("错误：使用 --upload 时必须指定 --space-id", file=sys.stderr)
        sys.exit(1)
    if args.upload and not args.parent_node:
        print("错误：使用 --upload 时必须指定 --parent-node", file=sys.stderr)
        sys.exit(1)
    if args.upload and args.format != "lark":
        args.format = "lark"  # --upload 隐含 --format lark

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

    # 根据格式分派
    if args.format == "lark":
        _generate_lark(index, pods_dir, output_dir, ai_results, args)
    else:
        _generate_markdown(index, pods_dir, output_dir, ai_results, args)


def _generate_markdown(
    index: dict, pods_dir: str, output_dir: str, ai_results: dict | None, args: argparse.Namespace,
) -> None:
    """Markdown 格式生成（原有逻辑）。"""
    generated = 0
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

    if not args.component:
        index_doc = generate_index_page(index)
        index_path = os.path.join(output_dir, "index.md")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(index_doc)
        logger.info("  ✓ 目录页 → %s", index_path)

    logger.info("\n完成！共生成 %d 个组件文档，输出目录: %s", generated, output_dir)


def _generate_lark(
    index: dict, pods_dir: str, output_dir: str, ai_results: dict | None, args: argparse.Namespace,
) -> None:
    """飞书 DocX 格式生成（+ 可选上传）。"""
    from tools.lark_doc_formatter import convert_component_to_blocks, convert_index_to_blocks

    # 初始化飞书客户端（仅上传时需要）
    lark_client = None
    if args.upload:
        from mcp_app.integrations.lark_client import LarkClient
        lark_client = LarkClient()

    generated = 0
    upload_results = []

    for comp in sorted(index.values(), key=lambda c: c["name"]):
        name = comp["name"]
        if args.component and name != args.component:
            continue

        blocks = convert_component_to_blocks(comp, index, pods_dir, ai_results)

        if args.upload and lark_client:
            # 上传到飞书知识库
            node = lark_client.create_wiki_node(args.space_id, args.parent_node, name)
            doc_id = node["obj_token"]
            lark_client.append_body_blocks(doc_id, doc_id, blocks)
            upload_results.append({"name": name, "node_token": node["node_token"], "obj_token": doc_id})
            logger.info("  ✓ %s → 飞书文档 %s", name, doc_id)
        else:
            # 输出 JSON 到本地
            out_path = os.path.join(output_dir, f"{name}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"component": name, "blocks": blocks}, f, ensure_ascii=False, indent=2)
            logger.info("  ✓ %s → %s", name, out_path)

        generated += 1

    # 目录页
    if not args.component:
        index_blocks = convert_index_to_blocks(index)
        if args.upload and lark_client:
            node = lark_client.create_wiki_node(args.space_id, args.parent_node, "iOS 基础库 API 文档")
            doc_id = node["obj_token"]
            lark_client.append_body_blocks(doc_id, doc_id, index_blocks)
            logger.info("  ✓ 目录页 → 飞书文档 %s", doc_id)
        else:
            index_path = os.path.join(output_dir, "index.json")
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump({"component": "_index", "blocks": index_blocks}, f, ensure_ascii=False, indent=2)
            logger.info("  ✓ 目录页 → %s", index_path)

    mode = "上传到飞书" if args.upload else f"输出目录: {output_dir}"
    logger.info("\n完成！共生成 %d 个组件文档（飞书格式），%s", generated, mode)

    if upload_results:
        logger.info("\n上传结果：")
        for r in upload_results:
            logger.info("  %s: node=%s, doc=%s", r["name"], r["node_token"], r["obj_token"])


if __name__ == "__main__":
    main()
