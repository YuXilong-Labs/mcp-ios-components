"""lark-cli 封装（lark_cli_wrapper.py）的测试。

覆盖安装检查、命令执行、wiki 节点创建、文档上传、预览模式。

Created by yuxilong on 2026/03/30
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch, call

from tools.lark_cli_wrapper import LarkCli, LarkCliError


class TestLarkCliInstallation(unittest.TestCase):
    """安装检查。"""

    @patch("subprocess.run")
    def test_installation_ok(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0\n", stderr="")
        cli = LarkCli()
        mock_run.assert_called_once()
        self.assertIn("--version", mock_run.call_args[0][0])

    @patch("subprocess.run", side_effect=FileNotFoundError("not found"))
    def test_installation_missing(self, mock_run):
        with self.assertRaises(LarkCliError) as ctx:
            LarkCli()
        self.assertIn("npm install", str(ctx.exception))

    @patch("subprocess.run")
    def test_installation_bad_returncode(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        with self.assertRaises(LarkCliError) as ctx:
            LarkCli()
        self.assertIn("未正确安装", str(ctx.exception))


class TestLarkCliRun(unittest.TestCase):
    """_run 方法。"""

    def _make_cli(self, dry_run=False):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0", stderr="")
            cli = LarkCli(dry_run=dry_run)
        return cli

    @patch("subprocess.run")
    def test_run_appends_format_json(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"result": "ok"}', stderr="")
        cli = self._make_cli()
        result = cli._run(["docs", "+create"])
        cmd = mock_run.call_args[0][0]
        self.assertIn("--format", cmd)
        self.assertIn("json", cmd)
        self.assertEqual(result["result"], "ok")

    @patch("subprocess.run")
    def test_run_dry_run_appended(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='{}', stderr="")
        cli = self._make_cli(dry_run=True)
        cli._run(["docs", "+create"])
        cmd = mock_run.call_args[0][0]
        self.assertIn("--dry-run", cmd)

    @patch("subprocess.run")
    def test_run_no_duplicate_format(self, mock_run):
        """已有 --format 时不重复添加。"""
        mock_run.return_value = MagicMock(returncode=0, stdout='{}', stderr="")
        cli = self._make_cli()
        cli._run(["docs", "+create", "--format", "pretty"])
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd.count("--format"), 1)

    @patch("subprocess.run")
    def test_run_error_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="auth failed")
        cli = self._make_cli()
        with self.assertRaises(LarkCliError) as ctx:
            cli._run(["docs", "+create"])
        self.assertIn("auth failed", str(ctx.exception))
        self.assertEqual(ctx.exception.returncode, 1)

    @patch("subprocess.run")
    def test_run_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        cli = self._make_cli()
        result = cli._run(["docs", "+create"])
        self.assertEqual(result, {})

    @patch("subprocess.run")
    def test_run_non_json_output(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="plain text output", stderr="")
        cli = self._make_cli()
        result = cli._run(["docs", "+create"])
        self.assertEqual(result["raw_output"], "plain text output")

    @patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="lark-cli", timeout=120))
    def test_run_timeout(self, mock_run):
        cli = self._make_cli()
        with self.assertRaises(LarkCliError) as ctx:
            cli._run(["docs", "+create"])
        self.assertIn("超时", str(ctx.exception))


class TestLarkCliWiki(unittest.TestCase):
    """Wiki 操作。"""

    def _make_cli(self, dry_run=False):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0", stderr="")
            cli = LarkCli(dry_run=dry_run)
        return cli

    @patch("subprocess.run")
    def test_create_wiki_node(self, mock_run):
        api_response = json.dumps({"node": {"node_token": "wikcnABC", "obj_token": "docxDEF"}})
        mock_run.return_value = MagicMock(returncode=0, stdout=api_response, stderr="")

        cli = self._make_cli()
        result = cli.create_wiki_node("space123", "parent456", "Test Doc")

        self.assertEqual(result["node_token"], "wikcnABC")
        self.assertEqual(result["obj_token"], "docxDEF")

        # 验证传入了正确的 API 路径
        cmd = mock_run.call_args[0][0]
        self.assertIn("/open-apis/wiki/v2/spaces/space123/nodes", " ".join(cmd))

    @patch("subprocess.run")
    def test_create_wiki_node_no_parent(self, mock_run):
        api_response = json.dumps({"node": {"node_token": "wikcnRoot", "obj_token": "docxRoot"}})
        mock_run.return_value = MagicMock(returncode=0, stdout=api_response, stderr="")

        cli = self._make_cli()
        result = cli.create_wiki_node("space123", "", "Root Doc")

        # 验证 body 中不含 parent_node_token
        cmd = mock_run.call_args[0][0]
        body_idx = cmd.index("--body") + 1
        body = json.loads(cmd[body_idx])
        self.assertNotIn("parent_node_token", body)

    @patch("subprocess.run")
    def test_create_wiki_node_with_parent(self, mock_run):
        api_response = json.dumps({"node": {"node_token": "wikcnABC", "obj_token": "docxDEF"}})
        mock_run.return_value = MagicMock(returncode=0, stdout=api_response, stderr="")

        cli = self._make_cli()
        cli.create_wiki_node("space123", "parent456", "Child Doc")

        cmd = mock_run.call_args[0][0]
        body_idx = cmd.index("--body") + 1
        body = json.loads(cmd[body_idx])
        self.assertEqual(body["parent_node_token"], "parent456")

    def test_create_wiki_node_dry_run(self):
        cli = self._make_cli(dry_run=True)
        result = cli.create_wiki_node("space123", "parent456", "Test Doc")
        self.assertEqual(result["node_token"], "(dry-run)")
        self.assertEqual(result["obj_token"], "(dry-run)")


class TestLarkCliCreateWikiDoc(unittest.TestCase):
    """create_wiki_doc 完整流程。"""

    def _make_cli(self, dry_run=False):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0", stderr="")
            cli = LarkCli(dry_run=dry_run)
        return cli

    @patch("subprocess.run")
    def test_create_wiki_doc_two_step(self, mock_run):
        """验证两步操作：创建节点 + 填充内容。"""
        # 第一次调用返回 wiki 节点，第二次返回内容结果
        wiki_resp = json.dumps({"node": {"node_token": "wikcnABC", "obj_token": "docxDEF"}})
        content_resp = json.dumps({"document_id": "docxDEF"})
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=wiki_resp, stderr=""),
            MagicMock(returncode=0, stdout=content_resp, stderr=""),
        ]

        cli = self._make_cli()
        result = cli.create_wiki_doc("space123", "", "Test", "# Hello\nWorld")

        self.assertEqual(result["node_token"], "wikcnABC")
        self.assertEqual(result["obj_token"], "docxDEF")
        self.assertEqual(mock_run.call_count, 2)

    def test_create_wiki_doc_dry_run(self):
        cli = self._make_cli(dry_run=True)
        result = cli.create_wiki_doc("space123", "", "Test", "# Hello")
        self.assertEqual(result["node_token"], "(dry-run)")
        self.assertIn("dry-run", result["content_result"]["status"])


class TestLarkCliCreateDoc(unittest.TestCase):
    """独立文档创建。"""

    def _make_cli(self, dry_run=False):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0", stderr="")
            cli = LarkCli(dry_run=dry_run)
        return cli

    @patch("subprocess.run")
    def test_create_doc(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"document_id": "docx123"}', stderr="")
        cli = self._make_cli()
        result = cli.create_doc("My Doc", "# Content")
        self.assertEqual(result["document_id"], "docx123")

        # 验证使用了临时文件
        cmd = mock_run.call_args[0][0]
        self.assertIn("--title", cmd)
        self.assertIn("--markdown-file", cmd)

    def test_create_doc_dry_run(self):
        cli = self._make_cli(dry_run=True)
        result = cli.create_doc("My Doc", "# Content")
        self.assertEqual(result["document_id"], "(dry-run)")


class TestLarkCliUploadFile(unittest.TestCase):
    """文件上传。"""

    def _make_cli(self, dry_run=False):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1.0.0", stderr="")
            cli = LarkCli(dry_run=dry_run)
        return cli

    def test_upload_nonexistent_file(self):
        cli = self._make_cli()
        with self.assertRaises(LarkCliError) as ctx:
            cli.upload_markdown_file("/nonexistent/file.md")
        self.assertIn("文件不存在", str(ctx.exception))

    @patch("subprocess.run")
    def test_upload_to_wiki(self, mock_run):
        """上传到 wiki 知识库。"""
        import tempfile
        wiki_resp = json.dumps({"node": {"node_token": "wikcnABC", "obj_token": "docxDEF"}})
        content_resp = json.dumps({"document_id": "docxDEF"})
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=wiki_resp, stderr=""),
            MagicMock(returncode=0, stdout=content_resp, stderr=""),
        ]

        # 创建临时 md 文件
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Test\nContent")
            tmp_path = f.name

        try:
            cli = self._make_cli()
            result = cli.upload_markdown_file(tmp_path, space_id="space123")
            self.assertEqual(result["node_token"], "wikcnABC")
        finally:
            os.unlink(tmp_path)

    @patch("subprocess.run")
    def test_upload_standalone(self, mock_run):
        """无 space_id 时创建独立文档。"""
        import tempfile
        mock_run.return_value = MagicMock(returncode=0, stdout='{"document_id": "docx123"}', stderr="")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# Test")
            tmp_path = f.name

        try:
            cli = self._make_cli()
            result = cli.upload_markdown_file(tmp_path)
            self.assertEqual(result["document_id"], "docx123")
        finally:
            os.unlink(tmp_path)

    @patch("subprocess.run")
    def test_upload_title_from_filename(self, mock_run):
        """标题从文件名提取。"""
        import tempfile
        mock_run.return_value = MagicMock(returncode=0, stdout='{"document_id": "docx123"}', stderr="")

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", prefix="BTBaseKit_", delete=False, encoding="utf-8"
        ) as f:
            f.write("# Test")
            tmp_path = f.name

        try:
            cli = self._make_cli()
            cli.upload_markdown_file(tmp_path)
            cmd = mock_run.call_args[0][0]
            title_idx = cmd.index("--title") + 1
            # 标题应包含文件名（去掉 .md）
            self.assertIn("BTBaseKit_", cmd[title_idx])
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
