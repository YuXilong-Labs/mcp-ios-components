import unittest
import importlib


class TestFindUsageExampleEdges(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_find_usage_example_component_missing(self):
        s = self._server()
        with s.INDEX_LOCK:
            s.INDEX = {}
        out = s.find_usage_example("BTBaseKit")
        self.assertIn("组件", out)

    def test_find_usage_example_no_other_components(self):
        s = self._server()
        with s.INDEX_LOCK:
            s.INDEX = {
                "BTBaseKit": {
                    "name": "BTBaseKit",
                    "dir": "BTBaseKit",
                    "summary": "",
                    "description": "",
                    "podspec": "",
                    "files": [],
                    "source_count": 0,
                    "apis": [],
                }
            }
        out = s.find_usage_example("BTBaseKit")
        # We only assert it returns a string and does not crash.
        self.assertTrue(isinstance(out, str) and len(out) > 0)


if __name__ == "__main__":
    unittest.main()
