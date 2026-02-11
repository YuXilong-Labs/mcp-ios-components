"""Index hashing and build routines."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Callable



def compute_hash(
    pods_dir: str,
    components: set,
    *,
    access_control: dict,
    walk_dir: Callable[[str], list],
    is_source_file: Callable[[str], bool],
) -> str:
    """Compute hash from source files + mtimes + access control."""
    h = hashlib.sha256()
    h.update(f"exclude:{','.join(sorted(access_control.get('exclude_from_index', set())))}\n".encode())
    h.update(f"api_only:{','.join(sorted(access_control.get('api_only', set())))}\n".encode())
    for name in sorted(components):
        comp_dir = os.path.join(pods_dir, name)
        if not os.path.exists(comp_dir):
            continue
        files = sorted(f for f in walk_dir(comp_dir) if is_source_file(f))
        for f in files:
            full = os.path.join(comp_dir, f)
            try:
                stat = os.stat(full)
                h.update(f"{f}:{stat.st_mtime_ns}\n".encode())
            except Exception:
                pass
    return h.hexdigest()


def build_index(
    pods_dir: str,
    *,
    cache_dir: str,
    access_control: dict,
    normalize_name: Callable[[str], str],
    discover_components: Callable[..., tuple],
    compute_hash: Callable[[str, set, dict | None], str],
    parse_podspec: Callable[[str, str], dict],
    walk_dir: Callable[[str], list],
    is_source_file: Callable[[str], bool],
    extract_apis: Callable[[str, str], list],
    access_mode_full: str,
    access_mode_api_only: str,
) -> dict:
    """Build or load component index from cache."""
    components, filtered_mixup, filtered_by_policy = discover_components(
        pods_dir, return_filtered=True, access_control=access_control
    )
    api_only_entries = sorted(name for name, reason in filtered_by_policy.items() if reason.startswith("api_only"))
    excluded_entries = {
        name: reason for name, reason in filtered_by_policy.items() if reason.startswith("exclude_from_index")
    }

    print("\n[mcp-ios] ========== 组件分类 ==========" , file=sys.stderr)
    print(f"[mcp-ios] ✅ 基础组件 ({len(components)} 个):", file=sys.stderr)
    for name in sorted(components):
        print(f"    {name}", file=sys.stderr)

    print(f"\n[mcp-ios] ❌ 非基础组件 - 已过滤 ({len(filtered_mixup)} 个):", file=sys.stderr)
    for name in sorted(filtered_mixup.keys()):
        mixup_info = " | ".join(filtered_mixup[name])
        print(f"    {name}: {mixup_info}", file=sys.stderr)

    print(f"\n[mcp-ios] 🔒 访问控制 - 排除索引 ({len(excluded_entries)} 个):", file=sys.stderr)
    for name in sorted(excluded_entries.keys()):
        print(f"    {name}: {excluded_entries[name]}", file=sys.stderr)

    print(f"\n[mcp-ios] 🔐 访问控制 - API 可见模式 ({len(api_only_entries)} 个):", file=sys.stderr)
    for name in api_only_entries:
        print(f"    {name}", file=sys.stderr)
    print("[mcp-ios] ==================================\n", file=sys.stderr)

    if not components:
        print(f"[mcp-ios] 未在 {pods_dir} 发现组件", file=sys.stderr)
        return {}

    current_hash = compute_hash(pods_dir, components, access_control)
    cache_path = os.path.join(cache_dir, "index.json")

    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("hash") == current_hash:
                print(f"[mcp-ios] 使用缓存索引 ({len(cached['components'])} 个组件)", file=sys.stderr)
                return cached["components"]
        except Exception:
            pass

    print(f"[mcp-ios] 构建索引... ({len(components)} 个组件)", file=sys.stderr)
    index = {}
    for dir_name in sorted(components):
        comp_dir = os.path.join(pods_dir, dir_name)
        try:
            spec = parse_podspec(comp_dir, dir_name)
            pod_name = spec.get("pod_name") or dir_name
            entry_norm = normalize_name(dir_name)
            pod_norm = normalize_name(pod_name)
            access_mode = (
                access_mode_api_only
                if (entry_norm in access_control.get("api_only", set()) or pod_norm in access_control.get("api_only", set()))
                else access_mode_full
            )

            all_files = walk_dir(comp_dir)
            source_files = [f for f in all_files if is_source_file(f)]
            apis = []
            for f in source_files:
                apis.extend(extract_apis(os.path.join(comp_dir, f), f))

            index[pod_name] = {
                "name": pod_name,
                "dir": dir_name,
                "podspec": spec.get("podspec", ""),
                "summary": spec.get("summary", ""),
                "description": spec.get("description", ""),
                "apis": apis,
                "files": all_files,
                "source_count": len(source_files),
                "access_mode": access_mode,
            }
            print(
                f"  ✓ {pod_name} ({dir_name}): {len(apis)} APIs, {len(source_files)} 源文件, 访问={access_mode}",
                file=sys.stderr,
            )
        except Exception as e:
            print(f"  ✗ {dir_name}: {e}", file=sys.stderr)

    os.makedirs(cache_dir, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({"hash": current_hash, "components": index}, f, ensure_ascii=False)
    print(f"[mcp-ios] 索引已缓存 ({len(index)} 个组件)", file=sys.stderr)
    return index
