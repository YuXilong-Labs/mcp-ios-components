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

    def test_find_usage_example_api_only_denied_and_alias(self):
        s = self._server()
        with s.INDEX_LOCK:
            s.PODS_DIR = "/tmp"
            s.INDEX = {
                "BTBaseKit": {
                    "name": "BTBaseKit",
                    "dir": "btbasekit",
                    "summary": "",
                    "description": "",
                    "podspec": "",
                    "files": [],
                    "source_count": 0,
                    "apis": [],
                    "access_mode": s.ACCESS_MODE_API_ONLY,
                }
            }

        out = s.find_usage_example("btbasekit")
        self.assertEqual(out, s.API_ONLY_DENY_MESSAGE)


if __name__ == "__main__":
    unittest.main()
