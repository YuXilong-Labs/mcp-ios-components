"""飞书 DocX Block 格式转换器。

将组件索引数据转换为飞书文档 Block JSON 结构，
可直接传入 LarkClient.append_body_blocks() 上传。

Created by yuxilong on 2026/03/25
"""

from __future__ import annotations

import logging
from datetime import datetime

from mcp_app.integrations.lark_client import LANG_MAP

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Block 构建辅助函数
# ------------------------------------------------------------------


def _text_element(content: str, bold: bool = False, inline_code: bool = False) -> dict:
    """构建 text_run 元素。"""
    style = {}
    if bold:
        style["bold"] = True
    if inline_code:
        style["inline_code"] = True
    elem = {"text_run": {"content": content}}
    if style:
        elem["text_run"]["text_element_style"] = style
    return elem


def _text_block(text: str, bold: bool = False) -> dict:
    """文本块 (block_type=2)。"""
    return {
        "block_type": 2,
        "text": {
            "elements": [_text_element(text, bold=bold)],
        },
    }


def _heading_block(level: int, text: str) -> dict:
    """标题块 (block_type=3~11 对应 heading1~heading9)。"""
    level = max(1, min(level, 9))
    block_type = level + 2  # heading1=3, heading2=4, ...
    field = f"heading{level}"
    return {
        "block_type": block_type,
        field: {
            "elements": [_text_element(text)],
        },
    }


def _code_block(code: str, lang: str = "objc") -> dict:
    """代码块 (block_type=14)。"""
    lang_code = LANG_MAP.get(lang.lower(), 1)
    return {
        "block_type": 14,
        "code": {
            "elements": [_text_element(code)],
            "style": {"language": lang_code, "wrap": False},
        },
    }


def _bullet_block(text: str, bold: bool = False) -> dict:
    """无序列表块 (block_type=12)。"""
    return {
        "block_type": 12,
        "bullet": {
            "elements": [_text_element(text, bold=bold)],
        },
    }


def _quote_block(text: str) -> dict:
    """引用块 (block_type=15)。"""
    return {
        "block_type": 15,
        "quote": {
            "elements": [_text_element(text)],
        },
    }


def _divider_block() -> dict:
    """分割线块 (block_type=22)。"""
    return {"block_type": 22}


def _rich_text_block(elements: list[dict]) -> dict:
    """由多个 text_element 组成的文本块。"""
    return {
        "block_type": 2,
        "text": {"elements": elements},
    }


# ------------------------------------------------------------------
# 注释清理（复用 generate_api_docs 的逻辑）
# ------------------------------------------------------------------


def _clean_comment_lines(comment: str) -> str:
    """清理注释标记（///、/**、*/、*）。"""
    lines = []
    for line in comment.split("\n"):
        line = line.strip()
        if line.startswith("///"):
            line = line[3:].strip()
        elif line.startswith("/**"):
            line = line[3:].strip()
        elif line.startswith("*/"):
            continue
        elif line.startswith("*"):
            line = line[1:].strip()
        lines.append(line)
    return "\n".join(lines).strip()


def _split_abstract_discussion(comment: str) -> tuple[str, str]:
    """将注释拆分为摘要和详细讨论。"""
    text = _clean_comment_lines(comment)
    if not text:
        return "", ""
    parts = text.split("\n", 1)
    abstract = parts[0].strip()
    discussion = parts[1].strip() if len(parts) > 1 else ""
    return abstract, discussion


def _deprecated_text(api: dict) -> str:
    """生成废弃标注文本。"""
    dep = api.get("deprecated")
    if not dep:
        return ""
    parts = ["⚠️ 已废弃"]
    if dep.get("since") and dep.get("until"):
        parts.append(f"(iOS {dep['since']}–{dep['until']})")
    if dep.get("message"):
        parts.append(f"— {dep['message']}")
    if dep.get("replacement"):
        parts.append(f"→ {dep['replacement']}")
    return " ".join(parts)


def _lang_for_file(file_path: str) -> str:
    """根据文件后缀确定代码语言。"""
    return "swift" if file_path.endswith(".swift") else "objc"


# ------------------------------------------------------------------
# 组件 → Block 列表转换
# ------------------------------------------------------------------


def _group_apis_by_class(apis: list) -> tuple[dict, list, list, list]:
    """按类/协议聚合 API（从 generate_api_docs 复用逻辑）。"""
    # 延迟导入避免循环
    from tools.generate_api_docs import _group_apis_by_class as _group

    return _group(apis)


def convert_component_to_blocks(
    comp: dict,
    index: dict,
    pods_dir: str,
    ai_results: dict | None = None,
) -> list[dict]:
    """将单个组件数据转换为飞书 Block 列表。"""
    name = comp["name"]
    summary = comp.get("summary", "")
    description = comp.get("description", "")
    apis = comp.get("apis", [])

    blocks: list[dict] = []

    # 标题
    blocks.append(_heading_block(1, name))

    # 摘要
    if summary:
        blocks.append(_quote_block(summary))
    if description:
        blocks.append(_text_block(description))

    # 统计
    api_count = len(apis)
    source_count = comp.get("source_count", 0)
    blocks.append(_text_block(f"API 数量：{api_count} | 源文件数：{source_count}"))
    blocks.append(_divider_block())

    if not apis:
        blocks.append(_text_block("该组件未发现公开 API 声明。"))
    else:
        class_groups, enums, typedefs, standalone = _group_apis_by_class(apis)

        # 类/协议
        for class_name in sorted(class_groups.keys()):
            group = class_groups[class_name]
            _render_class_blocks(blocks, class_name, group, name, ai_results)

        # 枚举
        if enums:
            blocks.append(_heading_block(2, "枚举类型"))
            for enum_info in enums:
                _render_enum_blocks(blocks, enum_info)

        # typedef
        if typedefs:
            blocks.append(_heading_block(2, "类型定义"))
            for td in typedefs:
                _render_api_blocks(blocks, td, name, ai_results)

        # 独立函数
        if standalone:
            blocks.append(_heading_block(2, "函数与其他"))
            for api in standalone:
                _render_api_blocks(blocks, api, name, ai_results)

    # 页脚
    blocks.append(_divider_block())
    blocks.append(_text_block(f"文档自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}"))

    return blocks


def _render_class_blocks(
    blocks: list[dict],
    class_name: str,
    group: dict,
    comp_name: str,
    ai_results: dict | None,
) -> None:
    """渲染单个类/协议的 Block 列表。"""
    definition = group.get("definition")
    categories = group.get("categories", {})
    members = group.get("members", [])

    # 类标题
    if definition:
        kind = definition.get("kind", "interface")
        kind_labels = {"interface": "类", "protocol": "协议", "class": "类", "struct": "结构体"}
        label = kind_labels.get(kind, kind)
        dep = _deprecated_text(definition)
        title = f"{label} {class_name}"
        if dep:
            title += f" {dep}"
        blocks.append(_heading_block(2, title))

        # 声明
        lang = _lang_for_file(definition.get("file", ""))
        blocks.append(_code_block(definition["declaration"], lang))

        # 注释
        comment = (definition.get("comment") or "").strip()
        if comment:
            abstract, discussion = _split_abstract_discussion(comment)
            blocks.append(_text_block(abstract, bold=True))
            if discussion:
                blocks.append(_text_block(discussion))

        blocks.append(_text_block(f"📄 {definition.get('file', '')}"))
    else:
        blocks.append(_heading_block(2, f"📦 {class_name}"))

    # 直属成员
    if members:
        props = [m for m in members if m.get("kind") in ("property", "var", "let")]
        methods = [m for m in members if m.get("kind") not in ("property", "var", "let")]

        if props:
            blocks.append(_heading_block(3, "属性"))
            for p in props:
                _render_api_blocks(blocks, p, comp_name, ai_results, heading_level=4)

        if methods:
            blocks.append(_heading_block(3, "方法"))
            for m in methods:
                _render_api_blocks(blocks, m, comp_name, ai_results, heading_level=4)

    # Category 成员
    for cat_name, cat_apis in sorted(categories.items()):
        if not cat_apis:
            continue
        cat_label = cat_name or "匿名"
        blocks.append(_heading_block(3, f"Category: {cat_label}"))
        for api in cat_apis:
            _render_api_blocks(blocks, api, comp_name, ai_results, heading_level=4)

    blocks.append(_divider_block())


def _render_enum_blocks(blocks: list[dict], enum_info: dict) -> None:
    """渲染枚举章节的 Block 列表。"""
    definition = enum_info["definition"]
    members = enum_info["members"]
    dep = _deprecated_text(definition)

    title = f"枚举 {definition['name']}"
    if dep:
        title += f" {dep}"
    blocks.append(_heading_block(3, title))
    blocks.append(_code_block(definition["declaration"], "objc"))

    comment = (definition.get("comment") or "").strip()
    if comment:
        abstract, _ = _split_abstract_discussion(comment)
        blocks.append(_text_block(abstract, bold=True))

    if members:
        for m in members:
            mc = _clean_comment_lines(m.get("comment", "")).split("\n")[0] if m.get("comment") else "—"
            blocks.append(_bullet_block(f"{m['name']} — {mc}"))

    blocks.append(_divider_block())


def _render_api_blocks(
    blocks: list[dict],
    api: dict,
    comp_name: str,
    ai_results: dict | None,
    heading_level: int = 4,
) -> None:
    """渲染单个 API 条目的 Block 列表。"""
    api_name = api.get("name", "")
    declaration = api.get("declaration", "")
    comment = (api.get("comment") or "").strip()
    file_path = api.get("file", "")

    # 废弃标注
    dep = _deprecated_text(api)
    title = api_name
    if dep:
        title += f" {dep}"
    blocks.append(_heading_block(heading_level, title))

    # 声明
    lang = _lang_for_file(file_path)
    blocks.append(_code_block(declaration, lang))

    # 注释
    if comment:
        abstract, discussion = _split_abstract_discussion(comment)
        if discussion:
            blocks.append(_text_block(abstract, bold=True))
            blocks.append(_text_block(discussion))
        else:
            blocks.append(_text_block(_clean_comment_lines(comment)))
    elif ai_results and comp_name in ai_results and api_name in ai_results[comp_name]:
        ai_text = ai_results[comp_name][api_name]
        blocks.append(_quote_block(f"AI 生成：{ai_text}"))
    else:
        blocks.append(_text_block("暂无说明"))


# ------------------------------------------------------------------
# 生成索引页 Block 列表
# ------------------------------------------------------------------


def convert_index_to_blocks(components: dict) -> list[dict]:
    """生成组件目录页的 Block 列表。"""
    blocks: list[dict] = []
    blocks.append(_heading_block(1, "iOS 基础库 API 文档"))
    blocks.append(_quote_block(f"自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}，共 {len(components)} 个组件"))
    blocks.append(_heading_block(2, "组件列表"))

    for comp in sorted(components.values(), key=lambda c: c["name"]):
        name = comp["name"]
        summary = comp.get("summary", "") or "—"
        api_count = len(comp.get("apis", []))
        source_count = comp.get("source_count", 0)
        blocks.append(_bullet_block(f"{name} — {summary} (API: {api_count}, 源文件: {source_count})"))

    return blocks
