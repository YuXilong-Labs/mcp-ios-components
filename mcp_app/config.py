"""Configuration helpers."""

from __future__ import annotations

import json
import os
import re
import sys

from .models import DEFAULT_EXCLUDE_COMPONENTS


def get_app_base_dir() -> str:
    """Get application base directory (project root)."""
    env_base = os.environ.get("IOS_PODS_APP_BASE_DIR", "").strip()
    if env_base:
        return os.path.abspath(env_base)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resolve_config_path(config_path: str, default_config_file: str) -> str:
    """Resolve config path relative to app base dir."""
    if not config_path:
        config_path = default_config_file
    if os.path.isabs(config_path):
        return config_path
    return os.path.join(get_app_base_dir(), config_path)


def normalize_component_name(name: str) -> str:
    """Normalize component identifier by strip + lowercase."""
    return (name or "").strip().lower()


def extract_pod_name_from_podspec_content(content: str, fallback: str) -> str:
    """Extract pod name from podspec text."""
    m = re.search(r"\.name\s*=\s*['\"](.+?)['\"]", content)
    return m.group(1).strip() if m else fallback


def load_components_config(config_path: str) -> dict:
    """Load components config from YAML or JSON."""
    if not os.path.exists(config_path):
        return {}

    with open(config_path, encoding="utf-8") as f:
        content = f.read()

    if config_path.endswith(".yaml") or config_path.endswith(".yml"):
        try:
            import yaml

            return yaml.safe_load(content) or {}
        except ImportError:
            print("[mcp-ios] ⚠️ 需要安装 pyyaml: pip install pyyaml", file=sys.stderr)
            return {}
    return json.loads(content)


def load_access_control(default_config_file: str, config_path: str = "") -> dict:
    """Load access control section from components config."""
    resolved = resolve_config_path(config_path, default_config_file)
    config = load_components_config(resolved)

    exclude_set = set(DEFAULT_EXCLUDE_COMPONENTS)
    api_only_set = set()
    access = config.get("access_control", {}) if isinstance(config, dict) else {}

    if isinstance(access, dict):
        exclude_items = access.get("exclude_from_index", [])
        api_only_items = access.get("api_only", [])

        if isinstance(exclude_items, list):
            for item in exclude_items:
                norm = normalize_component_name(str(item))
                if norm:
                    exclude_set.add(norm)

        if isinstance(api_only_items, list):
            for item in api_only_items:
                norm = normalize_component_name(str(item))
                if norm:
                    api_only_set.add(norm)

    # exclude has higher priority than api_only
    api_only_set -= exclude_set

    return {
        "exclude_from_index": exclude_set,
        "api_only": api_only_set,
        "config_path": resolved,
    }
