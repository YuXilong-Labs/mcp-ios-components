#!/usr/bin/env python3
"""MCP Server: iOS CocoaPods Component Index."""

from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import os
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from typing import Optional

from mcp.server.fastmcp import FastMCP
try:
    from mcp.server.transport_security import TransportSecuritySettings
except Exception:  # pragma: no cover - older mcp versions / import issues
    TransportSecuritySettings = None  # type: ignore[assignment]

from . import config as app_config
from .indexing import builder as index_builder
from .indexing import discover as index_discover
from .indexing import parser as index_parser
from .integrations import auth_store
from .integrations import git_client
from .integrations import gitlab_client
from .models import (
    ACCESS_MODE_API_ONLY,
    ACCESS_MODE_FULL,
    API_ONLY_DENY_MESSAGE,
    DEFAULT_EXCLUDE_COMPONENTS,
    MAX_API_OUTPUT,
    MAX_KEYWORD_LEN,
    MAX_READ_LINES,
    VALID_FORMATS,
    VALID_KINDS,
)
from .services import query_service, source_service, sync_service, update_service

# ============================================================
# 配置
# ============================================================

APP_BASE_DIR = app_config.get_app_base_dir()
DEFAULT_PODS_DIR = os.environ.get("IOS_PODS_DIR", os.getcwd())
CACHE_DIR = os.environ.get("IOS_PODS_CACHE_DIR", os.path.join(APP_BASE_DIR, ".cache"))
KEYS_FILE = os.environ.get("IOS_PODS_KEYS_FILE", os.path.join(APP_BASE_DIR, ".api-keys"))
MIXUP_MARKER = os.environ.get("IOS_PODS_MIXUP_MARKER", "SUPPORT_MIXUP")
WEBHOOK_SECRET = os.environ.get("IOS_PODS_WEBHOOK_SECRET", "")
WATCH_INTERVAL = int(os.environ.get("IOS_PODS_WATCH_INTERVAL", "0"))
COMPONENTS_CONFIG_FILE = os.environ.get("IOS_PODS_CONFIG", "components.yaml")
GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")

# 运行时状态
PODS_DIR = DEFAULT_PODS_DIR
INDEX: dict = {}
INDEX_LOCK = threading.Lock()
LAST_HASH: str = ""
WATCH_LOG: list = []
WATCH_LOG_MAX = 50
REINDEX_LOCK = threading.Lock()


# ============================================================
# 配置相关函数
# ============================================================

def _resolve_config_path(config_path: str) -> str:
    return app_config.resolve_config_path(config_path, COMPONENTS_CONFIG_FILE)


def normalize_component_name(name: str) -> str:
    return app_config.normalize_component_name(name)


def _extract_pod_name_from_podspec_content(content: str, fallback: str) -> str:
    return app_config.extract_pod_name_from_podspec_content(content, fallback)


def load_components_config(config_path: str) -> dict:
    return app_config.load_components_config(config_path)


def load_access_control(config_path: str = "") -> dict:
    resolved = _resolve_config_path(config_path)
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

    api_only_set -= exclude_set

    return {
        "exclude_from_index": exclude_set,
        "api_only": api_only_set,
        "config_path": resolved,
    }


mcp = FastMCP(
    "ios-components",
    instructions="""iOS 组件库代码索引 — 复用优先，拒绝重复造轮子。

⚠️ 【强制检查规则】
实现以下功能前，必须先调用 search_component 检查现有组件：
- 图片处理（缩放、裁剪、圆角、滤镜、缓存、下载）
- 网络请求（HTTP、WebSocket、上传、下载）
- UI 组件（弹窗、Toast、刷新、空态、骨架屏）
- 数据存储（缓存、数据库、文件、Keychain）
- 工具类（日期、字符串、加密、JSON、日志）
- 基础扩展（UIView、UIImage、NSString、NSArray 等分类）

🔍 【搜索策略】
1. 先用中文关键词搜：search_component("图片圆角")
2. 再用英文/类名搜：search_component("corner radius") 或 search_component("UIImage")
3. 搜索结果为空不代表没有，尝试同义词：缓存→cache→store→persist

📋 【标准工作流】
search_component(关键词) → 发现候选组件 →
get_component_api(组件名) → 查看完整 API →
get_class_detail(组件名, 类名) → 查看具体类 →
read_source(组件名, 文件, 起始行, 结束行) → 查看实现细节

💡 【使用示例查找】
find_usage_example(组件名) — 查看其他组件如何 import 和使用，学习最佳实践

🎯 【优先级规则】
搜索到多个方法时，按以下顺序选择：
1. Category/Extension 方法（如 UIButton+XX）— 最自然，接近原生 API
2. Protocol/基类方法 — 统一接口
3. Helper/Utility 类 — 最后选择，仅当无分类方法时使用

❌ 【禁止行为】
- 未搜索就直接写 UIImage 圆角、缩放等常见功能
- 自己写网络请求封装而不检查现有网络组件
- 复制粘贴 Stack Overflow 代码而不查组件库

✅ 【正确示范】
用户说"给图片加圆角" →
你先调用 search_component("圆角") 或 search_component("UIImage corner") →
发现 UIImage+CornerRadius 分类 →
告诉用户直接用：[image xx_imageWithCornerRadius:8]""",
)


# ============================================================
# 组件发现 & 索引构建
# ============================================================

def discover_components(pods_dir: str, return_filtered: bool = False, access_control: dict | None = None) -> set | tuple:
    return index_discover.discover_components(
        pods_dir,
        return_filtered=return_filtered,
        access_control=access_control,
        mixup_marker=MIXUP_MARKER,
        normalize_name=normalize_component_name,
        load_access_control_func=load_access_control,
        extract_pod_name=_extract_pod_name_from_podspec_content,
    )


def walk_dir(directory: str, skip_dirs: set | None = None) -> list:
    return index_discover.walk_dir(directory, skip_dirs)


def is_source_file(f: str) -> bool:
    return index_discover.is_source_file(f)


def parse_podspec(pod_dir: str, name: str) -> dict:
    return index_parser.parse_podspec(pod_dir, name)


def extract_apis(file_path: str, rel_path: str) -> list:
    return index_parser.extract_apis(file_path, rel_path)


def compute_hash(pods_dir: str, components: set, access_control: dict | None = None) -> str:
    access = access_control or load_access_control()
    return index_builder.compute_hash(
        pods_dir,
        components,
        access_control=access,
        walk_dir=walk_dir,
        is_source_file=is_source_file,
    )


def build_index(pods_dir: str) -> dict:
    access = load_access_control()
    return index_builder.build_index(
        pods_dir,
        cache_dir=CACHE_DIR,
        access_control=access,
        normalize_name=normalize_component_name,
        discover_components=discover_components,
        compute_hash=compute_hash,
        parse_podspec=parse_podspec,
        walk_dir=walk_dir,
        is_source_file=is_source_file,
        extract_apis=extract_apis,
        access_mode_full=ACCESS_MODE_FULL,
        access_mode_api_only=ACCESS_MODE_API_ONLY,
    )


# ============================================================
# API Key 管理
# ============================================================

def _hash_api_key(key: str) -> str:
    return auth_store.hash_api_key(key)


def load_api_keys() -> dict:
    return auth_store.load_api_keys(KEYS_FILE, os.environ.get("MCP_API_KEYS", ""))


def validate_api_key(provided_key: str, valid_keys: dict) -> bool:
    return auth_store.validate_api_key(provided_key, valid_keys)


def generate_api_key(name: str = "") -> str:
    return auth_store.generate_api_key(KEYS_FILE, name)


def list_api_keys() -> list:
    return auth_store.list_api_keys(KEYS_FILE)


# ============================================================
# MCP Tools
# ============================================================

@mcp.tool()
def list_components() -> str:
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    return query_service.list_components(index_snapshot)


@mcp.tool()
def get_tool_docs(tool_name: str = "", format: str = "text") -> str:
    """返回 MCP 工具说明与最佳实践。

    适用场景：
    - Agent 首次接入本服务，不确定工具用途/参数时
    - 需要 machine-readable 文档（`format=\"json\"`）做自动化决策时

    参数：
    - `tool_name`: 指定工具名；为空时返回全部工具概览
    - `format`: `text` 或 `json`

    注意事项：
    - 推荐优先查看 `search_component`、`read_source` 等高频工具文档
    - 本工具内容依赖各 MCP tool 的函数 docstring，若为空会影响说明完整度
    """
    if format not in VALID_FORMATS:
        return f"错误：无效的 format 值，可选: {', '.join(sorted(VALID_FORMATS))}"

    import inspect

    tools = {
        "list_components": list_components,
        "search_component": search_component,
        "audit_component_api_quality": audit_component_api_quality,
        "get_component_api": get_component_api,
        "get_class_detail": get_class_detail,
        "read_source": read_source,
        "find_usage_example": find_usage_example,
        "refresh_index": refresh_index,
        "watch_status": watch_status,
        "sync_from_config": sync_from_config,
        "sync_gitlab_group": sync_gitlab_group_tool,
        "get_tool_docs": get_tool_docs,
    }

    def doc_for(name: str, fn):
        sig = str(inspect.signature(fn))
        doc = (inspect.getdoc(fn) or "").strip()
        return {"name": name, "signature": f"{name}{sig}", "doc": doc}

    if tool_name:
        fn = tools.get(tool_name)
        if not fn:
            available = ", ".join(sorted(tools.keys()))
            if format == "text":
                return f"未知工具：{tool_name}\n可用工具：{available}"
            return _to_json({"ok": False, "error": "unknown_tool", "tool": tool_name, "available": sorted(tools.keys())})
        payload = {"ok": True, "tool": doc_for(tool_name, fn)}
        if format == "json":
            return _to_json(payload)
        return f"# {payload['tool']['name']}\n\n`{payload['tool']['signature']}`\n\n{payload['tool']['doc']}"

    all_docs = sorted([doc_for(n, f) for n, f in tools.items()], key=lambda x: x["name"])

    if format == "json":
        return _to_json({"ok": True, "tools": all_docs})

    lines = [
        "# MCP 工具说明",
        "",
        "建议调用顺序：search_component -> (get_component_api/get_class_detail) -> read_source -> find_usage_example",
        "",
    ]
    for t in all_docs:
        one_line = t["doc"].split("\n")[0] if t["doc"] else ""
        lines.append(f"- `{t['name']}`: {one_line}")
    lines.append("\n想看某个工具的完整说明：get_tool_docs(tool_name=\"search_component\")")
    return "\n".join(lines)


def _to_json(data) -> str:
    return query_service.to_json(data)


def _get_component_from_snapshot(index_snapshot: dict, component_name: str) -> Optional[dict]:
    return query_service.get_component_from_snapshot(index_snapshot, component_name, normalize_component_name)


def is_api_only_component(component_name: str, comp: Optional[dict] = None) -> bool:
    if comp is not None:
        return query_service.is_api_only_component(
            component_name,
            comp,
            {},
            normalize_component_name,
            ACCESS_MODE_API_ONLY,
        )
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    return query_service.is_api_only_component(
        component_name,
        None,
        index_snapshot,
        normalize_component_name,
        ACCESS_MODE_API_ONLY,
    )


@mcp.tool()
def search_component(keyword: str, kind: str = "", format: str = "text", limit: int = 50) -> str:
    """搜索组件公开符号/声明/注释（模糊匹配）。

    适用场景：
    - 复用优先检索：先找是否已有组件/API 能覆盖需求
    - 组件选型、实现前查找候选方法/类/协议

    参数：
    - `keyword`: 关键词（必填，建议短词）
    - `kind`: 可选类型过滤（如 `method`、`interface`）
    - `format`: `text` 或 `json`；Agent 推荐 `json`
    - `limit`: 返回条数上限（1-200）

    推荐用法：
    - 默认 `format=\"json\", limit=5` 多轮检索（中文词/英文词/类名词）逐步收敛
    - 命中后再调用 `get_component_api` / `get_class_detail` 确认

    常见误区：
    - 单次大 `limit` 检索后就判定“无结果/无能力”
    - 只搜语义词，不搜类名和动词组合，导致误判
    """
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    return query_service.search_component(
        index_snapshot,
        keyword=keyword,
        kind=kind,
        format=format,
        limit=limit,
        max_keyword_len=MAX_KEYWORD_LEN,
        valid_kinds=VALID_KINDS,
        valid_formats=VALID_FORMATS,
    )


def _looks_suspicious_name(name: str) -> str:
    return query_service.looks_suspicious_name(name)


@mcp.tool()
def audit_component_api_quality(component_name: str = "", format: str = "json", limit: int = 200) -> str:
    """只读审计组件 API 质量候选清单（缺注释/可疑命名）。

    适用场景：
    - 在组件选型阶段比较维护风险
    - 治理 API 命名与注释质量（只读，不修改源码）

    参数：
    - `component_name`: 指定组件；为空表示审计全部组件
    - `format`: `text` 或 `json`（推荐 `json`）
    - `limit`: 每类问题最多返回条数

    注意事项：
    - 输出是启发式候选清单，不等于最终结论
    - 建议结合 `get_component_api` / `read_source` 小范围确认
    """
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    return query_service.audit_component_api_quality(
        index_snapshot,
        component_name=component_name,
        format=format,
        limit=limit,
        valid_formats=VALID_FORMATS,
    )


@mcp.tool()
def get_component_api(component_name: str) -> str:
    """获取组件完整公开 API（按文件分组）。

    适用场景：
    - 已通过 `search_component` 命中候选后，确认可复用 API 范围
    - 组件选型、实现、审查中的证据输出

    参数：
    - `component_name`: 组件名（区分大小写；支持已索引组件）

    推荐调用顺序：
    - `search_component` -> `get_component_api` -> `get_class_detail` -> `read_source`（必要时）

    常见误区：
    - 未确认组件名直接猜测 API
    - 仅凭搜索命中，不查看 API 就下结论
    """
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    return query_service.get_component_api(index_snapshot, component_name, max_api_output=MAX_API_OUTPUT)


@mcp.tool()
def get_class_detail(component_name: str, classname: str) -> str:
    """查看类/协议视图（定义、属性、公开/内部方法）。

    适用场景：
    - 确认关键类入口、方法分布与定义文件
    - 在不读取大量源码的前提下做结构化验证

    参数：
    - `component_name`: 组件名
    - `classname`: 类/协议/结构体名

    注意事项：
    - 建议先用 `get_component_api` 确认候选类名，再调用本工具
    - 若仍需实现细节，再用 `read_source` 小范围读取
    """
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    return query_service.get_class_detail(index_snapshot, component_name, classname)


@mcp.tool()
def read_source(component_name: str, file: str, start: int = 1, end: int = 0) -> str:
    """按行读取组件源码（支持模糊文件名）。

    适用场景：
    - 在已有 `file:line` 证据后，小范围验证实现语义/边界条件
    - 补充 `get_component_api` / `get_class_detail` 无法表达的细节

    参数：
    - `component_name`: 组件名
    - `file`: 文件路径或模糊文件名（限制在组件目录内）
    - `start` / `end`: 行号范围；`end<=0` 时自动给出小窗口

    推荐用法：
    - 先 `search_component` / `get_component_api` 定位，再读取 20-40 行窗口

    常见误区：
    - 大段读取源码作为首选步骤（成本高且易偏离）
    - 忽略 `api_only` 组件访问限制（会被拒绝）
    """
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    return source_service.read_source(
        index_snapshot=index_snapshot,
        pods_dir=PODS_DIR,
        component_name=component_name,
        file=file,
        start=start,
        end=end,
        max_read_lines=MAX_READ_LINES,
        api_only_deny_message=API_ONLY_DENY_MESSAGE,
        is_source_file=is_source_file,
        get_component_from_snapshot=lambda snapshot, name: _get_component_from_snapshot(snapshot, name),
        is_api_only_component=lambda name, comp: is_api_only_component(name, comp),
    )


@mcp.tool()
def refresh_index() -> str:
    result = check_for_updates()

    lines = [f"🔄 检查完成 ({result['time']})"]

    for repo in result["repos"]:
        status = "✅ 已更新" if repo["updated"] else ("⚠️ " + repo["error"] if repo["error"] else "➖ 无变更")
        changes = f" ({repo['changes']} 文件)" if repo["changes"] else ""
        lines.append(f"  {repo['name']}: {status}{changes}")

    if result["reindexed"]:
        with INDEX_LOCK:
            count = len(INDEX)
        lines.append(f"\n✅ 索引已重建（{count} 个组件）")
    else:
        lines.append("\nℹ️ 索引无需更新")

    return "\n".join(lines)


@mcp.tool()
def watch_status() -> str:
    lines = []

    if WATCH_INTERVAL > 0:
        lines.append(f"🔄 定时检查: 每 {WATCH_INTERVAL} 秒")
    else:
        lines.append("⏸️ 定时检查: 未启用")

    repos = discover_git_repos(PODS_DIR)
    lines.append(f"📦 监控仓库: {len(repos)} 个")
    for repo in repos:
        name = os.path.basename(repo) or "root"
        lines.append(f"  - {name}")

    with INDEX_LOCK:
        count = len(INDEX)
    lines.append(f"\n📊 当前索引: {count} 个组件")

    if WATCH_LOG:
        lines.append(f"\n📋 最近 {min(len(WATCH_LOG), 10)} 条更新日志:")
        for entry in WATCH_LOG[-10:]:
            updated_repos = [r["name"] for r in entry["repos"] if r["updated"]]
            if updated_repos:
                lines.append(f"  {entry['time']} — ✅ 更新: {', '.join(updated_repos)}")
            else:
                errors = [r["name"] for r in entry["repos"] if r["error"]]
                if errors:
                    lines.append(f"  {entry['time']} — ⚠️ 错误: {', '.join(errors)}")
                else:
                    lines.append(f"  {entry['time']} — ➖ 无变更")
    else:
        lines.append("\n📋 暂无更新日志")

    return "\n".join(lines)


@mcp.tool()
def sync_from_config(config_path: str = "") -> str:
    if not config_path:
        config_path = os.path.join(APP_BASE_DIR, "components.yaml")

    if not os.path.exists(config_path):
        return (
            f"配置文件不存在: {config_path}\n\n请创建 components.yaml，格式示例:\n"
            "```yaml\ncomponents:\n  BTBaseKit:\n    repo: git@gitlab.com:ios/BTBaseKit.git\n    branch: main\n```"
        )

    results = sync_components(config_path, PODS_DIR)

    if not results:
        return "无组件需要同步"

    lines = ["📦 组件同步结果:\n"]
    for r in results:
        status_icon = {"cloned": "✅", "updated": "🔄", "skip": "⏭️", "error": "❌"}.get(r["status"], "❓")
        lines.append(f"{status_icon} **{r['name']}**: {r['message']}")

    cloned = sum(1 for r in results if r["status"] == "cloned")
    updated = sum(1 for r in results if r["status"] == "updated")
    errors = sum(1 for r in results if r["status"] == "error")

    lines.append(f"\n📊 统计: {cloned} 克隆, {updated} 更新, {errors} 错误")

    if cloned > 0:
        lines.append("\n🔄 检测到新组件，正在重建索引...")
        global INDEX, LAST_HASH
        cache_path = os.path.join(CACHE_DIR, "index.json")
        if os.path.exists(cache_path):
            os.remove(cache_path)
        new_index = build_index(PODS_DIR)
        with INDEX_LOCK:
            INDEX = new_index
        components = discover_components(PODS_DIR)
        LAST_HASH = compute_hash(PODS_DIR, components)
        lines.append(f"✅ 索引已更新（{len(INDEX)} 个组件）")

    return "\n".join(lines)


@mcp.tool()
def sync_gitlab_group_tool(group_id: str, gitlab_url: str = "", gitlab_token: str = "", use_ssh: bool = True) -> str:
    token = gitlab_token or GITLAB_TOKEN
    if not token:
        return "错误：未配置 GitLab Token。请设置 GITLAB_TOKEN 环境变量或传入 gitlab_token 参数。"

    results = sync_gitlab_group(group_id, PODS_DIR, gitlab_url, token, use_ssh)

    if not results:
        return "未找到仓库或获取失败"

    lines = [f"📦 GitLab Group '{group_id}' 同步结果:\n"]

    base_components = []
    skipped = []

    for r in results:
        if r["status"] == "skip":
            skipped.append(f"⏭️ {r['name']}: {r['message']}")
        else:
            status_icon = {"cloned": "✅", "updated": "🔄", "error": "❌"}.get(r["status"], "❓")
            base_components.append(f"{status_icon} {r['name']}: {r['message']}")

    if base_components:
        lines.append("**基础组件:**")
        lines.extend(base_components)

    if skipped:
        lines.append(f"\n**已跳过（非基础组件，共 {len(skipped)} 个）:**")
        lines.extend(skipped[:10])
        if len(skipped) > 10:
            lines.append(f"... 还有 {len(skipped) - 10} 个")

    cloned = sum(1 for r in results if r["status"] == "cloned")
    updated = sum(1 for r in results if r["status"] == "updated")
    errors = sum(1 for r in results if r["status"] == "error")

    lines.append(f"\n📊 统计: {len(base_components)} 基础组件 ({cloned} 克隆, {updated} 更新, {errors} 错误), {len(skipped)} 已跳过")

    if cloned > 0:
        lines.append("\n🔄 检测到新组件，正在重建索引...")
        global INDEX, LAST_HASH
        cache_path = os.path.join(CACHE_DIR, "index.json")
        if os.path.exists(cache_path):
            os.remove(cache_path)
        new_index = build_index(PODS_DIR)
        with INDEX_LOCK:
            INDEX = new_index
        components = discover_components(PODS_DIR)
        LAST_HASH = compute_hash(PODS_DIR, components)
        lines.append(f"✅ 索引已更新（{len(INDEX)} 个组件）")

    return "\n".join(lines)


@mcp.tool()
def find_usage_example(component_name: str) -> str:
    """搜索其他组件中对目标组件的导入与使用示例。

    适用场景：
    - 组件选型时验证是否有真实使用样例
    - 迁移/实现时参考现有接入方式
    - `api_only` 组件场景下，作为源码验证的替代证据之一

    参数：
    - `component_name`: 目标组件名

    注意事项：
    - 返回结果可能较多，建议只摘取最相关位置做证据
    - 与 `get_component_api` 联合使用，避免只凭 import 命中下结论
    """
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    return source_service.find_usage_example(
        index_snapshot=index_snapshot,
        pods_dir=PODS_DIR,
        component_name=component_name,
        api_only_deny_message=API_ONLY_DENY_MESSAGE,
        is_source_file=is_source_file,
        get_component_from_snapshot=lambda snapshot, name: _get_component_from_snapshot(snapshot, name),
        is_api_only_component=lambda name, comp: is_api_only_component(name, comp),
    )


# ============================================================
# Webhook & 热更新
# ============================================================

def reindex() -> None:
    global INDEX, LAST_HASH

    def _set_index(new_index: dict) -> None:
        global INDEX
        with INDEX_LOCK:
            INDEX = new_index

    def _set_last_hash(new_hash: str) -> None:
        global LAST_HASH
        LAST_HASH = new_hash

    update_service.reindex(
        pods_dir=PODS_DIR,
        cache_dir=CACHE_DIR,
        reindex_lock=REINDEX_LOCK,
        set_index=_set_index,
        set_last_hash=_set_last_hash,
        build_index=build_index,
        discover_components=discover_components,
        compute_hash=compute_hash,
    )


# ============================================================
# 定时检查 & 多仓库更新
# ============================================================

def discover_git_repos(pods_dir: str) -> list:
    return git_client.discover_git_repos(pods_dir)


def git_pull_repo(repo_path: str) -> dict:
    return git_client.git_pull_repo(repo_path)


def check_for_updates() -> dict:
    global INDEX, LAST_HASH, WATCH_LOG

    def _set_index(new_index: dict) -> None:
        global INDEX
        with INDEX_LOCK:
            INDEX = new_index

    def _set_last_hash(new_hash: str) -> None:
        global LAST_HASH
        LAST_HASH = new_hash

    return update_service.check_for_updates(
        pods_dir=PODS_DIR,
        cache_dir=CACHE_DIR,
        last_hash=LAST_HASH,
        watch_log=WATCH_LOG,
        watch_log_max=WATCH_LOG_MAX,
        set_index=_set_index,
        set_last_hash=_set_last_hash,
        discover_git_repos=discover_git_repos,
        git_pull_repo=git_pull_repo,
        discover_components=discover_components,
        compute_hash=compute_hash,
        build_index=build_index,
    )


def watch_loop(interval: int):
    return update_service.watch_loop(interval, check_for_updates=check_for_updates)


# ============================================================
# 组件同步
# ============================================================

def sync_component(name: str, config: dict, target_dir: str) -> dict:
    return sync_service.sync_component(name, config, target_dir)


def sync_components(config_path: str, target_dir: str) -> list:
    return sync_service.sync_components(
        config_path,
        target_dir,
        load_components_config=load_components_config,
        sync_component_func=sync_component,
    )


def fetch_gitlab_group_repos(group_id: str, gitlab_url: str = "", gitlab_token: str = "") -> list:
    return gitlab_client.fetch_gitlab_group_repos(group_id, gitlab_url or GITLAB_URL, gitlab_token or GITLAB_TOKEN)


def check_repo_is_base_component(repo_url: str, branch: str = "main", gitlab_token: str = "") -> tuple:
    return gitlab_client.check_repo_is_base_component(repo_url, GITLAB_URL, branch, gitlab_token or GITLAB_TOKEN)


def sync_gitlab_group(group_id: str, target_dir: str, gitlab_url: str = "", gitlab_token: str = "", use_ssh: bool = True) -> list:
    effective_url = gitlab_url or GITLAB_URL
    effective_token = gitlab_token or GITLAB_TOKEN
    return sync_service.sync_gitlab_group(
        group_id,
        target_dir,
        gitlab_url=effective_url,
        gitlab_token=effective_token,
        use_ssh=use_ssh,
        fetch_gitlab_group_repos=fetch_gitlab_group_repos,
        check_repo_is_base_component=lambda repo_url, _url, branch, token: check_repo_is_base_component(repo_url, branch, token),
        sync_component_func=sync_component,
    )


def verify_gitlab_signature(body: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        print("[mcp-ios] ⚠️ Webhook 请求被拒绝：未配置 WEBHOOK_SECRET", file=sys.stderr)
        return False
    return hmac.compare_digest(signature, WEBHOOK_SECRET)


_LOOPBACK_HTTP_HOSTS = {"127.0.0.1", "localhost", "::1"}
_LOCALHOST_ONLY_ALLOWED_HOSTS = frozenset({"127.0.0.1:*", "localhost:*", "[::1]:*"})
_LOCALHOST_ONLY_ALLOWED_ORIGINS = frozenset({"http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"})
MCP_HTTP_PATH = "/mcp"
OAUTH_DISCOVERY_PATHS = frozenset(
    {
        "/.well-known/oauth-authorization-server",
        f"/.well-known/oauth-authorization-server{MCP_HTTP_PATH}",
        f"{MCP_HTTP_PATH}/.well-known/oauth-authorization-server",
    }
)
PUBLIC_MCP_DISCOVERY_METHODS = frozenset(
    {
        "initialize",
        "tools/list",
        "resources/list",
        "prompts/list",
    }
)


def _normalize_http_host(host: str) -> str:
    normalized = str(host or "").strip().lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    return normalized


def _is_loopback_http_host(host: str) -> bool:
    return _normalize_http_host(host) in _LOOPBACK_HTTP_HOSTS


def _is_localhost_only_transport_security(settings) -> bool:
    if settings is None:
        return False

    if not getattr(settings, "enable_dns_rebinding_protection", False):
        return False

    allowed_hosts = frozenset(getattr(settings, "allowed_hosts", []) or [])
    allowed_origins = frozenset(getattr(settings, "allowed_origins", []) or [])
    return allowed_hosts == _LOCALHOST_ONLY_ALLOWED_HOSTS and allowed_origins == _LOCALHOST_ONLY_ALLOWED_ORIGINS


def _align_mcp_http_runtime_settings(http_host: str, http_port: int) -> None:
    """Align FastMCP runtime settings with CLI HTTP bind args.

    FastMCP may auto-enable localhost-only DNS rebinding protection when created
    with default host=127.0.0.1. Our CLI default is --host 0.0.0.0, so we need to
    disable that localhost-only policy for LAN/WAN bindings to avoid 421 errors.
    """
    settings = getattr(mcp, "settings", None)
    if settings is None:
        return

    settings.host = http_host
    settings.port = http_port

    if _is_loopback_http_host(http_host):
        return

    current_transport_security = getattr(settings, "transport_security", None)
    if not _is_localhost_only_transport_security(current_transport_security):
        return

    if TransportSecuritySettings is None:
        return

    settings.transport_security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    print(
        f"[mcp-ios] ⚙️ 非 localhost 监听 ({http_host})，已关闭 FastMCP 默认 localhost Host 校验以支持局域网访问",
        file=sys.stderr,
    )


def _decode_http_headers(scope: dict) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw_key, raw_value in scope.get("headers", []):
        try:
            key = raw_key.decode().lower()
            value = raw_value.decode()
        except Exception:
            continue
        headers[key] = value
    return headers


def _is_plain_mcp_probe_request(scope: dict) -> bool:
    if scope.get("type") != "http":
        return False

    if scope.get("method", "").upper() != "GET":
        return False

    if scope.get("path", "") != MCP_HTTP_PATH:
        return False

    headers = _decode_http_headers(scope)

    return not any(
        [
            "mcp-session-id" in headers,
            "last-event-id" in headers,
        ]
    )


def _build_mcp_probe_payload(http_host: str, http_port: int, auth_enabled: bool) -> dict:
    return {
        "ok": True,
        "message": "MCP HTTP 端点已启动。请使用 MCP 客户端通过 POST /mcp 发起初始化，而不是直接用浏览器 GET /mcp。",
        "mcp_endpoint": f"http://{http_host}:{http_port}{MCP_HTTP_PATH}",
        "health_endpoint": f"http://{http_host}:{http_port}/webhook/health",
        "auth": "bearer" if auth_enabled else "none",
    }


def _build_oauth_not_supported_payload(http_host: str, http_port: int, auth_enabled: bool) -> dict:
    return {
        "ok": False,
        "error": "oauth_discovery_not_supported",
        "message": "当前服务未提供 OAuth 自动发现端点，请直接连接 MCP HTTP 端点并按需携带 Bearer API Key。",
        "mcp_endpoint": f"http://{http_host}:{http_port}{MCP_HTTP_PATH}",
        "health_endpoint": f"http://{http_host}:{http_port}/webhook/health",
        "auth": "bearer" if auth_enabled else "none",
    }


def _extract_jsonrpc_method_from_body(body: bytes) -> str:
    if not body:
        return ""

    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return ""

    if isinstance(payload, dict):
        method = payload.get("method", "")
        if isinstance(method, str):
            return method

    return ""


def _is_public_mcp_discovery_method(method: str) -> bool:
    return method in PUBLIC_MCP_DISCOVERY_METHODS


async def _read_http_request_body(receive) -> bytes:
    chunks: list[bytes] = []

    while True:
        message = await receive()
        if message.get("type") != "http.request":
            break

        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break

    return b"".join(chunks)


def _build_replay_receive(body: bytes):
    sent = False
    disconnect_event = asyncio.Event()

    async def replay_receive():
        nonlocal sent
        if not sent:
            sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }
        await disconnect_event.wait()
        return {"type": "http.disconnect"}

    return replay_receive


# ============================================================
# 启动
# ============================================================

def main():
    global PODS_DIR, INDEX, LAST_HASH, WATCH_INTERVAL, WEBHOOK_SECRET, GITLAB_URL, GITLAB_TOKEN

    parser = argparse.ArgumentParser(description="iOS Components MCP Server")
    parser.add_argument("pods_dir", nargs="?", default=DEFAULT_PODS_DIR, help="组件库根目录")
    parser.add_argument("--http", action="store_true", help="HTTP 模式启动")
    parser.add_argument("--port", type=int, default=8900, help="HTTP 端口（默认 8900）")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP 监听地址")
    parser.add_argument("--api-keys", help="API Keys（逗号分隔）")
    parser.add_argument("--gen-key", metavar="NAME", help="生成新 API Key")
    parser.add_argument("--list-keys", action="store_true", help="列出已注册 API Keys")
    parser.add_argument("--webhook-secret", help="GitLab Webhook Secret Token")
    parser.add_argument("--watch", type=int, metavar="SECONDS", default=0, help="定时检查间隔（秒）")
    parser.add_argument("--sync", metavar="CONFIG", nargs="?", const="components.yaml", help="根据配置文件同步组件代码")
    parser.add_argument("--sync-only", action="store_true", help="仅同步，不启动服务")
    parser.add_argument("--gitlab-group", metavar="GROUP", help="从 GitLab group 自动发现并同步基础组件")
    parser.add_argument("--gitlab-url", default="", help="GitLab 服务器地址")
    parser.add_argument("--gitlab-token", default="", help="GitLab API Token")
    parser.add_argument("--use-https", action="store_true", help="使用 HTTPS 地址克隆（默认 SSH）")

    args = parser.parse_args()
    PODS_DIR = args.pods_dir

    if args.gen_key:
        key = generate_api_key(args.gen_key)
        print(f"✅ 已生成 API Key (name: {args.gen_key}):\n   {key}")
        print("\n   Claude Code 远程连接:")
        print(f"   claude mcp add --transport http ios-components http://your-server:{args.port}/mcp \\")
        print(f'     --header "Authorization: Bearer {key}"')
        return

    if args.list_keys:
        keys = list_api_keys()
        if not keys:
            print("暂无 API Key。使用 --gen-key <name> 生成。")
        else:
            print(f"已注册 API Keys ({len(keys)} 个):")
            for k in keys:
                print(f"  #{k['id']}: {k['name']}")
        return

    if args.sync:
        config_path = args.sync
        if not os.path.isabs(config_path):
            config_path = os.path.join(APP_BASE_DIR, config_path)

        results = sync_components(config_path, PODS_DIR)

        if args.sync_only:
            errors = sum(1 for r in results if r["status"] == "error")
            sys.exit(1 if errors > 0 else 0)

    if args.gitlab_group:
        if args.gitlab_url:
            GITLAB_URL = args.gitlab_url
        if args.gitlab_token:
            GITLAB_TOKEN = args.gitlab_token

        results = sync_gitlab_group(
            args.gitlab_group,
            PODS_DIR,
            args.gitlab_url,
            args.gitlab_token,
            use_ssh=not args.use_https,
        )

        if args.sync_only:
            errors = sum(1 for r in results if r["status"] == "error")
            sys.exit(1 if errors > 0 else 0)

    if args.api_keys:
        os.environ["MCP_API_KEYS"] = args.api_keys
    if args.webhook_secret:
        WEBHOOK_SECRET = args.webhook_secret

    INDEX = build_index(PODS_DIR)

    components = discover_components(PODS_DIR)
    LAST_HASH = compute_hash(PODS_DIR, components)

    watch_interval = args.watch or WATCH_INTERVAL
    if watch_interval > 0:
        WATCH_INTERVAL = watch_interval
        watcher = threading.Thread(target=watch_loop, args=(watch_interval,), daemon=True)
        watcher.start()

    if args.http:
        import uvicorn
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Mount, Route

        valid_keys = load_api_keys()
        _align_mcp_http_runtime_settings(args.host, args.port)
        mcp_app = mcp.streamable_http_app()

        @asynccontextmanager
        async def lifespan(app):
            async with mcp_app.router.lifespan_context(app):
                yield

        async def webhook_gitlab(request: Request):
            token = request.headers.get("X-Gitlab-Token", "")
            if not verify_gitlab_signature(b"", token):
                return JSONResponse({"error": "Forbidden"}, status_code=403)

            try:
                body = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)

            event = request.headers.get("X-Gitlab-Event", "")
            object_kind = body.get("object_kind", "")

            if event != "Push Hook" and object_kind != "push":
                return JSONResponse({"message": f"Ignored event: {event or object_kind}"})

            ref = body.get("ref", "")
            project = body.get("project", {}).get("name", "unknown")
            commits = len(body.get("commits", []))
            print(f"[mcp-ios] 📦 GitLab push: {project} ({ref}), {commits} commit(s)", file=sys.stderr)

            threading.Thread(target=reindex, daemon=True).start()

            return JSONResponse(
                {
                    "message": "Reindex triggered",
                    "project": project,
                    "ref": ref,
                    "commits": commits,
                }
            )

        async def webhook_health(request: Request):
            with INDEX_LOCK:
                count = len(INDEX)
            return JSONResponse({"status": "ok", "components": count})

        async def auth_mcp_app(scope, receive, send):
            if scope["type"] == "http":
                if scope.get("path", "") in OAUTH_DISCOVERY_PATHS:
                    response = JSONResponse(
                        _build_oauth_not_supported_payload(args.host, args.port, bool(valid_keys)),
                        status_code=404,
                    )
                    await response(scope, receive, send)
                    return

                if _is_plain_mcp_probe_request(scope):
                    response = JSONResponse(
                        _build_mcp_probe_payload(args.host, args.port, bool(valid_keys)),
                        status_code=200,
                    )
                    await response(scope, receive, send)
                    return

                if scope.get("path", "") == MCP_HTTP_PATH and scope.get("method", "").upper() == "POST":
                    raw_body = await _read_http_request_body(receive)
                    receive = _build_replay_receive(raw_body)

                    if _is_public_mcp_discovery_method(_extract_jsonrpc_method_from_body(raw_body)):
                        await mcp_app(scope, receive, send)
                        return

                headers = dict(scope.get("headers", []))
                auth_value = headers.get(b"authorization", b"").decode()
                api_key = auth_value.replace("Bearer ", "").strip()
                current_keys = load_api_keys()
                if not validate_api_key(api_key, current_keys):
                    response = JSONResponse(
                        {"error": "Unauthorized", "message": "Invalid or missing API key"},
                        status_code=401,
                    )
                    await response(scope, receive, send)
                    return
            await mcp_app(scope, receive, send)

        app = Starlette(
            routes=[
                Route("/webhook/gitlab", webhook_gitlab, methods=["POST"]),
                Route("/webhook/health", webhook_health, methods=["GET"]),
                Mount("/", app=auth_mcp_app),
            ],
            lifespan=lifespan,
        )

        print("🚀 iOS Components MCP Server (HTTP)")
        print(f"   地址: http://{args.host}:{args.port}")
        print(f"   鉴权: {'✅ 已启用' if valid_keys else '⚠️ 未配置'}")
        print(f"   Webhook: http://{args.host}:{args.port}/webhook/gitlab")
        print(f"   Webhook Secret: {'✅ 已配置' if WEBHOOK_SECRET else '⚠️ 未配置'}")
        print(f"   定时检查: {'每 ' + str(watch_interval) + ' 秒' if watch_interval > 0 else '未启用'}")
        print(f"   Git 仓库: {len(discover_git_repos(PODS_DIR))} 个")
        print(f"   组件: {len(INDEX)} 个")
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
