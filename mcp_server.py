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

# 运行时赋值
PODS_DIR = DEFAULT_PODS_DIR
INDEX: dict = {}

mcp = FastMCP("ios-components", instructions="""iOS CocoaPods component library code index.
Search existing APIs before writing code — reuse, don't reinvent.
Typical flow: search_component → get_class_detail → read_source.
Use find_usage_example to see how components are used across the codebase.

【Priority Rules】
When multiple methods are found, prefer in this order:
1. Category/Extension methods (e.g. UIButton+Extension) — most natural, closest to native API
2. Protocol/Base class methods
3. Helper/Utility classes — lowest priority, use only when no category method exists""")


# ============================================================
# 组件发现 & 索引构建
# ============================================================

def discover_components(pods_dir: str) -> set:
    """自动发现基础组件：扫描含 .podspec 且不含 MIXUP_MARKER 的目录"""
    components = set()
    if not os.path.exists(pods_dir):
        return components
    for entry in os.listdir(pods_dir):
        entry_path = os.path.join(pods_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        specs = [f for f in os.listdir(entry_path) if f.endswith('.podspec')]
        if not specs:
            continue
        spec_content = open(os.path.join(entry_path, specs[0]), encoding='utf-8', errors='ignore').read()
        has_marker = False
        for line in spec_content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('//'):
                continue
            if re.search(rf'(?<![A-Z_]){MIXUP_MARKER}\s*=', stripped):
                has_marker = True
                break
        if not has_marker:
            components.add(entry)
    return components


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
    """从 podspec 提取 summary 和 description"""
    for fname in [f'{name}.podspec', f'{name}.podspec.json']:
        spec_path = os.path.join(pod_dir, fname)
        if not os.path.exists(spec_path):
            continue
        content = open(spec_path, encoding='utf-8', errors='ignore').read()
        summary_m = re.search(r"\.summary\s*=\s*['\"](.+?)['\"]", content)
        desc_m = re.search(r'\.description\s*=\s*<<-DESC\s*([\s\S]*?)\s*DESC', content)
        desc_m2 = re.search(r"\.description\s*=\s*['\"](.+?)['\"]", content)
        return {
            'summary': summary_m.group(1) if summary_m else '',
            'description': (desc_m.group(1).strip() if desc_m else desc_m2.group(1) if desc_m2 else ''),
        }
    return {'summary': '', 'description': ''}


def extract_apis(file_path: str, rel_path: str) -> list:
    """提取 API 声明 + 注释"""
    apis = []
    try:
        content = open(file_path, encoding='utf-8', errors='ignore').read()
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
    components = discover_components(pods_dir)
    if not components:
        print(f"[mcp-ios] 未在 {pods_dir} 发现组件", file=sys.stderr)
        return {}

    current_hash = compute_hash(pods_dir, components)
    cache_path = os.path.join(CACHE_DIR, 'index.json')

    # 尝试加载缓存
    if os.path.exists(cache_path):
        try:
            cached = json.load(open(cache_path))
            if cached.get('hash') == current_hash:
                print(f"[mcp-ios] 使用缓存索引 ({len(cached['components'])} 个组件)", file=sys.stderr)
                return cached['components']
        except:
            pass

    print(f"[mcp-ios] 构建索引... ({len(components)} 个组件)", file=sys.stderr)
    index = {}
    for name in sorted(components):
        comp_dir = os.path.join(pods_dir, name)
        try:
            spec = parse_podspec(comp_dir, name)
            all_files = walk_dir(comp_dir)
            source_files = [f for f in all_files if is_source_file(f)]
            apis = []
            for f in source_files:
                apis.extend(extract_apis(os.path.join(comp_dir, f), f))
            index[name] = {
                'name': name,
                'summary': spec['summary'],
                'description': spec['description'],
                'apis': apis,
                'files': all_files,
                'source_count': len(source_files),
            }
            print(f"  ✓ {name}: {len(apis)} APIs, {len(source_files)} 源文件", file=sys.stderr)
        except Exception as e:
            print(f"  ✗ {name}: {e}", file=sys.stderr)

    # 写缓存
    os.makedirs(CACHE_DIR, exist_ok=True)
    json.dump({'hash': current_hash, 'components': index}, open(cache_path, 'w'), ensure_ascii=False)
    print(f"[mcp-ios] 索引已缓存 ({len(index)} 个组件)", file=sys.stderr)
    return index


# ============================================================
# API Key 管理
# ============================================================

def load_api_keys() -> set:
    keys = set()
    env_keys = os.environ.get("MCP_API_KEYS", "")
    if env_keys:
        keys.update(k.strip() for k in env_keys.split(",") if k.strip())
    if os.path.exists(KEYS_FILE):
        with open(KEYS_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    keys.add(line.split(":")[-1].strip())
    return keys


def generate_api_key(name: str = "") -> str:
    key = f"sk-btp-{secrets.token_hex(24)}"
    os.makedirs(os.path.dirname(KEYS_FILE), exist_ok=True)
    with open(KEYS_FILE, "a") as f:
        f.write(f"{name}:{key}\n" if name else f"{key}\n")
    os.chmod(KEYS_FILE, 0o600)
    return key


def list_api_keys() -> list:
    if not os.path.exists(KEYS_FILE):
        return []
    result = []
    with open(KEYS_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                name, key = line.split(":", 1)
                result.append({"name": name.strip(), "key": key[:10] + "..." + key[-4:]})
            else:
                result.append({"name": "(unnamed)", "key": line[:10] + "..." + line[-4:]})
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
def search_component(keyword: str, kind: str = "") -> str:
    """搜索组件中的符号（类名、方法名、属性名、注释等，模糊匹配）。

    Args:
        keyword: 搜索关键词（不区分大小写）
        kind: 可选过滤，值: interface/protocol/method/property/func/class/struct/enum/var
    """
    if not INDEX:
        return "暂无索引数据。"

    kw = keyword.lower()
    results = []

    for comp in INDEX.values():
        # 匹配组件名
        if kw in comp['name'].lower():
            results.append(f"[组件] {comp['name']} — {comp['summary']}")

        # 匹配 API
        for api in comp['apis']:
            if kind and api['kind'] != kind:
                continue
            if (kw in api['name'].lower() or
                kw in api['declaration'].lower() or
                kw in api.get('comment', '').lower()):
                comment_preview = ''
                if api.get('comment'):
                    first_line = api['comment'].split('\n')[0].strip()
                    comment_preview = f"\n  💬 {first_line}"
                results.append(
                    f"[{comp['name']}] {api['kind']} **{api['name']}**\n"
                    f"  {api['declaration']}\n"
                    f"  📄 {api['file']}:{api['line']}{comment_preview}"
                )

    if not results:
        return f"未找到与 \"{keyword}\" 相关的结果"

    limited = results[:50]
    text = "\n\n".join(limited)
    if len(results) > 50:
        text += f"\n\n... 共 {len(results)} 条结果，仅显示前 50 条"
    return text


@mcp.tool()
def get_component_api(component_name: str) -> str:
    """获取指定组件的完整公开 API 列表（按文件分组）。

    Args:
        component_name: 组件名称，如 BTBaseKit、BTNetwork
    """
    comp = INDEX.get(component_name)
    if not comp:
        available = ", ".join(sorted(INDEX.keys()))
        return f"组件 \"{component_name}\" 不存在。可用: {available}"

    if not comp['apis']:
        return f"{component_name} 未发现公开 API 声明"

    # 按文件分组
    by_file = {}
    for api in comp['apis']:
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

    return "\n\n".join(sections)


@mcp.tool()
def get_class_detail(component_name: str, classname: str) -> str:
    """查看某个类/协议的完整信息：定义位置、属性、公开方法、内部方法。

    Args:
        component_name: 组件名称
        classname: 类名，如 BTBaseViewController
    """
    comp = INDEX.get(component_name)
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
    comp = INDEX.get(component_name)
    if not comp:
        return f"组件 \"{component_name}\" 不存在。"

    # 精确匹配 → 后缀匹配 → 模糊匹配
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
        return f"文件 \"{file}\" 未找到。\n\n可用源文件:\n" + "\n".join(f"  - {f}" for f in source_files[:30])

    filepath = os.path.join(PODS_DIR, component_name, match)
    if not os.path.exists(filepath):
        return f"文件不存在: {match}"

    if end <= 0:
        end = start + 50

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
def find_usage_example(component_name: str) -> str:
    """在其他组件中搜索该组件的使用示例（import/引用），帮助理解组件用法。

    Args:
        component_name: 组件名称
    """
    if component_name not in INDEX:
        return f"\"{component_name}\" 不在已索引组件中。"

    import_patterns = [
        f'import {component_name}',
        f'@import {component_name}',
        f'#import <{component_name}/',
        f'#import "{component_name}/',
    ]

    results = []
    for other_name, other_comp in INDEX.items():
        if other_name == component_name:
            continue
        other_dir = os.path.join(PODS_DIR, other_name)
        source_files = [f for f in other_comp.get('files', []) if is_source_file(f)]

        for rel in source_files:
            full_path = os.path.join(other_dir, rel)
            try:
                content = open(full_path, encoding='utf-8', errors='ignore').read()
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
# 启动
# ============================================================

def main():
    global PODS_DIR, INDEX

    parser = argparse.ArgumentParser(description="iOS Components MCP Server")
    parser.add_argument("pods_dir", nargs="?", default=DEFAULT_PODS_DIR, help="组件库根目录")
    parser.add_argument("--http", action="store_true", help="HTTP 模式启动")
    parser.add_argument("--port", type=int, default=8900, help="HTTP 端口（默认 8900）")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP 监听地址")
    parser.add_argument("--api-keys", help="API Keys（逗号分隔）")
    parser.add_argument("--gen-key", metavar="NAME", help="生成新 API Key")
    parser.add_argument("--list-keys", action="store_true", help="列出已注册 API Keys")

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
                print(f"  {k['name']:20} {k['key']}")
        return

    if args.api_keys:
        os.environ["MCP_API_KEYS"] = args.api_keys

    # 构建索引
    INDEX = build_index(PODS_DIR)

    if args.http:
        import uvicorn
        from starlette.responses import JSONResponse

        valid_keys = load_api_keys()
        mcp_app = mcp.streamable_http_app()

        async def auth_app(scope, receive, send):
            if scope["type"] == "http":
                headers = dict(scope.get("headers", []))
                auth_value = headers.get(b"authorization", b"").decode()
                api_key = auth_value.replace("Bearer ", "").strip()
                current_keys = load_api_keys()
                if current_keys and api_key not in current_keys:
                    response = JSONResponse(
                        {"error": "Unauthorized", "message": "Invalid or missing API key"},
                        status_code=401
                    )
                    await response(scope, receive, send)
                    return
            await mcp_app(scope, receive, send)

        print(f"🚀 iOS Components MCP Server (HTTP)")
        print(f"   地址: http://{args.host}:{args.port}")
        print(f"   鉴权: {'✅ 已启用' if valid_keys else '⚠️ 未配置'}")
        print(f"   组件: {len(INDEX)} 个")
        uvicorn.run(auth_app, host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
