import unittest
import importlib


class TestRefreshIndexEdges(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_refresh_index_no_reindex_branch(self):
        s = self._server()

        def fake_check():
            return {
                "time": "now",
                "repos": [{"name": "BTBaseKit", "updated": False, "error": "", "changes": 0}],
                "reindexed": False,
            }

        s.check_for_updates = fake_check
        out = s.refresh_index()
        self.assertIn("索引无需更新", out)

    def test_refresh_index_error_formatting(self):
        s = self._server()

        def fake_check():
            return {
                "time": "now",
                "repos": [{"name": "BTBaseKit", "updated": False, "error": "boom", "changes": 0}],
                "reindexed": False,
            }

        s.check_for_updates = fake_check
        out = s.refresh_index()
        self.assertIn("boom", out)


if __name__ == "__main__":
    unittest.main()
