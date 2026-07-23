"""飞书官方 CLI（lark-cli）子进程封装。

通过 subprocess 调用 lark-cli 实现文档创建与上传，
使用 `lark-cli docs +create --wiki-node` 一步完成知识库文档创建。

前置条件:
    npm install -g @larksuite/cli
    lark-cli config init
    lark-cli auth login --recommend

Created by yuxilong on 2026/03/30
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class LarkCliError(RuntimeError):
    """lark-cli 命令执行失败。"""

    def __init__(self, message: str, returncode: int = -1, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(message)


class LarkCli:
    """lark-cli 子进程封装。

    通过调用 lark-cli 命令行工具操作飞书文档和知识库。
    认证由 lark-cli 自身管理（config init + auth login）。
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self._verify_installation()

    def _verify_installation(self) -> None:
        """检查 lark-cli 是否已安装。"""
        try:
            result = subprocess.run(
                ["lark-cli", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                raise LarkCliError(
                    "lark-cli 未正确安装。\n"
                    "安装方式: npm install -g @larksuite/cli\n"
                    "初始化: lark-cli config init && lark-cli auth login --recommend"
                )
            logger.debug("lark-cli version: %s", result.stdout.strip())
        except FileNotFoundError as e:
            raise LarkCliError(
                "未找到 lark-cli 命令。\n"
                "安装方式: npm install -g @larksuite/cli\n"
                "初始化: lark-cli config init && lark-cli auth login --recommend"
            ) from e

    def _run(
        self,
        args: list[str],
        stdin_data: str | None = None,
        timeout: int = 120,
    ) -> dict:
        """执行 lark-cli 命令并返回 JSON 结果。

        自动附加 --format json；dry_run 时附加 --dry-run。
        """
        cmd = ["lark-cli"] + args

        if "--format" not in args:
            cmd += ["--format", "json"]

        if self.dry_run and "--dry-run" not in args:
            cmd.append("--dry-run")

        logger.info("执行: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            raise LarkCliError(f"lark-cli 命令超时 ({timeout}s)", stderr=str(e)) from e

        if result.returncode != 0:
            raise LarkCliError(
                f"lark-cli 命令失败 (exit={result.returncode}): {result.stderr.strip()}",
                returncode=result.returncode,
                stderr=result.stderr,
            )

        stdout = result.stdout.strip()
        if not stdout:
            return {}

        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            # 非 JSON 输出时返回原始文本
            return {"raw_output": stdout}

    def _write_temp_markdown(self, markdown: str) -> str:
        """将 Markdown 写入临时文件，返回路径。"""
        fd, path = tempfile.mkstemp(suffix=".md", prefix="lark_doc_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(markdown)
        except Exception:
            os.close(fd)
            raise
        return path

    # ------------------------------------------------------------------
    # 知识库文档操作
    # ------------------------------------------------------------------

    def create_wiki_node(
        self,
        space_id: str,
        parent_node_token: str,
        title: str,
    ) -> dict:
        """兼容旧调用：在知识库空间下创建文档节点。"""
        body: dict = {
            "obj_type": "docx",
            "node_type": "origin",
            "title": title,
        }
        if parent_node_token:
            body["parent_node_token"] = parent_node_token

        if self.dry_run:
            return {"node_token": "(dry-run)", "obj_token": "(dry-run)"}

        result = self._run(
            [
                "api",
                "POST",
                f"/open-apis/wiki/v2/spaces/{space_id}/nodes",
                "--body",
                json.dumps(body, ensure_ascii=False),
            ]
        )
        node = result.get("node", {})
        return {
            "node_token": node.get("node_token", ""),
            "obj_token": node.get("obj_token", ""),
        }

    def update_doc_content(self, document_id: str, markdown: str) -> dict:
        """兼容旧调用：向已创建的文档写入 Markdown。"""
        if self.dry_run:
            return {"document_id": document_id, "status": "dry-run"}

        tmp_path = self._write_temp_markdown(markdown)
        try:
            return self._run(
                [
                    "docs",
                    "+create",
                    "--document-id",
                    document_id,
                    "--markdown-file",
                    tmp_path,
                    "--as",
                    "user",
                ]
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    def create_wiki_doc(
        self,
        wiki_target: str,
        *args: str,
    ) -> dict:
        """创建知识库文档，同时兼容单步和旧版两步调用。

        - ``create_wiki_doc(wiki_node, title, markdown)``：当前单步接口。
        - ``create_wiki_doc(space_id, parent_node, title, markdown)``：兼容旧接口。
        """
        if len(args) == 3:
            parent_node_token, title, markdown = args
            node = self.create_wiki_node(wiki_target, parent_node_token, title)
            if self.dry_run:
                return {**node, "content_result": {"status": "dry-run"}}
            content_result = self.update_doc_content(node["obj_token"], markdown)
            return {**node, "content_result": content_result}

        if len(args) != 2:
            raise TypeError("create_wiki_doc expects 3 or 4 positional arguments")

        title, markdown = args
        if self.dry_run:
            preview = markdown[:200] + "..." if len(markdown) > 200 else markdown
            logger.info("[预览] 创建 wiki 文档: node=%s, title=%s\n%s", wiki_target, title, preview)
            return {"doc_id": "(dry-run)", "doc_url": "(dry-run)"}

        tmp_path = self._write_temp_markdown(markdown)
        try:
            result = self._run(
                [
                    "docs",
                    "+create",
                    "--title",
                    title,
                    "--markdown-file",
                    tmp_path,
                    "--wiki-node",
                    wiki_target,
                    "--as",
                    "user",
                ]
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return result

    # ------------------------------------------------------------------
    # 独立文档操作（非 wiki 场景）
    # ------------------------------------------------------------------

    def create_doc(self, title: str, markdown: str, folder_token: str = "") -> dict:
        """创建独立文档（非 wiki 场景）。

        使用 lark-cli docs +create 创建文档。
        """
        if self.dry_run:
            preview = markdown[:200] + "..." if len(markdown) > 200 else markdown
            logger.info("[预览] 创建文档 '%s' (%d 字符):\n%s", title, len(markdown), preview)
            return {"document_id": "(dry-run)", "title": title}

        tmp_path = self._write_temp_markdown(markdown)
        try:
            args = ["docs", "+create", "--title", title, "--markdown-file", tmp_path, "--as", "user"]
            if folder_token:
                args += ["--folder-token", folder_token]
            result = self._run(args)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return result

    def upload_markdown_file(
        self,
        file_path: str,
        wiki_node: str = "",
        title: str = "",
        *,
        space_id: str = "",
        parent_node_token: str = "",
    ) -> dict:
        """上传本地 .md 文件到飞书。

        支持上传到 wiki 知识库（需 wiki_node）或作为独立文档。
        """
        if not os.path.isfile(file_path):
            raise LarkCliError(f"文件不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            markdown = f.read()

        if not title:
            title = os.path.splitext(os.path.basename(file_path))[0]

        if space_id:
            return self.create_wiki_doc(space_id, parent_node_token, title, markdown)
        if wiki_node:
            return self.create_wiki_doc(wiki_node, title, markdown)
        return self.create_doc(title, markdown)
