"""Podspec and source API parsers."""

from __future__ import annotations

import os
import re


def parse_podspec(pod_dir: str, name: str) -> dict:
    """Extract pod name/summary/description from podspec."""
    candidates = [f"{name}.podspec", f"{name}.podspec.json"]

    try:
        for f in os.listdir(pod_dir):
            if f.endswith(".podspec") and f not in candidates:
                candidates.append(f)
                break
    except Exception:
        pass

    for fname in candidates:
        spec_path = os.path.join(pod_dir, fname)
        if not os.path.exists(spec_path):
            continue
        with open(spec_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()

        name_m = re.search(r"\.name\s*=\s*['\"](.+?)['\"]", content)
        summary_m = re.search(r"\.summary\s*=\s*['\"](.+?)['\"]", content)
        desc_m = re.search(r"\.description\s*=\s*<<-DESC\s*([\s\S]*?)\s*DESC", content)
        desc_m2 = re.search(r"\.description\s*=\s*['\"](.+?)['\"]", content)

        return {
            "pod_name": name_m.group(1) if name_m else name,
            "summary": summary_m.group(1) if summary_m else "",
            "description": (desc_m.group(1).strip() if desc_m else desc_m2.group(1) if desc_m2 else ""),
            "podspec": fname,
        }

    return {"pod_name": name, "summary": "", "description": "", "podspec": ""}


def extract_apis(file_path: str, rel_path: str) -> list:
    """Extract API declarations and nearby comments.

    Supports:
    - ObjC: @interface, @protocol, @property, methods (+/-), inline/extern functions,
      NS_ENUM/NS_OPTIONS, typedef, Category host_class tracking, multi-line method declarations,
      deprecation annotations (NS_DEPRECATED_IOS, __attribute__((deprecated)))
    - Swift: public/open class/struct/protocol/enum/func/var/let/typealias/init/subscript,
      @available(*, deprecated) annotations
    """
    apis = []
    try:
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return apis

    lines = content.split("\n")
    is_swift = file_path.endswith(".swift")
    is_header = file_path.endswith(".h")
    pending_comment = ""

    # ObjC Category/interface 状态追踪
    current_host_class = ""
    current_category = ""

    def _make_api(kind: str, name: str, declaration: str, line_num: int, comment: str = "", **extra) -> dict:
        entry = {
            "kind": kind,
            "name": name,
            "declaration": declaration,
            "file": rel_path,
            "line": line_num,
            "comment": comment,
        }
        # Category 宿主类标记
        if current_host_class and kind not in ("interface", "protocol"):
            entry["host_class"] = current_host_class
            if current_category:
                entry["category"] = current_category
        # 废弃标注提取
        deprecated = _extract_deprecation(declaration)
        if deprecated:
            entry["deprecated"] = deprecated
        entry.update(extra)
        return entry

    i = 0
    while i < len(lines):
        trimmed = lines[i].strip()

        # === 注释收集 ===
        if trimmed.startswith("///"):
            pending_comment += ("\n" if pending_comment else "") + trimmed
            i += 1
            continue

        if trimmed.startswith("/**"):
            block = trimmed
            j = i
            while "*/" not in block and j < len(lines) - 1:
                j += 1
                block += "\n" + lines[j].strip()
            pending_comment = block
            i = j + 1
            continue

        # === Swift 解析 ===
        if is_swift:
            # Swift @available(*, deprecated) 在声明行之前
            m = re.match(
                r"^(?:@\w+(?:\([^)]*\))?\s+)*(?:public|open)\s+(?:(?:class|static|final|override|weak|lazy|nonisolated|@objc(?:\([^)]*\))?)\s+)*"
                r"(class|struct|protocol|enum|func|var|let|typealias|init|subscript)\b(.*)",
                trimmed,
            )
            if m:
                kind = m.group(1)
                rest = m.group(2).strip()
                name = ""
                if kind == "func":
                    fn = re.match(r"^(\w+)", rest)
                    name = fn.group(1) if fn else rest.split("(")[0]
                elif kind == "init":
                    name = "init"
                elif kind in ("var", "let", "typealias"):
                    vn = re.match(r"^(\w+)", rest)
                    name = vn.group(1) if vn else ""
                else:
                    cn = re.match(r"^(\w+)", rest)
                    name = cn.group(1) if cn else ""
                apis.append(_make_api(kind, name, trimmed, i + 1, pending_comment))
                pending_comment = ""
                i += 1
                continue

        # === ObjC Header 解析 ===
        if is_header:
            # @end — 重置 Category 状态
            if trimmed == "@end":
                current_host_class = ""
                current_category = ""
                i += 1
                continue

            # @interface ClassName (CategoryName) — Category
            m = re.match(r"^@interface\s+(\w+)\s*\((\w*)\)", trimmed)
            if m:
                host = m.group(1)
                cat = m.group(2) or ""
                current_host_class = host
                current_category = cat
                apis.append(_make_api("interface", host, trimmed, i + 1, pending_comment,
                                      host_class=host, category=cat))
                pending_comment = ""
                i += 1
                continue

            # @interface ClassName / @protocol ClassName — 普通类/协议
            m = re.match(r"^@(interface|protocol)\s+(\w+)", trimmed)
            if m:
                current_host_class = m.group(2)
                current_category = ""
                apis.append(_make_api(m.group(1), m.group(2), trimmed, i + 1, pending_comment))
                pending_comment = ""
                i += 1
                continue

            # NS_ENUM / NS_OPTIONS
            m = re.match(r"^typedef\s+(?:NS_ENUM|NS_OPTIONS)\s*\([^,]+,\s*(\w+)\)", trimmed)
            if m:
                enum_name = m.group(1)
                enum_decl = trimmed
                enum_line = i + 1
                enum_comment = pending_comment
                pending_comment = ""

                # 添加枚举类型本身
                apis.append(_make_api("enum", enum_name, enum_decl, enum_line, enum_comment))

                # 解析枚举成员（向下扫描直到 }）
                member_comment = ""
                j = i + 1
                while j < len(lines):
                    ml = lines[j].strip()
                    if ml.startswith("///"):
                        member_comment += ("\n" if member_comment else "") + ml
                        j += 1
                        continue
                    if ml.startswith("/**"):
                        block = ml
                        while "*/" not in block and j < len(lines) - 1:
                            j += 1
                            block += "\n" + lines[j].strip()
                        member_comment = block
                        j += 1
                        continue
                    if ml.startswith("}"):
                        i = j
                        break
                    # 枚举成员匹配：EnumValue = xxx, 或 EnumValue,
                    em = re.match(r"^(\w+)\s*(?:=\s*[^,}]+)?[,}]?", ml)
                    if em and em.group(1) and not ml.startswith("//"):
                        apis.append(_make_api("enum_case", em.group(1), ml.rstrip(",").strip(),
                                              j + 1, member_comment, enum_type=enum_name))
                        member_comment = ""
                    elif ml:
                        member_comment = ""
                    j += 1
                else:
                    i = j
                i += 1
                continue

            # typedef block: typedef void (^BlockName)(...)
            m = re.match(r"^typedef\s+.*?\(\s*\^\s*(\w+)\s*\)", trimmed)
            if m:
                apis.append(_make_api("typedef", m.group(1), trimmed, i + 1, pending_comment))
                pending_comment = ""
                i += 1
                continue

            # typedef struct/union/plain: typedef ... Name;
            m = re.match(r"^typedef\s+(?:struct|union)?\s*\w*\s*\{?[^}]*\}?\s*(\w+)\s*;", trimmed)
            if m:
                apis.append(_make_api("typedef", m.group(1), trimmed, i + 1, pending_comment))
                pending_comment = ""
                i += 1
                continue

            # @property — block 类型: @property(...) returnType (^name)(params);
            m = re.match(r"^@property\s*\([^)]*\)\s*\w[\w\s*]*\(\s*\^\s*(\w+)\s*\)", trimmed)
            if m:
                apis.append(_make_api("property", m.group(1), trimmed, i + 1, pending_comment))
                pending_comment = ""
                i += 1
                continue

            # @property — 普通类型
            m = re.match(r"^@property\s*\(([^)]*)\)\s*\S+\s*\*?\s*(\w+)", trimmed)
            if m:
                apis.append(_make_api("property", m.group(2), trimmed, i + 1, pending_comment))
                pending_comment = ""
                i += 1
                continue

            # inline functions
            m = re.match(
                r"^(?:CG_INLINE|NS_INLINE|FOUNDATION_STATIC_INLINE|static\s+(?:__)?inline)\s+\w[\w\s*]*?\b(\w+)\s*\(",
                trimmed,
            )
            if m:
                apis.append(_make_api("func", m.group(1), trimmed, i + 1, pending_comment))
                pending_comment = ""
                i += 1
                continue

            # extern functions
            m = re.match(
                r"^(?:FOUNDATION_EXTERN|UIKIT_EXTERN|extern|OBJC_EXTERN)\s+.*?\b(\w+)\s*\(",
                trimmed,
            )
            if m:
                apis.append(_make_api("func", m.group(1), trimmed, i + 1, pending_comment))
                pending_comment = ""
                i += 1
                continue

            # ObjC 方法（支持多行声明）
            if trimmed.startswith("-") or trimmed.startswith("+"):
                method_decl = trimmed
                method_line = i + 1
                # 多行合并：如果当前行没有 ;，持续拼接后续行
                j = i
                while ";" not in method_decl and j < len(lines) - 1:
                    j += 1
                    next_line = lines[j].strip()
                    if not next_line or next_line.startswith("//") or next_line.startswith("{"):
                        break
                    method_decl += " " + next_line
                if ";" in method_decl:
                    mm = re.match(r"[-+]\s*\([^)]+\)\s*(\w+)", method_decl)
                    apis.append(_make_api("method", mm.group(1) if mm else "", method_decl,
                                          method_line, pending_comment))
                    pending_comment = ""
                    i = j + 1
                    continue

        if trimmed:
            pending_comment = ""

        i += 1

    return apis


# === 废弃标注提取 ===

_RE_NS_DEPRECATED = re.compile(
    r"NS_DEPRECATED_IOS\s*\(\s*([\d_.]+)\s*,\s*([\d_.]+)\s*(?:,\s*\"([^\"]*)\")?\s*\)"
)
_RE_ATTR_DEPRECATED = re.compile(
    r'__attribute__\s*\(\s*\(\s*deprecated\s*(?:\(\s*"([^"]*)"\s*\))?\s*\)\s*\)'
)
_RE_SWIFT_DEPRECATED = re.compile(
    r'@available\s*\(\s*\*\s*,\s*deprecated(?:\s*,\s*message\s*:\s*"([^"]*)")?\s*'
    r'(?:,\s*renamed\s*:\s*"([^"]*)")?\s*\)'
)


def _extract_deprecation(declaration: str) -> dict | None:
    """从声明行中提取废弃标注信息。"""
    m = _RE_NS_DEPRECATED.search(declaration)
    if m:
        result = {"since": m.group(1), "until": m.group(2)}
        if m.group(3):
            result["message"] = m.group(3)
        return result

    m = _RE_ATTR_DEPRECATED.search(declaration)
    if m:
        result = {}
        if m.group(1):
            result["message"] = m.group(1)
        return result

    m = _RE_SWIFT_DEPRECATED.search(declaration)
    if m:
        result = {}
        if m.group(1):
            result["message"] = m.group(1)
        if m.group(2):
            result["replacement"] = m.group(2)
        return result

    return None
