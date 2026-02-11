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
    """Extract API declarations and nearby comments."""
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

    for i, line in enumerate(lines):
        trimmed = line.strip()

        if trimmed.startswith("///"):
            pending_comment += ("\n" if pending_comment else "") + trimmed
            continue

        if trimmed.startswith("/**"):
            block = trimmed
            j = i
            while "*/" not in block and j < len(lines) - 1:
                j += 1
                block += "\n" + lines[j].strip()
            pending_comment = block
            continue

        if is_swift:
            m = re.match(
                r"^(?:@\w+\s+)*(?:public|open)\s+(?:(?:class|static|final|override|weak|lazy|nonisolated|@objc(?:\([^)]*\))?)\s+)*"
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
                apis.append(
                    {
                        "kind": kind,
                        "name": name,
                        "declaration": trimmed,
                        "file": rel_path,
                        "line": i + 1,
                        "comment": pending_comment,
                    }
                )
                pending_comment = ""
                continue

        if is_header:
            m = re.match(r"^@(interface|protocol)\s+(\w+)", trimmed)
            if m:
                apis.append(
                    {
                        "kind": m.group(1),
                        "name": m.group(2),
                        "declaration": trimmed,
                        "file": rel_path,
                        "line": i + 1,
                        "comment": pending_comment,
                    }
                )
                pending_comment = ""
                continue

            m = re.match(r"^@property\s*\(([^)]*)\)\s*\S+\s*\*?\s*(\w+)", trimmed)
            if m:
                apis.append(
                    {
                        "kind": "property",
                        "name": m.group(2),
                        "declaration": trimmed,
                        "file": rel_path,
                        "line": i + 1,
                        "comment": pending_comment,
                    }
                )
                pending_comment = ""
                continue

            m = re.match(
                r"^(?:CG_INLINE|NS_INLINE|FOUNDATION_STATIC_INLINE|static\s+(?:__)?inline)\s+\w[\w\s*]*?\b(\w+)\s*\(",
                trimmed,
            )
            if m:
                apis.append(
                    {
                        "kind": "func",
                        "name": m.group(1),
                        "declaration": trimmed,
                        "file": rel_path,
                        "line": i + 1,
                        "comment": pending_comment,
                    }
                )
                pending_comment = ""
                continue

            m = re.match(
                r"^(?:FOUNDATION_EXTERN|UIKIT_EXTERN|extern|OBJC_EXTERN)\s+.*?\b(\w+)\s*\(",
                trimmed,
            )
            if m:
                apis.append(
                    {
                        "kind": "func",
                        "name": m.group(1),
                        "declaration": trimmed,
                        "file": rel_path,
                        "line": i + 1,
                        "comment": pending_comment,
                    }
                )
                pending_comment = ""
                continue

            if (trimmed.startswith("-") or trimmed.startswith("+")) and ";" in trimmed:
                mm = re.match(r"[-+]\s*\([^)]+\)\s*(\w+)", trimmed)
                apis.append(
                    {
                        "kind": "method",
                        "name": mm.group(1) if mm else "",
                        "declaration": trimmed,
                        "file": rel_path,
                        "line": i + 1,
                        "comment": pending_comment,
                    }
                )
                pending_comment = ""
                continue

        if trimmed:
            pending_comment = ""

    return apis
