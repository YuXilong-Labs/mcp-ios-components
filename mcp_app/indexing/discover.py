"""Component discovery and file traversal."""

from __future__ import annotations

import os
import re
from typing import Callable


def discover_components(
    pods_dir: str,
    return_filtered: bool = False,
    access_control: dict | None = None,
    *,
    mixup_marker: str,
    normalize_name: Callable[[str], str],
    load_access_control_func: Callable[[], dict],
    extract_pod_name: Callable[[str, str], str],
) -> set | tuple:
    """Discover base components from podspec files."""
    components = set()
    filtered = {}
    filtered_by_policy = {}

    access = access_control or load_access_control_func()
    exclude_set = access.get("exclude_from_index", set())
    api_only_set = access.get("api_only", set())

    include_env = os.getenv("IOS_PODS_INCLUDE", "").strip()
    include_set = {x.strip() for x in include_env.split(",") if x.strip()} if include_env else set()
    include_set_lower = {x.lower() for x in include_set}

    if not os.path.exists(pods_dir):
        return (components, filtered, filtered_by_policy) if return_filtered else components

    for entry in os.listdir(pods_dir):
        if include_set and entry.lower() not in include_set_lower:
            continue
        entry_path = os.path.join(pods_dir, entry)
        if not os.path.isdir(entry_path):
            continue

        specs = [f for f in os.listdir(entry_path) if f.endswith(".podspec")]
        if not specs:
            continue

        with open(os.path.join(entry_path, specs[0]), encoding="utf-8", errors="ignore") as spec_file:
            spec_content = spec_file.read()
        pod_name = extract_pod_name(spec_content, entry)

        has_nonempty_mixup = False
        mixup_values = []

        for line in spec_content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            mixup_match = re.search(rf"((?:{mixup_marker}|BETA_{mixup_marker})\s*=\s*\[[^\]]*\])", stripped)
            if mixup_match:
                mixup_values.append(mixup_match.group(1))
                array_match = re.search(r"=\s*\[([^\]]*)\]", mixup_match.group(1))
                if array_match:
                    array_content = array_match.group(1).strip()
                    if array_content:
                        has_nonempty_mixup = True

        if not has_nonempty_mixup:
            entry_norm = normalize_name(entry)
            pod_norm = normalize_name(pod_name)
            if entry_norm in exclude_set or pod_norm in exclude_set:
                filtered_by_policy[entry] = f"exclude_from_index ({pod_name})"
            else:
                components.add(entry)
                if entry_norm in api_only_set or pod_norm in api_only_set:
                    filtered_by_policy[entry] = f"api_only ({pod_name})"
        else:
            filtered[entry] = mixup_values

    return (components, filtered, filtered_by_policy) if return_filtered else components


def walk_dir(directory: str, skip_dirs: set | None = None) -> list:
    """List all files recursively, skipping Example and hidden dirs."""
    if skip_dirs is None:
        skip_dirs = {"Example", "Examples"}
    results = []
    if not os.path.exists(directory):
        return results
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for f in files:
            results.append(os.path.relpath(os.path.join(root, f), directory))
    return results


def is_source_file(path: str) -> bool:
    return path.endswith((".swift", ".h", ".m", ".mm"))
