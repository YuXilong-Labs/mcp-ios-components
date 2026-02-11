import tempfile
import unittest
import importlib
from unittest import mock


class TestSyncGitlabGroup(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_sync_gitlab_group_no_repos_and_mixed(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            out = s.sync_gitlab_group("g", d, gitlab_token="t")
            self.assertEqual(out, [])

            repos = [
                {"path": "A", "ssh_url": "sshA", "http_url": "httpA", "default_branch": "main"},
                {"path": "B", "ssh_url": "sshB", "http_url": "httpB", "default_branch": "dev"},
            ]
            with mock.patch.object(s, "fetch_gitlab_group_repos", return_value=repos), \
                mock.patch.object(s, "check_repo_is_base_component", side_effect=[(False, "A.podspec", "non-base"), (True, "B.podspec", "ok")]), \
                mock.patch.object(s, "sync_component", return_value={"name": "B", "status": "cloned", "message": "ok"}):
                res = s.sync_gitlab_group("g", d, gitlab_token="t", use_ssh=False)

            self.assertEqual(len(res), 2)
            self.assertEqual(res[0]["status"], "skip")
            self.assertEqual(res[1]["status"], "cloned")

            # use_ssh=True branch
            with mock.patch.object(s, "fetch_gitlab_group_repos", return_value=[repos[0]]), \
                mock.patch.object(s, "check_repo_is_base_component", return_value=(True, "A.podspec", "ok")), \
                mock.patch.object(s, "sync_component", return_value={"name": "A", "status": "updated", "message": "ok"}) as sync_mock:
                s.sync_gitlab_group("g", d, gitlab_token="t", use_ssh=True)
            args, kwargs = sync_mock.call_args
            self.assertEqual(args[1]["repo"], "sshA")

    def test_sync_gitlab_group_tool_format_and_reindex(self):
        s = self._server()
        s.GITLAB_TOKEN = "tok"

        results = [
            {"name": "A", "status": "skip", "message": "x"},
            {"name": "B", "status": "cloned", "message": "ok"},
            {"name": "C", "status": "error", "message": "bad"},
        ]

        with mock.patch.object(s, "sync_gitlab_group", return_value=results), \
            mock.patch.object(s, "build_index", return_value={"B": {}}), \
            mock.patch.object(s, "discover_components", return_value={"B"}), \
            mock.patch.object(s, "compute_hash", return_value="h"):
            out = s.sync_gitlab_group_tool("group", gitlab_url="", gitlab_token="", use_ssh=True)

        self.assertIn("基础组件", out)
        self.assertIn("已跳过", out)
        self.assertIn("索引已更新", out)

        with mock.patch.object(s, "sync_gitlab_group", return_value=[]):
            out2 = s.sync_gitlab_group_tool("group", gitlab_token="tok")
            self.assertIn("未找到仓库", out2)


if __name__ == "__main__":
    unittest.main()
