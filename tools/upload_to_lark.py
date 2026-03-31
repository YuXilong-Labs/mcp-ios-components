#!/usr/bin/env python3
"""将本地 Markdown 文件上传到飞书文档。

支持单文件或整个目录批量上传，通过 lark-cli docs +create / +update 实现。

前置条件:
    npm install -g @larksuite/cli
    lark-cli config init
    lark-cli auth login --recommend

用法:
    python tools/upload_to_lark.py docs/api/BTBaseKit.md
    python tools/upload_to_lark.py docs/api/
    python tools/upload_to_lark.py docs/api/ --wiki-node wikcnXXXX
    python tools/upload_to_lark.py docs/api/BTBaseKit.md --dry-run

Created by yuxilong on 2026/03/30
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# -- 数据模型 ---------------------------------------------------------------


@dataclass(frozen=True)
class UploadResult:
    """单个文件的上传结果。"""

    file_path: str
    title: str
    doc_id: str = ""
    doc_url: str = ""
    error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.doc_id) and not self.error


# -- lark-cli 调用 ----------------------------------------------------------


def _run_lark_cli(args: list[str], timeout: int = 120) -> dict:
    """执行 lark-cli 命令并返回解析后的 JSON。"""
    cmd = ["lark-cli"] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"lark-cli 失败 (exit={result.returncode}): {stderr}")

    stdout = result.stdout.strip()
    if not stdout:
        return {}
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return {"raw_output": stdout}


def _build_location_args(ns: argparse.Namespace) -> list[str]:
    """根据命令行参数构建 docs +create 的位置参数。"""
    if ns.wiki_node:
        return ["--wiki-node", ns.wiki_node]
    if ns.wiki_space:
        return ["--wiki-space", ns.wiki_space]
    if ns.folder_token:
        return ["--folder-token", ns.folder_token]
    return []


# -- 标题提取 ---------------------------------------------------------------


def _extract_title(markdown: str, file_path: str) -> str:
    """从 Markdown 首行 `# xxx` 提取标题，回退到文件名。"""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
        if stripped:
            break
    # 用文件名（去扩展名）
    return Path(file_path).stem


# -- 分段逻辑 ---------------------------------------------------------------


def _split_markdown(markdown: str, head_lines: int, chunk_lines: int) -> tuple[str, list[str]]:
    """将 Markdown 拆分为 head（用于 create）和若干 chunks（用于 append）。

    返回 (head_content, [chunk1, chunk2, ...])。
    """
    lines = markdown.splitlines(keepends=True)

    head = "".join(lines[:head_lines])
    rest = lines[head_lines:]

    chunks: list[str] = []
    buf: list[str] = []
    for line in rest:
        buf.append(line)
        if len(buf) >= chunk_lines:
            chunks.append("".join(buf))
            buf = []
    if buf:
        chunks.append("".join(buf))

    return head, chunks


# -- 单文件上传 -------------------------------------------------------------


def upload_file(
    file_path: str,
    title: str,
    location_args: list[str],
    chunk_lines: int = 400,
    head_lines: int = 50,
    dry_run: bool = False,
) -> UploadResult:
    """上传单个 Markdown 文件到飞书。"""
    path = Path(file_path)
    if not path.is_file():
        return UploadResult(file_path=file_path, title=title, error=f"文件不存在: {file_path}")

    markdown = path.read_text(encoding="utf-8")
    if not markdown.strip():
        return UploadResult(file_path=file_path, title=title, error="文件内容为空")

    if not title:
        title = _extract_title(markdown, file_path)

    total_lines = len(markdown.splitlines())
    head_content, chunks = _split_markdown(markdown, head_lines, chunk_lines)

    if dry_run:
        parts = 1 + len(chunks) if chunks else 1
        print(f"  [预览] {title}")
        print(f"         文件: {file_path}")
        print(f"         行数: {total_lines}，分 {parts} 段上传")
        return UploadResult(file_path=file_path, title=title, doc_id="(dry-run)", doc_url="(dry-run)")

    # 第一步：创建文档
    create_args = ["docs", "+create", "--title", title, "--markdown", head_content, "--as", "user"] + location_args
    try:
        resp = _run_lark_cli(create_args)
    except (RuntimeError, subprocess.TimeoutExpired) as e:
        return UploadResult(file_path=file_path, title=title, error=str(e))

    data = resp.get("data", resp)
    doc_id = data.get("doc_id", "")
    doc_url = data.get("doc_url", "")

    if not doc_id:
        return UploadResult(file_path=file_path, title=title, error=f"创建文档失败: {resp}")

    # 第二步：分段追加
    for i, chunk in enumerate(chunks):
        print(f"  上传第 {i + 2}/{1 + len(chunks)} 段 ({len(chunk)} 字符)...", end=" ", flush=True)
        try:
            _run_lark_cli(
                [
                    "docs",
                    "+update",
                    "--doc",
                    doc_id,
                    "--mode",
                    "append",
                    "--markdown",
                    chunk,
                ]
            )
            print("成功")
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            print("失败")
            return UploadResult(
                file_path=file_path,
                title=title,
                doc_id=doc_id,
                doc_url=doc_url,
                error=f"追加第 {i + 2} 段失败: {e}",
            )
        if i < len(chunks) - 1:
            time.sleep(1)

    return UploadResult(file_path=file_path, title=title, doc_id=doc_id, doc_url=doc_url)


# -- 文件收集 ---------------------------------------------------------------


def _collect_files(path: str) -> list[str]:
    """收集目标路径下的 .md 文件。"""
    p = Path(path)
    if p.is_file():
        if p.suffix.lower() != ".md":
            print(f"警告：{path} 不是 .md 文件，仍尝试上传", file=sys.stderr)
        return [str(p)]
    if p.is_dir():
        files = sorted(p.glob("*.md"))
        if not files:
            print(f"错误：目录 {path} 下没有 .md 文件", file=sys.stderr)
            sys.exit(1)
        return [str(f) for f in files]
    print(f"错误：路径不存在: {path}", file=sys.stderr)
    sys.exit(1)


# -- 主入口 -----------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="上传 Markdown 文件到飞书文档",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s docs/api/BTBaseKit.md                  # 上传单个文件
  %(prog)s docs/api/                              # 上传目录下所有 .md
  %(prog)s docs/api/ --wiki-node wikcnXXXX        # 上传到知识库节点下
  %(prog)s docs/api/BTBaseKit.md --dry-run         # 预览模式
""",
    )
    parser.add_argument("path", help="Markdown 文件或目录路径")
    parser.add_argument("--title", default="", help="文档标题（仅单文件时生效，默认从内容提取）")
    parser.add_argument("--wiki-node", default="", help="知识库节点 token（wikcnXXXX 格式）")
    parser.add_argument("--wiki-space", default="", help="知识空间 ID（与 --wiki-node 互斥）")
    parser.add_argument("--folder-token", default="", help="云空间文件夹 token（与 --wiki-node 互斥）")
    parser.add_argument("--chunk-lines", type=int, default=400, help="分段上传行数（默认 400）")
    parser.add_argument("--head-lines", type=int, default=50, help="首次创建包含的行数（默认 50）")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际上传")

    args = parser.parse_args()

    # 互斥校验
    loc_count = sum(bool(v) for v in [args.wiki_node, args.wiki_space, args.folder_token])
    if loc_count > 1:
        print("错误：--wiki-node、--wiki-space、--folder-token 三者互斥，只能指定一个", file=sys.stderr)
        sys.exit(1)

    files = _collect_files(args.path)
    location_args = _build_location_args(args)

    print(f"准备上传 {len(files)} 个文件" + ("（预览模式）" if args.dry_run else ""))
    print()

    results: list[UploadResult] = []
    for i, fpath in enumerate(files):
        # 多文件时 --title 不生效
        title = args.title if len(files) == 1 else ""
        print(f"[{i + 1}/{len(files)}] {Path(fpath).name}")

        result = upload_file(
            file_path=fpath,
            title=title,
            location_args=location_args,
            chunk_lines=args.chunk_lines,
            head_lines=args.head_lines,
            dry_run=args.dry_run,
        )
        results.append(result)

        if result.ok and not args.dry_run:
            print(f"  完成: {result.doc_url}")
        elif result.error:
            print(f"  失败: {result.error}", file=sys.stderr)
        print()

    # 汇总
    ok_count = sum(1 for r in results if r.ok)
    fail_count = sum(1 for r in results if r.error and r.doc_id != "(dry-run)")
    print("=" * 50)
    print(f"上传完成：成功 {ok_count}，失败 {fail_count}")
    if not args.dry_run:
        for r in results:
            status = "成功" if r.ok else f"失败({r.error[:40]})"
            url = r.doc_url if r.ok else ""
            print(f"  {r.title}: {status} {url}")


if __name__ == "__main__":
    main()
