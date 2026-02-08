import unittest
import importlib


class TestGetComponentApiGrouping(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_grouping_sorted_files_and_includes_comments(self):
        s = self._server()

        apis = [
            {"kind": "method", "name": "m2", "declaration": "- (void)m2;", "file": "B.h", "line": 2, "comment": "/// c2"},
            {"kind": "method", "name": "m1", "declaration": "- (void)m1;", "file": "A.h", "line": 1, "comment": "/// c1"},
        ]

        with s.INDEX_LOCK:
            s.INDEX = {
                "BTBaseKit": {
                    "name": "BTBaseKit",
                    "dir": "BTBaseKit",
                    "summary": "sum",
                    "description": "desc",
                    "podspec": "",
                    "files": [],
                    "source_count": 0,
                    "apis": apis,
                }
            }

        out = s.get_component_api("BTBaseKit")

        # File sections are sorted lexicographically.
        self.assertLess(out.find("## A.h"), out.find("## B.h"))

        # Comments should be included before declarations.
        self.assertIn("/// c1", out)
        self.assertIn("- (void)m1;", out)
        self.assertIn("/// c2", out)
        self.assertIn("- (void)m2;", out)


if __name__ == "__main__":
    unittest.main()
