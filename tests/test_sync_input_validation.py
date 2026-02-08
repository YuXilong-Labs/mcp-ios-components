import os
import tempfile
import unittest
import importlib


class TestSyncInputValidation(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_sync_from_config_missing_file(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            missing = os.path.join(d, "nope.yaml")
            out = s.sync_from_config(missing)
            self.assertIn("配置文件不存在", out)

    def test_sync_from_config_default_missing(self):
        s = self._server()

        # Ensure default components.yaml does not exist by pointing module dir to a temp.
        with tempfile.TemporaryDirectory() as d:
            # Monkeypatch __file__-derived default by setting config_path explicitly empty
            # and ensuring the expected default doesn't exist.
            default_path = os.path.join(os.path.dirname(os.path.abspath(s.__file__)), "components.yaml")
            if os.path.exists(default_path):
                self.skipTest("default components.yaml exists in repo; cannot test missing-default branch")
            out = s.sync_from_config("")
            self.assertIn("配置文件不存在", out)

    def test_sync_gitlab_group_tool_requires_token(self):
        s = self._server()

        # Ensure env token is not set.
        old = os.environ.pop("GITLAB_TOKEN", None)
        s.GITLAB_TOKEN = ""
        try:
            out = s.sync_gitlab_group_tool(group_id="ios-components", gitlab_url="", gitlab_token="")
            self.assertIn("未配置 GitLab Token", out)
        finally:
            if old is not None:
                os.environ["GITLAB_TOKEN"] = old

    def test_sync_gitlab_group_tool_skips_network_on_missing_token(self):
        s = self._server()

        called = {"count": 0}

        def fake_sync(*args, **kwargs):
            called["count"] += 1
            return []

        s.sync_gitlab_group = fake_sync
        s.GITLAB_TOKEN = ""

        out = s.sync_gitlab_group_tool(group_id="x", gitlab_url="", gitlab_token="")
        self.assertIn("未配置 GitLab Token", out)
        self.assertEqual(called["count"], 0)


if __name__ == "__main__":
    unittest.main()
