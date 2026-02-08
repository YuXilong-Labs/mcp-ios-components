import os
import tempfile
import unittest
import importlib


class TestRefreshAndWatchStatus(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_watch_status_basic(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            with s.INDEX_LOCK:
                s.PODS_DIR = d
                s.INDEX = {"BTBaseKit": {"name": "BTBaseKit", "dir": "BTBaseKit", "summary": "", "description": "", "podspec": "", "files": [], "source_count": 0, "apis": []}}

            s.WATCH_INTERVAL = 0
            s.WATCH_LOG = []

            out = s.watch_status()
            self.assertIn("定时检查", out)
            self.assertIn("当前索引", out)
            self.assertIn("暂无更新日志", out)

    def test_refresh_index_uses_check_for_updates(self):
        s = self._server()

        # Monkeypatch check_for_updates to avoid touching git.
        def fake_check():
            return {
                "time": "now",
                "repos": [
                    {"name": "BTBaseKit", "updated": False, "error": "", "changes": 0},
                    {"name": "BTNetwork", "updated": True, "error": "", "changes": 2},
                ],
                "reindexed": True,
            }

        s.check_for_updates = fake_check

        with s.INDEX_LOCK:
            s.INDEX = {"BTBaseKit": {"name": "BTBaseKit", "dir": "BTBaseKit", "summary": "", "description": "", "podspec": "", "files": [], "source_count": 0, "apis": []}}

        out = s.refresh_index()
        self.assertIn("检查完成", out)
        self.assertIn("BTBaseKit", out)
        self.assertIn("BTNetwork", out)
        self.assertIn("索引已重建", out)


if __name__ == "__main__":
    unittest.main()
