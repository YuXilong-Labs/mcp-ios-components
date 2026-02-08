#!/usr/bin/env python3
"""MCP Server: iOS CocoaPods Component Index

Provides AI-powered code search for iOS CocoaPods component libraries.
Helps Claude Code (or any MCP client) discover existing APIs before writing code.

Features:
- Auto component discovery via podspec scanning
- Comment extraction (/// and /** */) for Swift & ObjC
- Swift public/open declaration parsing
- Cross-component usage example search
- SHA256 cache with auto-rebuild on file changes
- HTTP mode with API Key authentication
- Line-range source reading (token-efficient)
- Per-class aggregated view

Usage:
  Local stdio:   python mcp_server.py [/path/to/pods]
  HTTP server:   python mcp_server.py --http --port 8900 [/path/to/pods]
  Key management: python mcp_server.py --gen-key <name>
                  python mcp_server.py --list-keys
"""

import json
import os
import re
import sys
import hashlib
import secrets
import argparse
import subprocess
import hmac
import threading
from collections import Counter
from typing import Optional
from mcp.server.fastmcp import FastMCP

# ============================================================
# 配置
# ============================================================

DEFAULT_PODS_DIR = os.environ.get("IOS_PODS_DIR", os.getcwd())
CACHE_DIR = os.environ.get("IOS_PODS_CACHE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache"))
KEYS_FILE = os.environ.get("IOS_PODS_KEYS_FILE", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".api-keys"))
MIXUP_MARKER = os.environ.get("IOS_PODS_MIXUP_MARKER", "SUPPORT_MIXUP")
WEBHOOK_SECRET = os.environ.get("IOS_PODS_WEBHOOK_SECRET", "")
WATCH_INTERVAL = int(os.environ.get("IOS_PODS_WATCH_INTERVAL", "0"))  # 秒, 0=禁用

# 运行时赋值
PODS_DIR = DEFAULT_PODS_DIR
INDEX: dict = {}
INDEX_LOCK = threading.Lock()
LAST_HASH: str = ""
WATCH_LOG: list = []  # 最近的更新日志
WATCH_LOG_MAX = 50

mcp = FastMCP("ios-components", instructions="""iOS 组件库代码索引 — 复用优先，拒绝重复造轮子。

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
告诉用户直接用：[image xx_imageWithCornerRadius:8]""")


# ============================================================
# 组件发现 & 索引构建
# ============================================================

def discover_components(pods_dir: str, return_filtered: bool = False) -> set | tuple:
    """自动发现基础组件：扫描含 .podspec 的目录
    
    判定规则：
    1. podspec 中不含任何 MIXUP 声明 → 基础组件
    2. podspec 中的 MIXUP 声明全部为空数组 → 基础组件
       - SUPPORT_MIXUP = []
       - BETA_SUPPORT_MIXUP = []
    3. podspec 中存在非空 MIXUP 声明 → 非基础组件
       - SUPPORT_MIXUP = ['XXX', 'YYY']
       - BETA_SUPPORT_MIXUP = ['VO']
    
    Args:
        pods_dir: 组件库根目录
        return_filtered: 是否同时返回被过滤的非基础组件
    
    Returns:
        如果 return_filtered=False: 返回基础组件集合
        如果 return_filtered=True: 返回 (基础组件集合, 非基础组件字典{name: mixup_values})
    """
    components = set()
    filtered = {}  # {组件名: mixup声明内容}

    # Optional allowlist for safe/fast smoke tests.
    # Example: IOS_PODS_INCLUDE="BTBaseKit,BTNetwork"
    include_env = os.getenv("IOS_PODS_INCLUDE", "").strip()
    include_set = {x.strip() for x in include_env.split(",") if x.strip()} if include_env else set()
    include_set_lower = {x.lower() for x in include_set}
    
    if not os.path.exists(pods_dir):
        return (components, filtered) if return_filtered else components
    
    for entry in os.listdir(pods_dir):
        if include_set and entry.lower() not in include_set_lower:
            continue
        entry_path = os.path.join(pods_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        specs = [f for f in os.listdir(entry_path) if f.endswith('.podspec')]
        if not specs:
            continue
        with open(os.path.join(entry_path, specs[0]), encoding='utf-8', errors='ignore') as spec_file:
            spec_content = spec_file.read()
        
        has_nonempty_mixup = False  # 是否有非空的 MIXUP 声明
        mixup_values = []  # 记录 MIXUP 声明内容
        
        for line in spec_content.split('\n'):
            stripped = line.strip()
            # 跳过注释行
            if stripped.startswith('#') or stripped.startswith('//'):
                continue
            
            # 检查 SUPPORT_MIXUP 或 BETA_SUPPORT_MIXUP 声明
            mixup_match = re.search(r'((?:SUPPORT_MIXUP|BETA_SUPPORT_MIXUP)\s*=\s*\[[^\]]*\])', stripped)
            if mixup_match:
                mixup_values.append(mixup_match.group(1))
                array_match = re.search(r'=\s*\[([^\]]*)\]', mixup_match.group(1))
                if array_match:
                    array_content = array_match.group(1).strip()
                    # 如果数组内容非空（有实际元素），则不是基础组件
                    if array_content:
                        has_nonempty_mixup = True
        
        if not has_nonempty_mixup:
            components.add(entry)
        else:
            filtered[entry] = mixup_values
    
    return (components, filtered) if return_filtered else components


def walk_dir(directory: str, skip_dirs: set = None) -> list:
    """递归列出目录下所有文件，忽略 Example 和隐藏目录"""
    if skip_dirs is None:
        skip_dirs = {'Example', 'Examples'}
    results = []
    if not os.path.exists(directory):
        return results
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
        for f in files:
            results.append(os.path.relpath(os.path.join(root, f), directory))
    return results


def is_source_file(f: str) -> bool:
    return f.endswith(('.swift', '.h', '.m', '.mm'))


def parse_podspec(pod_dir: str, name: str) -> dict:
    """从 podspec 提取 name/summary/description。

    Note: repo directory name may not match the pod name (case or naming).
    We try common filenames first, then fall back to the first *.podspec.
    """
    candidates = [f'{name}.podspec', f'{name}.podspec.json']

    # Fall back to any podspec in the directory.
    try:
        for f in os.listdir(pod_dir):
            if f.endswith('.podspec') and f not in candidates:
                candidates.append(f)
                break
    except Exception:
        pass

    for fname in candidates:
        spec_path = os.path.join(pod_dir, fname)
        if not os.path.exists(spec_path):
            continue
        with open(spec_path, encoding='utf-8', errors='ignore') as f:
            content = f.read()

        name_m = re.search(r"\.name\s*=\s*['\"](.+?)['\"]", content)
        summary_m = re.search(r"\.summary\s*=\s*['\"](.+?)['\"]", content)
        desc_m = re.search(r'\.description\s*=\s*<<-DESC\s*([\s\S]*?)\s*DESC', content)
        desc_m2 = re.search(r"\.description\s*=\s*['\"](.+?)['\"]", content)

        return {
            'pod_name': name_m.group(1) if name_m else name,
            'summary': summary_m.group(1) if summary_m else '',
            'description': (desc_m.group(1).strip() if desc_m else desc_m2.group(1) if desc_m2 else ''),
            'podspec': fname,
        }

    return {'pod_name': name, 'summary': '', 'description': '', 'podspec': ''}


def extract_apis(file_path: str, rel_path: str) -> list:
    """提取 API 声明 + 注释"""
    apis = []
    try:
        with open(file_path, encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except:
        return apis

    lines = content.split('\n')
    is_swift = file_path.endswith('.swift')
    is_header = file_path.endswith('.h')
    pending_comment = ''

    for i, line in enumerate(lines):
        trimmed = line.strip()

        # 收集 /// 注释
        if trimmed.startswith('///'):
            pending_comment += ('\n' if pending_comment else '') + trimmed
            continue

        # 收集 /** */ 块注释
        if trimmed.startswith('/**'):
            block = trimmed
            j = i
            while '*/' not in block and j < len(lines) - 1:
                j += 1
                block += '\n' + lines[j].strip()
            pending_comment = block
            continue

        if is_swift:
            # Swift public/open 声明
            m = re.match(
                r'^(?:@\w+\s+)*(?:public|open)\s+(?:(?:class|static|final|override|weak|lazy|nonisolated|@objc(?:\([^)]*\))?)\s+)*'
                r'(class|struct|protocol|enum|func|var|let|typealias|init|subscript)\b(.*)',
                trimmed
            )
            if m:
                kind = m.group(1)
                rest = m.group(2).strip()
                name = ''
                if kind == 'func':
                    fn = re.match(r'^(\w+)', rest)
                    name = fn.group(1) if fn else rest.split('(')[0]
                elif kind == 'init':
                    name = 'init'
                elif kind in ('var', 'let', 'typealias'):
                    vn = re.match(r'^(\w+)', rest)
                    name = vn.group(1) if vn else ''
                else:
                    cn = re.match(r'^(\w+)', rest)
                    name = cn.group(1) if cn else ''
                apis.append({
                    'kind': kind, 'name': name, 'declaration': trimmed,
                    'file': rel_path, 'line': i + 1, 'comment': pending_comment,
                })
                pending_comment = ''
                continue

        if is_header:
            # ObjC @interface / @protocol
            m = re.match(r'^@(interface|protocol)\s+(\w+)', trimmed)
            if m:
                apis.append({
                    'kind': m.group(1), 'name': m.group(2), 'declaration': trimmed,
                    'file': rel_path, 'line': i + 1, 'comment': pending_comment,
                })
                pending_comment = ''
                continue

            # @property
            m = re.match(r'^@property\s*\(([^)]*)\)\s*\S+\s*\*?\s*(\w+)', trimmed)
            if m:
                apis.append({
                    'kind': 'property', 'name': m.group(2), 'declaration': trimmed,
                    'file': rel_path, 'line': i + 1, 'comment': pending_comment,
                })
                pending_comment = ''
                continue

            # C 内联函数
            m = re.match(
                r'^(?:CG_INLINE|NS_INLINE|FOUNDATION_STATIC_INLINE|static\s+(?:__)?inline)\s+\w[\w\s*]*?\b(\w+)\s*\(',
                trimmed
            )
            if m:
                apis.append({
                    'kind': 'func', 'name': m.group(1), 'declaration': trimmed,
                    'file': rel_path, 'line': i + 1, 'comment': pending_comment,
                })
                pending_comment = ''
                continue

            # extern 函数
            m = re.match(
                r'^(?:FOUNDATION_EXTERN|UIKIT_EXTERN|extern|OBJC_EXTERN)\s+.*?\b(\w+)\s*\(',
                trimmed
            )
            if m:
                apis.append({
                    'kind': 'func', 'name': m.group(1), 'declaration': trimmed,
                    'file': rel_path, 'line': i + 1, 'comment': pending_comment,
                })
                pending_comment = ''
                continue

            # ObjC 方法声明 (- 或 +)
            if (trimmed.startswith('-') or trimmed.startswith('+')) and ';' in trimmed:
                mm = re.match(r'[-+]\s*\([^)]+\)\s*(\w+)', trimmed)
                apis.append({
                    'kind': 'method', 'name': mm.group(1) if mm else '',
                    'declaration': trimmed, 'file': rel_path, 'line': i + 1,
                    'comment': pending_comment,
                })
                pending_comment = ''
                continue

        if trimmed:
            pending_comment = ''

    return apis


def compute_hash(pods_dir: str, components: set) -> str:
    """基于文件列表 + mtime 计算 hash"""
    h = hashlib.sha256()
    for name in sorted(components):
        comp_dir = os.path.join(pods_dir, name)
        if not os.path.exists(comp_dir):
            continue
        files = sorted(f for f in walk_dir(comp_dir) if is_source_file(f))
        for f in files:
            full = os.path.join(comp_dir, f)
            try:
                stat = os.stat(full)
                h.update(f'{f}:{stat.st_mtime_ns}\n'.encode())
            except:
                pass
    return h.hexdigest()


def build_index(pods_dir: str) -> dict:
    """构建或加载索引（带缓存）"""
    components, filtered = discover_components(pods_dir, return_filtered=True)
    
    # 输出组件分类信息
    print(f"\n[mcp-ios] ========== 组件分类 ==========", file=sys.stderr)
    print(f"[mcp-ios] ✅ 基础组件 ({len(components)} 个):", file=sys.stderr)
    for name in sorted(components):
        print(f"    {name}", file=sys.stderr)
    
    print(f"\n[mcp-ios] ❌ 非基础组件 - 已过滤 ({len(filtered)} 个):", file=sys.stderr)
    for name in sorted(filtered.keys()):
        mixup_info = " | ".join(filtered[name])
        print(f"    {name}: {mixup_info}", file=sys.stderr)
    print(f"[mcp-ios] ==================================\n", file=sys.stderr)
    
    if not components:
        print(f"[mcp-ios] 未在 {pods_dir} 发现组件", file=sys.stderr)
        return {}

    current_hash = compute_hash(pods_dir, components)
    cache_path = os.path.join(CACHE_DIR, 'index.json')

    # 尝试加载缓存
    if os.path.exists(cache_path):
        try:
            with open(cache_path, encoding='utf-8') as f:
                cached = json.load(f)
            if cached.get('hash') == current_hash:
                print(f"[mcp-ios] 使用缓存索引 ({len(cached['components'])} 个组件)", file=sys.stderr)
                return cached['components']
        except:
            pass

    print(f"[mcp-ios] 构建索引... ({len(components)} 个组件)", file=sys.stderr)
    index = {}
    for dir_name in sorted(components):
        comp_dir = os.path.join(pods_dir, dir_name)
        try:
            spec = parse_podspec(comp_dir, dir_name)
            pod_name = spec.get('pod_name') or dir_name

            all_files = walk_dir(comp_dir)
            source_files = [f for f in all_files if is_source_file(f)]
            apis = []
            for f in source_files:
                apis.extend(extract_apis(os.path.join(comp_dir, f), f))

            # Key by pod name so agents can address components consistently.
            # Keep dir_name for filesystem operations.
            index[pod_name] = {
                'name': pod_name,
                'dir': dir_name,
                'podspec': spec.get('podspec', ''),
                'summary': spec.get('summary', ''),
                'description': spec.get('description', ''),
                'apis': apis,
                'files': all_files,
                'source_count': len(source_files),
            }
            print(f"  ✓ {pod_name} ({dir_name}): {len(apis)} APIs, {len(source_files)} 源文件", file=sys.stderr)
        except Exception as e:
            print(f"  ✗ {dir_name}: {e}", file=sys.stderr)

    # 写缓存
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump({'hash': current_hash, 'components': index}, f, ensure_ascii=False)
    print(f"[mcp-ios] 索引已缓存 ({len(index)} 个组件)", file=sys.stderr)
    return index


# ============================================================
# API Key 管理
# ============================================================

def _hash_api_key(key: str) -> str:
    """对 API Key 进行 SHA256 哈希"""
    return hashlib.sha256(key.encode()).hexdigest()


def load_api_keys() -> dict:
    """加载 API Keys，返回 {hash: name} 字典"""
    keys = {}
    env_keys = os.environ.get("MCP_API_KEYS", "")
    if env_keys:
        for k in env_keys.split(","):
            k = k.strip()
            if k:
                keys[_hash_api_key(k)] = "(env)"
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if ":" in line:
                        name, key_or_hash = line.split(":", 1)
                        key_or_hash = key_or_hash.strip()
                        # 判断是否已经是 hash（64位hex）还是原始 key
                        if len(key_or_hash) == 64 and all(c in '0123456789abcdef' for c in key_or_hash):
                            keys[key_or_hash] = name.strip()
                        else:
                            # 兼容旧格式：原始 key，计算 hash
                            keys[_hash_api_key(key_or_hash)] = name.strip()
                    else:
                        if len(line) == 64 and all(c in '0123456789abcdef' for c in line):
                            keys[line] = "(unnamed)"
                        else:
                            keys[_hash_api_key(line)] = "(unnamed)"
    return keys


def validate_api_key(provided_key: str, valid_keys: dict) -> bool:
    """常量时间 API Key 验证，防止时序攻击"""
    if not valid_keys:
        return True  # 无 key 配置则允许
    provided_hash = _hash_api_key(provided_key)
    # 使用 hmac.compare_digest 进行常量时间比较
    for stored_hash in valid_keys:
        if hmac.compare_digest(provided_hash, stored_hash):
            return True
    return False


def generate_api_key(name: str = "") -> str:
    """生成新 API Key，存储 hash 而非明文"""
    key = f"sk-btp-{secrets.token_hex(24)}"
    key_hash = _hash_api_key(key)
    os.makedirs(os.path.dirname(KEYS_FILE) or ".", exist_ok=True)
    with open(KEYS_FILE, "a") as f:
        f.write(f"{name}:{key_hash}\n" if name else f"{key_hash}\n")
    os.chmod(KEYS_FILE, 0o600)
    return key  # 仅在生成时返回明文，之后无法恢复


def list_api_keys() -> list:
    """列出 API Keys（仅显示名称，不显示任何 key 信息）"""
    if not os.path.exists(KEYS_FILE):
        return []
    result = []
    with open(KEYS_FILE) as f:
        idx = 0
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            idx += 1
            if ":" in line:
                name, _ = line.split(":", 1)
                result.append({"id": idx, "name": name.strip() or "(unnamed)"})
            else:
                result.append({"id": idx, "name": "(unnamed)"})
    return result


# ============================================================
# MCP Tools
# ============================================================

@mcp.tool()
def list_components() -> str:
    """列出所有已索引的 iOS 基础组件名称、描述和统计信息。"""
    if not INDEX:
        return "暂无已索引的组件。"
    lines = []
    for comp in sorted(INDEX.values(), key=lambda c: c['name']):
        lines.append(
            f"**{comp['name']}** — {comp['summary'] or '(无描述)'}\n"
            f"  APIs: {len(comp['apis'])}, 源文件: {comp['source_count']}"
        )
    return f"共 {len(INDEX)} 个组件:\n\n" + "\n\n".join(lines)


@mcp.tool()
def get_tool_docs(tool_name: str = "", format: str = "text") -> str:
    """返回 MCP 工具的详细说明（给 agent 用）。

    Best practice: agent 在首次接入服务、或不确定某个工具怎么用时，先调用本工具。

    Args:
        tool_name: 可选。为空时返回所有工具的概览；指定工具名时返回该工具的完整说明。
        format: 返回格式，"text" 或 "json"。

    Returns:
        - format=text: Markdown 文本
        - format=json: JSON 字符串（稳定结构，便于 agent 解析）
    """
    if format not in VALID_FORMATS:
        return f"错误：无效的 format 值，可选: {', '.join(sorted(VALID_FORMATS))}"

    import inspect

    # Tool registry (manually curated to keep output small and stable)
    tools = {
        "list_components": list_components,
        "search_component": search_component,
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
            return f"未知工具：{tool_name}\n可用工具：{available}" if format == "text" else _to_json({"ok": False, "error": "unknown_tool", "tool": tool_name, "available": sorted(tools.keys())})
        payload = {"ok": True, "tool": doc_for(tool_name, fn)}
        return _to_json(payload) if format == "json" else f"# {payload['tool']['name']}\n\n`{payload['tool']['signature']}`\n\n{payload['tool']['doc']}"

    all_docs = [doc_for(n, f) for n, f in tools.items()]
    all_docs = sorted(all_docs, key=lambda x: x["name"])

    if format == "json":
        return _to_json({"ok": True, "tools": all_docs})

    lines = ["# MCP 工具说明", "", "建议调用顺序：search_component -> (get_component_api/get_class_detail) -> read_source -> find_usage_example", ""]
    for t in all_docs:
        one_line = t["doc"].split("\n")[0] if t["doc"] else ""
        lines.append(f"- `{t['name']}`: {one_line}")
    lines.append("\n想看某个工具的完整说明：get_tool_docs(tool_name=\"search_component\")")
    return "\n".join(lines)


# 输入验证常量
MAX_KEYWORD_LEN = 500
MAX_READ_LINES = 500
MAX_API_OUTPUT = 200  # get_component_api 最大输出 API 数
VALID_KINDS = {'interface', 'protocol', 'method', 'property', 'func', 'class', 'struct', 'enum', 'var', 'let', 'typealias', 'init', 'subscript'}
VALID_FORMATS = {"text", "json"}


def _to_json(data) -> str:
    """Serialize as JSON string (stable output for agents)."""
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

@mcp.tool()
def search_component(keyword: str, kind: str = "", format: str = "text", limit: int = 50) -> str:
    """搜索组件中的符号（类名、方法名、属性名、注释等，模糊匹配）。
    
    ⚠️ 实现 UI/网络/图片/工具类功能前必须先调用此工具！

    Args:
        keyword: 搜索关键词（不区分大小写）。建议尝试：
                 - 中文：圆角、缓存、弹窗、网络请求、日期格式化
                 - 英文：corner、cache、toast、request、dateFormat
                 - 类名：UIImage、UIButton、NSString
        kind: 可选过滤，值: interface/protocol/method/property/func/class/struct/enum/var
    
    Returns:
        匹配的 API 列表，包含组件名、文件、行号，可直接用于 read_source
    """
    # 输入验证
    if not keyword or not keyword.strip():
        return "错误：关键词不能为空"
    if len(keyword) > MAX_KEYWORD_LEN:
        return f"错误：关键词过长（最大 {MAX_KEYWORD_LEN} 字符）"
    if kind and kind not in VALID_KINDS:
        return f"错误：无效的 kind 值，可选: {', '.join(sorted(VALID_KINDS))}"
    if format not in VALID_FORMATS:
        return f"错误：无效的 format 值，可选: {', '.join(sorted(VALID_FORMATS))}"

    # limit: keep small by default to avoid context bloat
    try:
        limit = int(limit)
    except Exception:
        limit = 50
    limit = max(1, min(200, limit))

    # 使用快照避免并发问题
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)

    if not index_snapshot:
        return "暂无索引数据。"

    kw = keyword.strip().lower()
    text_results: list[str] = []
    json_results: list[dict] = []

    def add_hit(comp_name: str, api: dict | None, kind_label: str, name: str, declaration: str = "", file: str = "", line: int = 0, comment: str = ""):
        if len(json_results) >= limit:
            return
        comment_preview = ""
        if comment:
            comment_preview = comment.split("\n")[0].strip()

        if api is None:
            text_results.append(f"[组件] {comp_name} — {declaration}")
            json_results.append({
                "component": comp_name,
                "kind": "component",
                "name": comp_name,
                "file": "",
                "line": 0,
                "declaration": declaration,
                "comment_preview": "",
            })
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

        json_results.append({
            "component": comp_name,
            "kind": kind_label,
            "name": name,
            "file": file,
            "line": int(line or 0),
            "declaration": declaration,
            "comment_preview": comment_preview,
        })

    for comp in index_snapshot.values():
        if len(json_results) >= limit:
            break

        # 匹配组件名
        if kw in comp['name'].lower():
            add_hit(comp['name'], None, "component", comp['name'], declaration=(comp.get('summary') or "(无描述)"))

        # 匹配 API
        for api in comp['apis']:
            if len(json_results) >= limit:
                break
            if kind and api['kind'] != kind:
                continue
            if (
                kw in api['name'].lower()
                or kw in api['declaration'].lower()
                or kw in api.get('comment', '').lower()
            ):
                add_hit(
                    comp['name'],
                    api,
                    api['kind'],
                    api['name'],
                    declaration=api['declaration'],
                    file=api['file'],
                    line=api['line'],
                    comment=api.get('comment', ''),
                )

    if not json_results:
        return f"未找到与 \"{keyword}\" 相关的结果" if format == "text" else _to_json({"ok": False, "keyword": keyword, "results": [], "truncated": False, "limit": limit})

    truncated = False
    # We stop searching early once we reach limit; this implies truncation.
    if len(json_results) >= limit:
        truncated = True

    if format == "json":
        return _to_json({"ok": True, "keyword": keyword, "kind": kind, "results": json_results, "truncated": truncated, "limit": limit})

    text = "\n\n".join(text_results)
    if truncated:
        text += f"\n\n... 结果较多，仅显示前 {limit} 条（可用 limit 调大，或用 format=\"json\" 做后续自动化）"
    return text


@mcp.tool()
def get_component_api(component_name: str) -> str:
    """获取指定组件的完整公开 API 列表（按文件分组）。

    Args:
        component_name: 组件名称，如 BTBaseKit、BTNetwork
    """
    # 使用快照避免并发问题
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    
    comp = index_snapshot.get(component_name)
    if not comp:
        available = ", ".join(sorted(index_snapshot.keys()))
        return f"组件 \"{component_name}\" 不存在。可用: {available}"

    if not comp['apis']:
        return f"{component_name} 未发现公开 API 声明"

    # 限制输出大小
    apis_list = comp['apis']
    truncated = False
    if len(apis_list) > MAX_API_OUTPUT:
        apis_list = apis_list[:MAX_API_OUTPUT]
        truncated = True

    # 按文件分组
    by_file = {}
    for api in apis_list:
        by_file.setdefault(api['file'], []).append(api)

    sections = []
    if comp['summary']:
        sections.append(f"# {comp['name']}\n\n{comp['summary']}\n{comp['description']}")

    for file, apis in sorted(by_file.items()):
        decls = []
        for a in apis:
            s = ''
            if a.get('comment'):
                s += a['comment'] + '\n'
            s += a['declaration']
            decls.append(s)
        sections.append(f"## {file}\n\n```\n" + "\n\n".join(decls) + "\n```")

    result = "\n\n".join(sections)
    if truncated:
        result += f"\n\n... 共 {len(comp['apis'])} 个 API，仅显示前 {MAX_API_OUTPUT} 个"
    return result


@mcp.tool()
def get_class_detail(component_name: str, classname: str) -> str:
    """查看某个类/协议的完整信息：定义位置、属性、公开方法、内部方法。

    Args:
        component_name: 组件名称
        classname: 类名，如 BTBaseViewController
    """
    # 使用快照避免并发问题
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    
    comp = index_snapshot.get(component_name)
    if not comp:
        return f"组件 \"{component_name}\" 不存在。"

    apis = comp['apis']
    cn = classname

    # 找定义
    definitions = [a for a in apis if a['name'] == cn and a['kind'] in ('interface', 'protocol', 'class', 'struct', 'enum')]
    # 找方法（scope 通过文件和行号范围推断，或通过名称前缀匹配）
    methods = [a for a in apis if a['kind'] in ('method', 'func') and a['name'] != cn]
    props = [a for a in apis if a['kind'] in ('property', 'var', 'let') and a['name'] != cn]

    # 对于 ObjC，方法归属需要看同一文件
    if definitions:
        def_files = set(d['file'] for d in definitions)
        # 取同文件的方法和属性作为该类的成员
        class_methods = [m for m in methods if m['file'] in def_files]
        class_props = [p for p in props if p['file'] in def_files]
    else:
        class_methods = []
        class_props = []

    if not definitions and not class_methods:
        return f"未找到类 '{cn}' (组件: {component_name})"

    lines = [f"=== {cn} ({component_name}) ==="]

    for d in definitions:
        comment = f"\n  💬 {d['comment'].split(chr(10))[0]}" if d.get('comment') else ''
        lines.append(f"  定义: {d['file']}:{d['line']} ({d['kind']}){comment}")

    if class_props:
        lines.append(f"\n  属性 ({len(class_props)}):")
        for p in class_props:
            comment = f"  💬 {p['comment'].split(chr(10))[0]}" if p.get('comment') else ''
            lines.append(f"    {p['name']:40} {p['file']}:{p['line']}{comment}")

    if class_methods:
        pub = [m for m in class_methods if m['file'].endswith('.h')]
        priv = [m for m in class_methods if not m['file'].endswith('.h')]
        if pub:
            lines.append(f"\n  公开方法 ({len(pub)}):")
            for m in pub:
                lines.append(f"    {m['name']:40} {m['file']}:{m['line']}")
        if priv:
            lines.append(f"\n  内部方法 ({len(priv)}):")
            for m in priv:
                lines.append(f"    {m['name']:40} {m['file']}:{m['line']}")

    return "\n".join(lines)


@mcp.tool()
def read_source(component_name: str, file: str, start: int = 1, end: int = 0) -> str:
    """按需读取组件源码片段。先用 search_component 定位文件和行号，再用此工具读取。

    Args:
        component_name: 组件名称
        file: 文件相对路径（从搜索结果中获取），支持模糊匹配文件名
        start: 起始行号（默认 1）
        end: 结束行号（默认 start+50）
    """
    # 输入验证
    if not component_name or not component_name.strip():
        return "错误：组件名不能为空"
    if not file or not file.strip():
        return "错误：文件路径不能为空"
    
    # 防止路径遍历攻击：检查是否包含可疑字符
    if '..' in file or file.startswith('/') or '..' in component_name:
        return "错误：非法路径"
    
    comp = INDEX.get(component_name)
    if not comp:
        return "组件不存在"  # 不暴露具体组件名

    # 精确匹配 → 后缀匹配 → 模糊匹配（仅在已索引文件列表中查找）
    fn_lower = file.lower()
    match = None
    for f in comp['files']:
        if f == file:
            match = f
            break
    if not match:
        for f in comp['files']:
            if f.lower().endswith(fn_lower):
                match = f
                break
    if not match:
        for f in comp['files']:
            if fn_lower in f.lower():
                match = f
                break

    if not match:
        source_files = sorted(f for f in comp['files'] if is_source_file(f))
        return "文件未找到。\n\n可用源文件:\n" + "\n".join(f"  - {f}" for f in source_files[:30])

    # 路径安全验证：确保最终路径在允许范围内
    comp_dir = comp.get('dir') or component_name

    filepath = os.path.realpath(os.path.join(PODS_DIR, comp_dir, match))
    allowed_base = os.path.realpath(os.path.join(PODS_DIR, comp_dir))
    if not filepath.startswith(allowed_base + os.sep) and filepath != allowed_base:
        return "错误：禁止访问此路径"
    
    if not os.path.exists(filepath):
        return "文件不存在"  # 通用错误消息

    if end <= 0:
        end = start + 50
    
    # 限制单次最大读取行数
    if end - start > MAX_READ_LINES:
        return f"错误：单次最多读取 {MAX_READ_LINES} 行"
    
    # 验证 start <= end
    if start > end:
        return "错误：起始行号不能大于结束行号"

    with open(filepath, encoding='utf-8', errors='ignore') as f:
        all_lines = f.readlines()

    total = len(all_lines)
    start = max(1, start)
    end = min(end, total)

    result = [f"=== {match} [L{start}-{end}/{total}] ==="]
    for i in range(start - 1, end):
        result.append(f"{i+1:4d}: {all_lines[i].rstrip()}")
    return "\n".join(result)


@mcp.tool()
def refresh_index() -> str:
    """手动触发检查组件仓库更新并重建索引。当你怀疑组件有更新时调用。"""
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
    """查看定时检查状态和最近的更新日志。"""
    lines = []

    # 定时检查状态
    if WATCH_INTERVAL > 0:
        lines.append(f"🔄 定时检查: 每 {WATCH_INTERVAL} 秒")
    else:
        lines.append("⏸️ 定时检查: 未启用")

    # Git 仓库
    repos = discover_git_repos(PODS_DIR)
    lines.append(f"📦 监控仓库: {len(repos)} 个")
    for repo in repos:
        name = os.path.basename(repo) or "root"
        lines.append(f"  - {name}")

    # 索引状态
    with INDEX_LOCK:
        count = len(INDEX)
    lines.append(f"\n📊 当前索引: {count} 个组件")

    # 最近日志
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
    """根据配置文件同步组件代码（git clone/pull）。

    Args:
        config_path: 配置文件路径（默认 components.yaml）
    """
    if not config_path:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "components.yaml")
    
    if not os.path.exists(config_path):
        return f"配置文件不存在: {config_path}\n\n请创建 components.yaml，格式示例:\n```yaml\ncomponents:\n  BTBaseKit:\n    repo: git@gitlab.com:ios/BTBaseKit.git\n    branch: main\n```"
    
    results = sync_components(config_path, PODS_DIR)
    
    if not results:
        return "无组件需要同步"
    
    # 格式化输出
    lines = ["📦 组件同步结果:\n"]
    for r in results:
        status_icon = {"cloned": "✅", "updated": "🔄", "skip": "⏭️", "error": "❌"}.get(r["status"], "❓")
        lines.append(f"{status_icon} **{r['name']}**: {r['message']}")
    
    cloned = sum(1 for r in results if r["status"] == "cloned")
    updated = sum(1 for r in results if r["status"] == "updated")
    errors = sum(1 for r in results if r["status"] == "error")
    
    lines.append(f"\n📊 统计: {cloned} 克隆, {updated} 更新, {errors} 错误")
    
    # 如果有新组件，触发重建索引
    if cloned > 0:
        lines.append("\n🔄 检测到新组件，正在重建索引...")
        global INDEX, LAST_HASH
        # 删除缓存
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
    """从 GitLab group 自动发现并同步基础组件。
    
    自动检查每个仓库的 podspec，只同步不含 MIXUP 声明（或为空数组）的基础组件。

    Args:
        group_id: GitLab group ID 或 path（如 "ios-team" 或 "123"）
        gitlab_url: GitLab 服务器地址（默认使用环境变量 GITLAB_URL）
        gitlab_token: GitLab API Token（默认使用环境变量 GITLAB_TOKEN）
        use_ssh: 是否使用 SSH 地址克隆（默认 True）
    """
    token = gitlab_token or GITLAB_TOKEN
    if not token:
        return "错误：未配置 GitLab Token。请设置 GITLAB_TOKEN 环境变量或传入 gitlab_token 参数。"
    
    results = sync_gitlab_group(group_id, PODS_DIR, gitlab_url, token, use_ssh)
    
    if not results:
        return "未找到仓库或获取失败"
    
    # 格式化输出
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
        # 只显示前 10 个
        lines.extend(skipped[:10])
        if len(skipped) > 10:
            lines.append(f"... 还有 {len(skipped) - 10} 个")
    
    cloned = sum(1 for r in results if r["status"] == "cloned")
    updated = sum(1 for r in results if r["status"] == "updated")
    errors = sum(1 for r in results if r["status"] == "error")
    
    lines.append(f"\n📊 统计: {len(base_components)} 基础组件 ({cloned} 克隆, {updated} 更新, {errors} 错误), {len(skipped)} 已跳过")
    
    # 如果有新组件，触发重建索引
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
    """在其他组件中搜索该组件的使用示例（import/引用），帮助理解组件用法。

    Args:
        component_name: 组件名称
    """
    # 使用快照避免并发问题
    with INDEX_LOCK:
        index_snapshot = dict(INDEX)
    
    if component_name not in index_snapshot:
        return f"\"{component_name}\" 不在已索引组件中。"

    import_patterns = [
        f'import {component_name}',
        f'@import {component_name}',
        f'#import <{component_name}/',
        f'#import "{component_name}/',
    ]

    results = []
    for other_name, other_comp in index_snapshot.items():
        if other_name == component_name:
            continue
        other_dir = os.path.join(PODS_DIR, other_comp.get('dir') or other_name)
        source_files = [f for f in other_comp.get('files', []) if is_source_file(f)]

        for rel in source_files:
            full_path = os.path.join(other_dir, rel)
            try:
                with open(full_path, encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except:
                continue

            if not any(p in content for p in import_patterns):
                continue

            # 提取相关行
            relevant = []
            for j, line in enumerate(content.split('\n')):
                if any(p in line for p in import_patterns) or component_name in line:
                    relevant.append(f"  L{j+1}: {line.strip()}")
                    if len(relevant) >= 10:
                        break

            if relevant:
                results.append(f"### {other_name}/{rel}\n" + "\n".join(relevant))

    if not results:
        return f"未在其他组件中找到 {component_name} 的使用示例"

    limited = results[:20]
    text = "\n\n".join(limited)
    if len(results) > 20:
        text += f"\n\n... 共 {len(results)} 处引用，仅显示前 20 处"
    return text


# ============================================================
# Webhook & 热更新
# ============================================================

def reindex():
    """重新拉取代码并重建索引（带并发保护）"""
    global INDEX, LAST_HASH
    
    # 并发保护：防止同时运行多个 reindex
    if not REINDEX_LOCK.acquire(blocking=False):
        print("[mcp-ios] ⚠️ reindex 已在运行，跳过本次请求", file=sys.stderr)
        return
    
    try:
        print("[mcp-ios] 🔄 webhook 触发重建索引...", file=sys.stderr)

        # git pull（如果 PODS_DIR 是 git 仓库）
        git_dir = os.path.join(PODS_DIR, ".git")
        if os.path.isdir(git_dir):
            try:
                result = subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=PODS_DIR, capture_output=True, text=True, timeout=120,
                )
                print(f"[mcp-ios] git pull: {result.stdout.strip()}", file=sys.stderr)
                if result.returncode != 0:
                    print(f"[mcp-ios] git pull stderr: {result.stderr.strip()}", file=sys.stderr)
            except Exception as e:
                print(f"[mcp-ios] git pull 失败: {e}", file=sys.stderr)

        # 删除缓存强制重建
        cache_path = os.path.join(CACHE_DIR, "index.json")
        if os.path.exists(cache_path):
            os.remove(cache_path)

        new_index = build_index(PODS_DIR)
        with INDEX_LOCK:
            INDEX = new_index
        components = discover_components(PODS_DIR)
        LAST_HASH = compute_hash(PODS_DIR, components)
        print(f"[mcp-ios] ✅ 索引已更新 ({len(new_index)} 个组件)", file=sys.stderr)
    finally:
        REINDEX_LOCK.release()


# ============================================================
# 定时检查 & 多仓库更新
# ============================================================

def discover_git_repos(pods_dir: str) -> list:
    """发现 pods_dir 下的所有 git 仓库（包括根目录和子目录）"""
    repos = []
    # 检查根目录
    if os.path.isdir(os.path.join(pods_dir, ".git")):
        repos.append(pods_dir)
    # 检查一级子目录（每个组件可能是独立仓库）
    try:
        for entry in os.listdir(pods_dir):
            entry_path = os.path.join(pods_dir, entry)
            if os.path.isdir(entry_path) and os.path.isdir(os.path.join(entry_path, ".git")):
                repos.append(entry_path)
    except OSError:
        pass
    return repos


def git_pull_repo(repo_path: str) -> dict:
    """对单个仓库执行 git fetch + diff 检查 + pull"""
    result = {"path": repo_path, "updated": False, "changes": [], "error": None}
    repo_name = os.path.basename(repo_path) or "root"

    try:
        # fetch 远程
        fetch = subprocess.run(
            ["git", "fetch", "--quiet"],
            cwd=repo_path, capture_output=True, text=True, timeout=60,
        )
        if fetch.returncode != 0:
            result["error"] = f"fetch failed: {fetch.stderr.strip()}"
            return result

        # 检查当前分支
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, timeout=10,
        )
        current_branch = branch.stdout.strip() or "main"

        # 比较本地和远程
        diff_stat = subprocess.run(
            ["git", "diff", "--stat", f"HEAD..origin/{current_branch}"],
            cwd=repo_path, capture_output=True, text=True, timeout=30,
        )
        diff_output = diff_stat.stdout.strip()

        if not diff_output:
            return result  # 无更新

        # 有更新，拉取
        pull = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=repo_path, capture_output=True, text=True, timeout=120,
        )
        if pull.returncode != 0:
            result["error"] = f"pull failed: {pull.stderr.strip()}"
            return result

        result["updated"] = True
        # 解析变更文件
        for line in diff_output.split('\n'):
            line = line.strip()
            if line and '|' in line:
                filename = line.split('|')[0].strip()
                result["changes"].append(filename)

        print(f"[mcp-ios] ✅ {repo_name}: {len(result['changes'])} 文件更新", file=sys.stderr)

    except subprocess.TimeoutExpired:
        result["error"] = "timeout"
    except Exception as e:
        result["error"] = str(e)

    return result


def check_for_updates() -> dict:
    """检查所有仓库更新，有变更则重建索引"""
    global INDEX, LAST_HASH, WATCH_LOG

    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {"time": timestamp, "repos": [], "reindexed": False}

    repos = discover_git_repos(PODS_DIR)
    any_updated = False

    for repo in repos:
        result = git_pull_repo(repo)
        repo_name = os.path.basename(result["path"]) or "root"
        if result["error"]:
            print(f"[mcp-ios] ⚠️ {repo_name}: {result['error']}", file=sys.stderr)
        if result["updated"]:
            any_updated = True
        log_entry["repos"].append({
            "name": repo_name,
            "updated": result["updated"],
            "changes": len(result["changes"]),
            "error": result["error"],
        })

    # 即使 git 没有变更，也检查文件系统变更（有人可能直接修改文件）
    if not any_updated:
        components = discover_components(PODS_DIR)
        current_hash = compute_hash(PODS_DIR, components)
        if current_hash != LAST_HASH and LAST_HASH:
            any_updated = True
            print(f"[mcp-ios] 🔍 检测到文件系统变更", file=sys.stderr)

    if any_updated:
        # 删除缓存强制重建
        cache_path = os.path.join(CACHE_DIR, "index.json")
        if os.path.exists(cache_path):
            os.remove(cache_path)

        new_index = build_index(PODS_DIR)
        with INDEX_LOCK:
            INDEX = new_index
        # 更新 hash
        components = discover_components(PODS_DIR)
        LAST_HASH = compute_hash(PODS_DIR, components)

        log_entry["reindexed"] = True
        print(f"[mcp-ios] ✅ 索引已更新 ({len(new_index)} 个组件)", file=sys.stderr)
    else:
        print(f"[mcp-ios] ℹ️ 无更新", file=sys.stderr)

    # 记录日志
    WATCH_LOG.append(log_entry)
    if len(WATCH_LOG) > WATCH_LOG_MAX:
        WATCH_LOG.pop(0)

    return log_entry


def watch_loop(interval: int):
    """后台定时检查循环"""
    import time
    print(f"[mcp-ios] 🔄 定时检查已启动，间隔 {interval} 秒", file=sys.stderr)
    while True:
        time.sleep(interval)
        try:
            check_for_updates()
        except Exception as e:
            print(f"[mcp-ios] ❌ 定时检查异常: {e}", file=sys.stderr)


REINDEX_LOCK = threading.Lock()  # reindex 并发锁


# ============================================================
# 组件配置同步
# ============================================================

COMPONENTS_CONFIG_FILE = os.environ.get("IOS_PODS_CONFIG", "components.yaml")

def load_components_config(config_path: str) -> dict:
    """加载组件配置文件（YAML 或 JSON）"""
    if not os.path.exists(config_path):
        return {}
    
    with open(config_path, encoding='utf-8') as f:
        content = f.read()
    
    if config_path.endswith('.yaml') or config_path.endswith('.yml'):
        try:
            import yaml
            return yaml.safe_load(content) or {}
        except ImportError:
            print("[mcp-ios] ⚠️ 需要安装 pyyaml: pip install pyyaml", file=sys.stderr)
            return {}
    else:
        return json.loads(content)


def sync_component(name: str, config: dict, target_dir: str) -> dict:
    """同步单个组件"""
    result = {"name": name, "status": "unknown", "message": ""}
    
    repo = config.get("repo") or config.get("url")
    branch = config.get("branch", "main")
    
    if not repo:
        result["status"] = "skip"
        result["message"] = "无 repo 配置"
        return result
    
    comp_dir = os.path.join(target_dir, name)
    
    try:
        if os.path.exists(comp_dir):
            # 已存在，执行 git pull
            if os.path.isdir(os.path.join(comp_dir, ".git")):
                # 切换到目标分支
                subprocess.run(
                    ["git", "checkout", branch],
                    cwd=comp_dir, capture_output=True, timeout=30,
                )
                # 拉取更新
                pull = subprocess.run(
                    ["git", "pull", "--ff-only"],
                    cwd=comp_dir, capture_output=True, text=True, timeout=120,
                )
                if pull.returncode == 0:
                    result["status"] = "updated"
                    result["message"] = pull.stdout.strip() or "Already up to date"
                else:
                    result["status"] = "error"
                    result["message"] = pull.stderr.strip()
            else:
                result["status"] = "skip"
                result["message"] = "目录存在但非 git 仓库"
        else:
            # 不存在，执行 git clone
            clone = subprocess.run(
                ["git", "clone", "--branch", branch, "--single-branch", repo, name],
                cwd=target_dir, capture_output=True, text=True, timeout=300,
            )
            if clone.returncode == 0:
                result["status"] = "cloned"
                result["message"] = f"从 {repo} 克隆成功"
            else:
                result["status"] = "error"
                result["message"] = clone.stderr.strip()
    
    except subprocess.TimeoutExpired:
        result["status"] = "error"
        result["message"] = "操作超时"
    except Exception as e:
        result["status"] = "error"
        result["message"] = str(e)
    
    return result


def sync_components(config_path: str, target_dir: str) -> list:
    """根据配置文件同步所有组件"""
    config = load_components_config(config_path)
    
    if not config:
        print(f"[mcp-ios] ⚠️ 配置文件为空或不存在: {config_path}", file=sys.stderr)
        return []
    
    components = config.get("components", {})
    if not components:
        print(f"[mcp-ios] ⚠️ 配置文件中无 components 定义", file=sys.stderr)
        return []
    
    os.makedirs(target_dir, exist_ok=True)
    
    results = []
    print(f"[mcp-ios] 🔄 开始同步 {len(components)} 个组件...", file=sys.stderr)
    
    for name, comp_config in components.items():
        if isinstance(comp_config, str):
            # 简化格式：name: "repo_url"
            comp_config = {"repo": comp_config}
        
        result = sync_component(name, comp_config, target_dir)
        results.append(result)
        
        status_icon = {
            "cloned": "✅",
            "updated": "🔄",
            "skip": "⏭️",
            "error": "❌",
        }.get(result["status"], "❓")
        
        print(f"  {status_icon} {name}: {result['message']}", file=sys.stderr)
    
    # 统计
    cloned = sum(1 for r in results if r["status"] == "cloned")
    updated = sum(1 for r in results if r["status"] == "updated")
    errors = sum(1 for r in results if r["status"] == "error")
    
    print(f"[mcp-ios] 📊 同步完成: {cloned} 克隆, {updated} 更新, {errors} 错误", file=sys.stderr)
    
    return results


# ============================================================
# GitLab Group 自动发现
# ============================================================

GITLAB_URL = os.environ.get("GITLAB_URL", "https://gitlab.com")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", "")

def fetch_gitlab_group_repos(group_id: str, gitlab_url: str = "", gitlab_token: str = "") -> list:
    """从 GitLab 获取指定 group 下的所有仓库"""
    import urllib.request
    import urllib.error
    
    base_url = gitlab_url or GITLAB_URL
    token = gitlab_token or GITLAB_TOKEN
    
    if not token:
        print("[mcp-ios] ⚠️ 未配置 GITLAB_TOKEN", file=sys.stderr)
        return []
    
    repos = []
    page = 1
    per_page = 100
    
    while True:
        url = f"{base_url}/api/v4/groups/{group_id}/projects?per_page={per_page}&page={page}&include_subgroups=true"
        
        req = urllib.request.Request(url)
        req.add_header("PRIVATE-TOKEN", token)
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
                
                if not data:
                    break
                
                for project in data:
                    repos.append({
                        "id": project["id"],
                        "name": project["name"],
                        "path": project["path"],
                        "ssh_url": project.get("ssh_url_to_repo", ""),
                        "http_url": project.get("http_url_to_repo", ""),
                        "default_branch": project.get("default_branch", "main"),
                    })
                
                page += 1
                
                # 检查是否还有下一页
                if len(data) < per_page:
                    break
                    
        except urllib.error.HTTPError as e:
            print(f"[mcp-ios] ❌ GitLab API 错误: {e.code} {e.reason}", file=sys.stderr)
            break
        except Exception as e:
            print(f"[mcp-ios] ❌ 请求失败: {e}", file=sys.stderr)
            break
    
    return repos


def check_repo_is_base_component(repo_url: str, branch: str = "main", gitlab_token: str = "") -> tuple:
    """检查仓库是否为基础组件（通过检查 podspec 中的 MIXUP 声明）
    
    Returns:
        (is_base_component, podspec_name, reason)
    """
    import urllib.request
    import urllib.error
    import base64
    
    token = gitlab_token or GITLAB_TOKEN
    
    # 从 URL 提取项目路径
    # ssh: git@gitlab.com:group/project.git
    # http: https://gitlab.com/group/project.git
    if repo_url.startswith("git@"):
        # git@gitlab.com:group/project.git -> group/project
        path = repo_url.split(":")[-1].replace(".git", "")
    else:
        # https://gitlab.com/group/project.git -> group/project
        path = "/".join(repo_url.split("/")[-2:]).replace(".git", "")
    
    project_encoded = path.replace("/", "%2F")
    base_url = GITLAB_URL
    
    # 获取仓库文件列表（根目录）
    url = f"{base_url}/api/v4/projects/{project_encoded}/repository/tree?ref={branch}&per_page=100"
    
    req = urllib.request.Request(url)
    if token:
        req.add_header("PRIVATE-TOKEN", token)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            files = json.loads(response.read().decode())
    except Exception as e:
        return (False, None, f"无法获取文件列表: {e}")
    
    # 查找 podspec 文件
    podspec_file = None
    for f in files:
        if f["name"].endswith(".podspec") and f["type"] == "blob":
            podspec_file = f["name"]
            break
    
    if not podspec_file:
        return (False, None, "无 podspec 文件")
    
    # 获取 podspec 内容
    file_encoded = podspec_file.replace("/", "%2F")
    url = f"{base_url}/api/v4/projects/{project_encoded}/repository/files/{file_encoded}/raw?ref={branch}"
    
    req = urllib.request.Request(url)
    if token:
        req.add_header("PRIVATE-TOKEN", token)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            content = response.read().decode('utf-8', errors='ignore')
    except Exception as e:
        return (False, podspec_file, f"无法读取 podspec: {e}")
    
    # 检查 MIXUP 声明
    has_nonempty_mixup = False
    mixup_values = []
    
    for line in content.split('\n'):
        stripped = line.strip()
        if stripped.startswith('#') or stripped.startswith('//'):
            continue
        
        mixup_match = re.search(r'((?:SUPPORT_MIXUP|BETA_SUPPORT_MIXUP)\s*=\s*\[[^\]]*\])', stripped)
        if mixup_match:
            mixup_values.append(mixup_match.group(1))
            array_match = re.search(r'=\s*\[([^\]]*)\]', mixup_match.group(1))
            if array_match:
                array_content = array_match.group(1).strip()
                if array_content:
                    has_nonempty_mixup = True
    
    if has_nonempty_mixup:
        return (False, podspec_file, f"非基础组件: {', '.join(mixup_values)}")
    
    return (True, podspec_file, "基础组件")


def sync_gitlab_group(group_id: str, target_dir: str, gitlab_url: str = "", gitlab_token: str = "", use_ssh: bool = True) -> list:
    """从 GitLab group 自动发现并同步基础组件
    
    Args:
        group_id: GitLab group ID 或 path (如 "ios-team" 或 "123")
        target_dir: 目标目录
        gitlab_url: GitLab 服务器地址
        gitlab_token: GitLab API Token
        use_ssh: 是否使用 SSH 地址克隆（默认 True）
    """
    print(f"[mcp-ios] 🔍 正在从 GitLab group '{group_id}' 获取仓库列表...", file=sys.stderr)
    
    repos = fetch_gitlab_group_repos(group_id, gitlab_url, gitlab_token)
    
    if not repos:
        print(f"[mcp-ios] ⚠️ 未找到仓库或获取失败", file=sys.stderr)
        return []
    
    print(f"[mcp-ios] 📦 发现 {len(repos)} 个仓库，正在检查是否为基础组件...", file=sys.stderr)
    
    os.makedirs(target_dir, exist_ok=True)
    
    results = []
    base_count = 0
    skip_count = 0
    
    for repo in repos:
        name = repo["path"]
        repo_url = repo["ssh_url"] if use_ssh else repo["http_url"]
        branch = repo["default_branch"]
        
        # 检查是否为基础组件
        is_base, podspec, reason = check_repo_is_base_component(
            repo_url, branch, gitlab_token or GITLAB_TOKEN
        )
        
        if not is_base:
            print(f"  ⏭️ {name}: {reason}", file=sys.stderr)
            results.append({"name": name, "status": "skip", "message": reason})
            skip_count += 1
            continue
        
        base_count += 1
        
        # 同步基础组件
        result = sync_component(name, {"repo": repo_url, "branch": branch}, target_dir)
        results.append(result)
        
        status_icon = {"cloned": "✅", "updated": "🔄", "skip": "⏭️", "error": "❌"}.get(result["status"], "❓")
        print(f"  {status_icon} {name}: {result['message']}", file=sys.stderr)
    
    cloned = sum(1 for r in results if r["status"] == "cloned")
    updated = sum(1 for r in results if r["status"] == "updated")
    errors = sum(1 for r in results if r["status"] == "error")
    
    print(f"[mcp-ios] 📊 完成: {base_count} 基础组件 ({cloned} 克隆, {updated} 更新, {errors} 错误), {skip_count} 非基础组件已跳过", file=sys.stderr)
    
    return results


def verify_gitlab_signature(body: bytes, signature: str) -> bool:
    """验证 GitLab webhook X-Gitlab-Token"""
    if not WEBHOOK_SECRET:
        print("[mcp-ios] ⚠️ Webhook 请求被拒绝：未配置 WEBHOOK_SECRET", file=sys.stderr)
        return False  # 未配置 secret 则拒绝所有请求
    return hmac.compare_digest(signature, WEBHOOK_SECRET)


# ============================================================
# 启动
# ============================================================

def main():
    global PODS_DIR, INDEX, LAST_HASH, WATCH_INTERVAL, WEBHOOK_SECRET

    parser = argparse.ArgumentParser(description="iOS Components MCP Server")
    parser.add_argument("pods_dir", nargs="?", default=DEFAULT_PODS_DIR, help="组件库根目录")
    parser.add_argument("--http", action="store_true", help="HTTP 模式启动")
    parser.add_argument("--port", type=int, default=8900, help="HTTP 端口（默认 8900）")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP 监听地址")
    parser.add_argument("--api-keys", help="API Keys（逗号分隔）")
    parser.add_argument("--gen-key", metavar="NAME", help="生成新 API Key")
    parser.add_argument("--list-keys", action="store_true", help="列出已注册 API Keys")
    parser.add_argument("--webhook-secret", help="GitLab Webhook Secret Token")
    parser.add_argument("--watch", type=int, metavar="SECONDS", default=0,
                        help="定时检查间隔（秒），如 --watch 300 表示每 5 分钟检查一次")
    parser.add_argument("--sync", metavar="CONFIG", nargs="?", const="components.yaml",
                        help="根据配置文件同步组件代码（默认 components.yaml）")
    parser.add_argument("--sync-only", action="store_true",
                        help="仅同步，不启动服务")
    parser.add_argument("--gitlab-group", metavar="GROUP",
                        help="从 GitLab group 自动发现并同步基础组件")
    parser.add_argument("--gitlab-url", default="",
                        help="GitLab 服务器地址（默认 https://gitlab.com 或 GITLAB_URL 环境变量）")
    parser.add_argument("--gitlab-token", default="",
                        help="GitLab API Token（或设置 GITLAB_TOKEN 环境变量）")
    parser.add_argument("--use-https", action="store_true",
                        help="使用 HTTPS 地址克隆（默认使用 SSH）")

    args = parser.parse_args()
    PODS_DIR = args.pods_dir

    # Key 管理
    if args.gen_key:
        key = generate_api_key(args.gen_key)
        print(f"✅ 已生成 API Key (name: {args.gen_key}):\n   {key}")
        print(f"\n   Claude Code 远程连接:")
        print(f'   claude mcp add --transport http ios-components http://your-server:{args.port}/mcp \\')
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

    # 组件同步（配置文件）
    if args.sync:
        config_path = args.sync
        if not os.path.isabs(config_path):
            # 相对路径基于脚本目录
            config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_path)
        
        results = sync_components(config_path, PODS_DIR)
        
        if args.sync_only:
            # 仅同步，不启动服务
            errors = sum(1 for r in results if r["status"] == "error")
            sys.exit(1 if errors > 0 else 0)

    # GitLab group 自动发现同步
    if args.gitlab_group:
        if args.gitlab_url:
            global GITLAB_URL
            GITLAB_URL = args.gitlab_url
        if args.gitlab_token:
            global GITLAB_TOKEN
            GITLAB_TOKEN = args.gitlab_token
        
        results = sync_gitlab_group(
            args.gitlab_group,
            PODS_DIR,
            args.gitlab_url,
            args.gitlab_token,
            use_ssh=not args.use_https
        )
        
        if args.sync_only:
            errors = sum(1 for r in results if r["status"] == "error")
            sys.exit(1 if errors > 0 else 0)

    if args.api_keys:
        os.environ["MCP_API_KEYS"] = args.api_keys
    if args.webhook_secret:
        WEBHOOK_SECRET = args.webhook_secret

    # 构建索引
    INDEX = build_index(PODS_DIR)

    # 记录初始 hash
    components = discover_components(PODS_DIR)
    LAST_HASH = compute_hash(PODS_DIR, components)

    # 启动定时检查
    watch_interval = args.watch or WATCH_INTERVAL
    if watch_interval > 0:
        WATCH_INTERVAL = watch_interval
        watcher = threading.Thread(target=watch_loop, args=(watch_interval,), daemon=True)
        watcher.start()

    if args.http:
        import uvicorn
        from contextlib import asynccontextmanager
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Route, Mount
        from starlette.requests import Request

        valid_keys = load_api_keys()
        mcp_app = mcp.streamable_http_app()

        @asynccontextmanager
        async def lifespan(app):
            """Initialize MCP session manager task group"""
            async with mcp_app.router.lifespan_context(app):
                yield

        async def webhook_gitlab(request: Request):
            """GitLab webhook: push 事件触发重新拉取 & 重建索引"""
            # 验证 token
            token = request.headers.get("X-Gitlab-Token", "")
            if not verify_gitlab_signature(b"", token):
                return JSONResponse({"error": "Forbidden"}, status_code=403)

            try:
                body = await request.json()
            except Exception:
                return JSONResponse({"error": "Invalid JSON"}, status_code=400)

            event = request.headers.get("X-Gitlab-Event", "")
            object_kind = body.get("object_kind", "")

            # 只处理 push 事件
            if event != "Push Hook" and object_kind != "push":
                return JSONResponse({"message": f"Ignored event: {event or object_kind}"})

            ref = body.get("ref", "")
            project = body.get("project", {}).get("name", "unknown")
            commits = len(body.get("commits", []))
            print(f"[mcp-ios] 📦 GitLab push: {project} ({ref}), {commits} commit(s)", file=sys.stderr)

            # 后台线程执行重建，避免阻塞 webhook 响应
            threading.Thread(target=reindex, daemon=True).start()

            return JSONResponse({
                "message": "Reindex triggered",
                "project": project,
                "ref": ref,
                "commits": commits,
            })

        async def webhook_health(request: Request):
            """Webhook 健康检查"""
            with INDEX_LOCK:
                count = len(INDEX)
            return JSONResponse({"status": "ok", "components": count})

        async def auth_mcp_app(scope, receive, send):
            """MCP ASGI app with API Key auth（使用常量时间比较防止时序攻击）"""
            if scope["type"] == "http":
                headers = dict(scope.get("headers", []))
                auth_value = headers.get(b"authorization", b"").decode()
                api_key = auth_value.replace("Bearer ", "").strip()
                current_keys = load_api_keys()
                if not validate_api_key(api_key, current_keys):
                    response = JSONResponse(
                        {"error": "Unauthorized", "message": "Invalid or missing API key"},
                        status_code=401
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

        print(f"🚀 iOS Components MCP Server (HTTP)")
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
