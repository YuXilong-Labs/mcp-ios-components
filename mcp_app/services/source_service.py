"""Source reading and usage example services."""

from __future__ import annotations

import os


def read_source(
    *,
    index_snapshot: dict,
    pods_dir: str,
    component_name: str,
    file: str,
    start: int,
    end: int,
    max_read_lines: int,
    api_only_deny_message: str,
    is_source_file,
    get_component_from_snapshot,
    is_api_only_component,
) -> str:
    if not component_name or not component_name.strip():
        return "错误：组件名不能为空"
    if not file or not file.strip():
        return "错误：文件路径不能为空"

    if ".." in file or file.startswith("/") or ".." in component_name:
        return "错误：非法路径"

    comp = get_component_from_snapshot(index_snapshot, component_name)
    if not comp:
        return "组件不存在"
    if is_api_only_component(component_name, comp):
        return api_only_deny_message

    fn_lower = file.lower()
    match = None
    for f in comp["files"]:
        if f == file:
            match = f
            break
    if not match:
        for f in comp["files"]:
            if f.lower().endswith(fn_lower):
                match = f
                break
    if not match:
        for f in comp["files"]:
            if fn_lower in f.lower():
                match = f
                break

    if not match:
        source_files = sorted(f for f in comp["files"] if is_source_file(f))
        return "文件未找到。\n\n可用源文件:\n" + "\n".join(f"  - {f}" for f in source_files[:30])

    comp_dir = comp.get("dir") or component_name

    filepath = os.path.realpath(os.path.join(pods_dir, comp_dir, match))
    allowed_base = os.path.realpath(os.path.join(pods_dir, comp_dir))
    if not filepath.startswith(allowed_base + os.sep) and filepath != allowed_base:
        return "错误：禁止访问此路径"

    if not os.path.exists(filepath):
        return "文件不存在"

    if end <= 0:
        end = start + 50

    if end - start > max_read_lines:
        return f"错误：单次最多读取 {max_read_lines} 行"

    if start > end:
        return "错误：起始行号不能大于结束行号"

    with open(filepath, encoding="utf-8", errors="ignore") as f:
        all_lines = f.readlines()

    total = len(all_lines)
    start = max(1, start)
    end = min(end, total)

    result = [f"=== {match} [L{start}-{end}/{total}] ==="]
    for i in range(start - 1, end):
        result.append(f"{i + 1:4d}: {all_lines[i].rstrip()}")
    return "\n".join(result)


def find_usage_example(
    *,
    index_snapshot: dict,
    pods_dir: str,
    component_name: str,
    api_only_deny_message: str,
    is_source_file,
    get_component_from_snapshot,
    is_api_only_component,
) -> str:
    comp = get_component_from_snapshot(index_snapshot, component_name)
    if not comp:
        return f'"{component_name}" 不在已索引组件中。'
    if is_api_only_component(component_name, comp):
        return api_only_deny_message

    resolved_name = comp.get("name", component_name)

    import_patterns = [
        f"import {resolved_name}",
        f"@import {resolved_name}",
        f"#import <{resolved_name}/",
        f"#import \"{resolved_name}/",
    ]

    results = []
    for other_name, other_comp in index_snapshot.items():
        if other_name == resolved_name:
            continue
        other_dir = os.path.join(pods_dir, other_comp.get("dir") or other_name)
        source_files = [f for f in other_comp.get("files", []) if is_source_file(f)]

        for rel in source_files:
            full_path = os.path.join(other_dir, rel)
            try:
                with open(full_path, encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue

            if not any(p in content for p in import_patterns):
                continue

            relevant = []
            for j, line in enumerate(content.split("\n")):
                if any(p in line for p in import_patterns) or resolved_name in line:
                    relevant.append(f"  L{j + 1}: {line.strip()}")
                    if len(relevant) >= 10:
                        break

            if relevant:
                results.append(f"### {other_name}/{rel}\n" + "\n".join(relevant))

    if not results:
        return f"未在其他组件中找到 {resolved_name} 的使用示例"

    limited = results[:20]
    text = "\n\n".join(limited)
    if len(results) > 20:
        text += f"\n\n... 共 {len(results)} 处引用，仅显示前 20 处"
    return text
