"""Query services for indexed components."""

from __future__ import annotations

import json
import re



def to_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def get_component_from_snapshot(index_snapshot: dict, component_name: str, normalize_name) -> dict | None:
    comp = index_snapshot.get(component_name)
    if comp:
        return comp

    target = normalize_name(component_name)
    if not target:
        return None

    for candidate in index_snapshot.values():
        if target in {
            normalize_name(candidate.get("name", "")),
            normalize_name(candidate.get("dir", "")),
        }:
            return candidate
    return None


def is_api_only_component(component_name: str, comp: dict | None, index_snapshot: dict, normalize_name, access_mode_api_only: str) -> bool:
    if comp is not None:
        return comp.get("access_mode") == access_mode_api_only
    found = get_component_from_snapshot(index_snapshot, component_name, normalize_name)
    return bool(found and found.get("access_mode") == access_mode_api_only)


def list_components(index_snapshot: dict) -> str:
    if not index_snapshot:
        return "暂无已索引的组件。"
    lines = []
    for comp in sorted(index_snapshot.values(), key=lambda c: c["name"]):
        lines.append(
            f"**{comp['name']}** — {comp['summary'] or '(无描述)'}\n"
            f"  APIs: {len(comp['apis'])}, 源文件: {comp['source_count']}"
        )
    return f"共 {len(index_snapshot)} 个组件:\n\n" + "\n\n".join(lines)


def search_component(
    index_snapshot: dict,
    *,
    keyword: str,
    kind: str,
    format: str,
    limit: int,
    max_keyword_len: int,
    valid_kinds: set,
    valid_formats: set,
) -> str:
    if not keyword or not keyword.strip():
        return "错误：关键词不能为空"
    if len(keyword) > max_keyword_len:
        return f"错误：关键词过长（最大 {max_keyword_len} 字符）"
    if kind and kind not in valid_kinds:
        return f"错误：无效的 kind 值，可选: {', '.join(sorted(valid_kinds))}"
    if format not in valid_formats:
        return f"错误：无效的 format 值，可选: {', '.join(sorted(valid_formats))}"

    try:
        limit = int(limit)
    except Exception:
        limit = 50
    limit = max(1, min(200, limit))

    if not index_snapshot:
        return "暂无索引数据。"

    kw = keyword.strip().lower()
    text_results = []
    json_results = []

    def add_hit(comp_name: str, api: dict | None, kind_label: str, name: str, declaration: str = "", file: str = "", line: int = 0, comment: str = ""):
        if len(json_results) >= limit:
            return
        comment_preview = ""
        if comment:
            comment_preview = comment.split("\n")[0].strip()

        if api is None:
            text_results.append(f"[组件] {comp_name} — {declaration}")
            json_results.append(
                {
                    "component": comp_name,
                    "kind": "component",
                    "name": comp_name,
                    "file": "",
                    "line": 0,
                    "declaration": declaration,
                    "comment_preview": "",
                }
            )
            return

        if comment_preview:
            text_results.append(
                f"[{comp_name}] {kind_label} **{name}**\n"
                f"  {declaration}\n"
                f"  📄 {file}:{line}\n"
                f"  💬 {comment_preview}"
            )
        else:
            text_results.append(
                f"[{comp_name}] {kind_label} **{name}**\n"
                f"  {declaration}\n"
                f"  📄 {file}:{line}"
            )

        json_results.append(
            {
                "component": comp_name,
                "kind": kind_label,
                "name": name,
                "file": file,
                "line": int(line or 0),
                "declaration": declaration,
                "comment_preview": comment_preview,
            }
        )

    for comp in index_snapshot.values():
        if len(json_results) >= limit:
            break

        if kw in comp["name"].lower():
            add_hit(comp["name"], None, "component", comp["name"], declaration=(comp.get("summary") or "(无描述)"))

        for api in comp["apis"]:
            if len(json_results) >= limit:
                break
            if kind and api["kind"] != kind:
                continue
            if kw in api["name"].lower() or kw in api["declaration"].lower() or kw in api.get("comment", "").lower():
                add_hit(
                    comp["name"],
                    api,
                    api["kind"],
                    api["name"],
                    declaration=api["declaration"],
                    file=api["file"],
                    line=api["line"],
                    comment=api.get("comment", ""),
                )

    if not json_results:
        return (
            f'未找到与 "{keyword}" 相关的结果'
            if format == "text"
            else to_json({"ok": False, "keyword": keyword, "results": [], "truncated": False, "limit": limit})
        )

    truncated = len(json_results) >= limit

    if format == "json":
        return to_json({"ok": True, "keyword": keyword, "kind": kind, "results": json_results, "truncated": truncated, "limit": limit})

    text = "\n\n".join(text_results)
    if truncated:
        text += f"\n\n... 结果较多，仅显示前 {limit} 条（可用 limit 调大，或用 format=\"json\" 做后续自动化）"
    return text


def looks_suspicious_name(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return "empty"
    if len(n) <= 2:
        return "too_short"
    if n.lower() in {"do", "run", "test", "tmp", "temp", "aaa"}:
        return "too_generic"
    if re.search(r"\d+$", n):
        return "trailing_digits"
    if "xxx" in n.lower() or "todo" in n.lower() or "fixme" in n.lower():
        return "placeholder"
    if n[0].isupper() and "_" not in n:
        return "starts_with_uppercase"
    return ""


def audit_component_api_quality(
    index_snapshot: dict,
    *,
    component_name: str,
    format: str,
    limit: int,
    valid_formats: set,
) -> str:
    if format not in valid_formats:
        return f"错误：无效的 format 值，可选: {', '.join(sorted(valid_formats))}"

    try:
        limit = int(limit)
    except Exception:
        limit = 200
    limit = max(1, min(500, limit))

    if not index_snapshot:
        return "暂无索引数据。" if format == "text" else to_json({"ok": False, "error": "empty_index"})

    if component_name:
        comp = index_snapshot.get(component_name)
        if not comp:
            available = sorted(index_snapshot.keys())
            return (
                f"组件 \"{component_name}\" 不存在。可用: {', '.join(available)}"
                if format == "text"
                else to_json({"ok": False, "error": "unknown_component", "component": component_name, "available": available})
            )
        targets = [comp]
    else:
        targets = list(index_snapshot.values())

    missing_comment = []
    suspicious_naming = []

    def add_item(dst: list, item: dict):
        if len(dst) < limit:
            dst.append(item)

    for comp in targets:
        comp_name = comp.get("name", "")
        for api in comp.get("apis", []):
            api_name = api.get("name", "")
            kind = api.get("kind", "")
            decl = api.get("declaration", "")
            file = api.get("file", "")
            line = int(api.get("line") or 0)
            comment = (api.get("comment") or "").strip()

            if not comment or len(comment) < 6:
                add_item(
                    missing_comment,
                    {
                        "component": comp_name,
                        "kind": kind,
                        "name": api_name,
                        "file": file,
                        "line": line,
                        "declaration": decl,
                    },
                )

            reason = looks_suspicious_name(api_name)
            if reason:
                add_item(
                    suspicious_naming,
                    {
                        "component": comp_name,
                        "kind": kind,
                        "name": api_name,
                        "file": file,
                        "line": line,
                        "declaration": decl,
                        "reason": reason,
                    },
                )

    payload = {
        "ok": True,
        "component": component_name or "*",
        "limit": limit,
        "rules": {
            "missing_comment": "comment 为空或长度 < 6",
            "suspicious_naming": "启发式命名检查（过短/占位符/尾随数字/首字母大写等）",
        },
        "missing_comment": missing_comment,
        "suspicious_naming": suspicious_naming,
        "counts": {
            "missing_comment": len(missing_comment),
            "suspicious_naming": len(suspicious_naming),
        },
    }

    if format == "json":
        return to_json(payload)

    lines = [
        f"审计组件: {payload['component']}",
        f"missing_comment: {payload['counts']['missing_comment']} 条（最多显示 {limit}）",
        f"suspicious_naming: {payload['counts']['suspicious_naming']} 条（最多显示 {limit}）",
        "\n提示：这是候选清单，不是强制规范；建议结合 read_source 小范围确认后再治理。",
    ]
    return "\n".join(lines)


def get_component_api(index_snapshot: dict, component_name: str, *, max_api_output: int) -> str:
    comp = index_snapshot.get(component_name)
    if not comp:
        available = ", ".join(sorted(index_snapshot.keys()))
        return f"组件 \"{component_name}\" 不存在。可用: {available}"

    if not comp["apis"]:
        return f"{component_name} 未发现公开 API 声明"

    apis_list = comp["apis"]
    truncated = False
    if len(apis_list) > max_api_output:
        apis_list = apis_list[:max_api_output]
        truncated = True

    by_file = {}
    for api in apis_list:
        by_file.setdefault(api["file"], []).append(api)

    sections = []
    if comp["summary"]:
        sections.append(f"# {comp['name']}\n\n{comp['summary']}\n{comp['description']}")

    for file, apis in sorted(by_file.items()):
        decls = []
        for a in apis:
            s = ""
            if a.get("comment"):
                s += a["comment"] + "\n"
            s += a["declaration"]
            decls.append(s)
        sections.append(f"## {file}\n\n```\n" + "\n\n".join(decls) + "\n```")

    result = "\n\n".join(sections)
    if truncated:
        result += f"\n\n... 共 {len(comp['apis'])} 个 API，仅显示前 {max_api_output} 个"
    return result


def get_class_detail(index_snapshot: dict, component_name: str, classname: str) -> str:
    comp = index_snapshot.get(component_name)
    if not comp:
        return f"组件 \"{component_name}\" 不存在。"

    apis = comp["apis"]
    definitions = [a for a in apis if a["name"] == classname and a["kind"] in ("interface", "protocol", "class", "struct", "enum")]
    methods = [a for a in apis if a["kind"] in ("method", "func") and a["name"] != classname]
    props = [a for a in apis if a["kind"] in ("property", "var", "let") and a["name"] != classname]

    if definitions:
        def_files = set(d["file"] for d in definitions)
        class_methods = [m for m in methods if m["file"] in def_files]
        class_props = [p for p in props if p["file"] in def_files]
    else:
        class_methods = []
        class_props = []

    if not definitions and not class_methods:
        return f"未找到类 '{classname}' (组件: {component_name})"

    lines = [f"=== {classname} ({component_name}) ==="]

    for d in definitions:
        comment = f"\n  💬 {d['comment'].split(chr(10))[0]}" if d.get("comment") else ""
        lines.append(f"  定义: {d['file']}:{d['line']} ({d['kind']}){comment}")

    if class_props:
        lines.append(f"\n  属性 ({len(class_props)}):")
        for p in class_props:
            comment = f"  💬 {p['comment'].split(chr(10))[0]}" if p.get("comment") else ""
            lines.append(f"    {p['name']:40} {p['file']}:{p['line']}{comment}")

    if class_methods:
        pub = [m for m in class_methods if m["file"].endswith(".h")]
        priv = [m for m in class_methods if not m["file"].endswith(".h")]
        if pub:
            lines.append(f"\n  公开方法 ({len(pub)}):")
            for m in pub:
                lines.append(f"    {m['name']:40} {m['file']}:{m['line']}")
        if priv:
            lines.append(f"\n  内部方法 ({len(priv)}):")
            for m in priv:
                lines.append(f"    {m['name']:40} {m['file']}:{m['line']}")

    return "\n".join(lines)
