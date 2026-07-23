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

    def test_sync_from_config_success_and_reindex(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "components.yaml")
            with open(cfg, "w", encoding="utf-8") as f:
                f.write("components:\\n  A: git@x:a.git\\n")

            os.makedirs(s.CACHE_DIR, exist_ok=True)
            cache_path = os.path.join(s.CACHE_DIR, "index.json")
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write("x")

            with s.INDEX_LOCK:
                s.PODS_DIR = d
                s.INDEX = {}

            with unittest.mock.patch.object(
                s, "sync_components", return_value=[{"name": "A", "status": "cloned", "message": "ok"}]
            ), unittest.mock.patch.object(s, "build_index", return_value={"A": {}}), unittest.mock.patch.object(
                s, "discover_components", return_value={"A"}
            ), unittest.mock.patch.object(s, "compute_hash", return_value="h"):
                out = s.sync_from_config(cfg)

            self.assertIn("组件同步结果", out)
            self.assertIn("索引已更新", out)
            self.assertFalse(os.path.exists(cache_path))

    def test_sync_from_config_updated_component_reindexes(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "components.yaml")
            with open(cfg, "w", encoding="utf-8") as f:
                f.write("components:\\n  A: git@x:a.git\\n")

            with unittest.mock.patch.object(
                s, "sync_components", return_value=[{"name": "A", "status": "updated", "message": "ok"}]
            ), unittest.mock.patch.object(s, "build_index", return_value={"A": {}}) as build, unittest.mock.patch.object(
                s, "discover_components", return_value={"A"}
            ), unittest.mock.patch.object(s, "compute_hash", return_value="updated-hash"):
                out = s.sync_from_config(cfg)

            self.assertIn("索引已更新", out)
            build.assert_called_once_with(s.PODS_DIR)
            self.assertEqual(s.LAST_HASH, "updated-hash")

    def test_sync_from_config_no_results(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "components.yaml")
            with open(cfg, "w", encoding="utf-8") as f:
                f.write("components:\\n  A: git@x:a.git\\n")
            with unittest.mock.patch.object(s, "sync_components", return_value=[]):
                out = s.sync_from_config(cfg)
            self.assertIn("无组件需要同步", out)


if __name__ == "__main__":
    unittest.main()
