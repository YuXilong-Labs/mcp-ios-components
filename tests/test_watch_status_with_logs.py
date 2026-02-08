import unittest
import importlib


class TestWatchStatusWithLogs(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_watch_status_formats_log_entries(self):
        s = self._server()

        s.WATCH_INTERVAL = 300
        s.WATCH_LOG = [
            {
                "time": "t1",
                "repos": [
                    {"name": "BTBaseKit", "updated": True, "error": "", "changes": 1},
                    {"name": "BTNetwork", "updated": False, "error": "", "changes": 0},
                ],
            },
            {
                "time": "t2",
                "repos": [
                    {"name": "BTBaseKit", "updated": False, "error": "boom", "changes": 0},
                ],
            },
            {
                "time": "t3",
                "repos": [
                    {"name": "BTBaseKit", "updated": False, "error": "", "changes": 0},
                ],
            },
        ]

        with s.INDEX_LOCK:
            s.INDEX = {"BTBaseKit": {"name": "BTBaseKit", "dir": "BTBaseKit", "summary": "", "description": "", "podspec": "", "files": [], "source_count": 0, "apis": []}}

        out = s.watch_status()
        self.assertIn("每 300 秒", out)
        self.assertIn("最近", out)
        self.assertIn("✅ 更新", out)
        self.assertIn("⚠️ 错误", out)
        self.assertIn("➖ 无变更", out)


if __name__ == "__main__":
    unittest.main()
