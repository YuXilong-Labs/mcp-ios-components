"""飞书官方 CLI（lark-cli）子进程封装。

通过 subprocess 调用 lark-cli 实现文档创建与上传，
替代原有 LarkClient 的手动 HTTP 方案。

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
                capture_output=True, text=True, timeout=10,
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
    # 知识库操作
    # ------------------------------------------------------------------

    def create_wiki_node(
        self,
        space_id: str,
        parent_node_token: str,
        title: str,
    ) -> dict:
        """在知识库空间下创建文档节点。

        使用 lark-cli 的 raw API 模式调用 wiki 接口。
        返回 {"node_token": "...", "obj_token": "..."}
        """
        body: dict = {
            "obj_type": "docx",
            "node_type": "origin",
            "title": title,
        }
        if parent_node_token:
            body["parent_node_token"] = parent_node_token

        if self.dry_run:
            logger.info("[预览] 创建 wiki 节点: space=%s, parent=%s, title=%s",
                        space_id, parent_node_token or "(根目录)", title)
            return {
                "node_token": "(dry-run)",
                "obj_token": "(dry-run)",
            }

        result = self._run([
            "api", "POST",
            f"/open-apis/wiki/v2/spaces/{space_id}/nodes",
            "--body", json.dumps(body, ensure_ascii=False),
        ])

        node = result.get("node", {})
        return {
            "node_token": node.get("node_token", ""),
            "obj_token": node.get("obj_token", ""),
        }

    def update_doc_content(self, document_id: str, markdown: str) -> dict:
        """向文档写入 Markdown 内容。

        使用 lark-cli docs +create 或 raw API 更新文档内容。
        对于大文档，通过临时文件传入。
        """
        if self.dry_run:
            preview = markdown[:200] + "..." if len(markdown) > 200 else markdown
            logger.info("[预览] 更新文档 %s 内容 (%d 字符):\n%s",
                        document_id, len(markdown), preview)
            return {"document_id": document_id, "status": "dry-run"}

        # 将 markdown 写入临时文件
        tmp_path = self._write_temp_markdown(markdown)
        try:
            result = self._run([
                "docs", "+create",
                "--document-id", document_id,
                "--markdown-file", tmp_path,
            ])
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        return result

    def create_wiki_doc(
        self,
        space_id: str,
        parent_node_token: str,
        title: str,
        markdown: str,
    ) -> dict:
        """创建 wiki 文档节点并填充 Markdown 内容。

        两步操作：1) 创建节点 2) 填充内容。
        返回 {"node_token": "...", "obj_token": "...", "content_result": ...}
        """
        # 第一步：创建 wiki 节点
        node = self.create_wiki_node(space_id, parent_node_token, title)

        if self.dry_run:
            preview = markdown[:200] + "..." if len(markdown) > 200 else markdown
            logger.info("[预览] 将写入 %d 字符 Markdown 到文档:\n%s",
                        len(markdown), preview)
            return {**node, "content_result": {"status": "dry-run"}}

        # 第二步：填充内容
        doc_id = node["obj_token"]
        content_result = self.update_doc_content(doc_id, markdown)

        return {**node, "content_result": content_result}

    def create_doc(self, title: str, markdown: str, folder_token: str = "") -> dict:
        """创建独立文档（非 wiki 场景）。

        使用 lark-cli docs +create 创建文档。
        """
        if self.dry_run:
            preview = markdown[:200] + "..." if len(markdown) > 200 else markdown
            logger.info("[预览] 创建文档 '%s' (%d 字符):\n%s",
                        title, len(markdown), preview)
            return {"document_id": "(dry-run)", "title": title}

        tmp_path = self._write_temp_markdown(markdown)
        try:
            args = ["docs", "+create", "--title", title, "--markdown-file", tmp_path]
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
        space_id: str = "",
        parent_node_token: str = "",
        title: str = "",
    ) -> dict:
        """上传本地 .md 文件到飞书。

        支持上传到 wiki 知识库（需 space_id）或作为独立文档。
        """
        if not os.path.isfile(file_path):
            raise LarkCliError(f"文件不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            markdown = f.read()

        if not title:
            # 从文件名提取标题
            title = os.path.splitext(os.path.basename(file_path))[0]

        if space_id:
            return self.create_wiki_doc(space_id, parent_node_token, title, markdown)
        else:
            return self.create_doc(title, markdown)
