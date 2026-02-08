import unittest
import importlib


class TestListComponents(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_list_components_empty(self):
        s = self._server()
        with s.INDEX_LOCK:
            s.INDEX = {}
        out = s.list_components()
        self.assertIn("暂无", out)

    def test_list_components_sorted_and_counts(self):
        s = self._server()
        with s.INDEX_LOCK:
            s.INDEX = {
                "B": {"name": "B", "dir": "B", "summary": "sb", "description": "", "podspec": "", "files": [], "source_count": 2, "apis": [{}, {}]},
                "A": {"name": "A", "dir": "A", "summary": "sa", "description": "", "podspec": "", "files": [], "source_count": 1, "apis": [{}]},
            }
        out = s.list_components()
        # A should appear before B
        self.assertLess(out.find("**A**"), out.find("**B**"))
        self.assertIn("共 2 个组件", out)
        self.assertIn("APIs: 1", out)
        self.assertIn("APIs: 2", out)


if __name__ == "__main__":
    unittest.main()
