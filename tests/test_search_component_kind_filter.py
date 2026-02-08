import json
import unittest
import importlib


class TestSearchComponentKindFilter(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_kind_filter(self):
        s = self._server()

        apis = [
            {"kind": "method", "name": "foo", "declaration": "- (void)foo;", "file": "A.h", "line": 1, "comment": ""},
            {"kind": "property", "name": "bar", "declaration": "@property int bar;", "file": "A.h", "line": 2, "comment": ""},
        ]

        with s.INDEX_LOCK:
            s.INDEX = {"BTBaseKit": {"name": "BTBaseKit", "dir": "BTBaseKit", "summary": "", "description": "", "podspec": "", "files": [], "source_count": 0, "apis": apis}}

        raw = s.search_component(keyword="bar", kind="property", format="json", limit=10)
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        self.assertTrue(all(r["kind"] == "property" for r in data["results"]))


if __name__ == "__main__":
    unittest.main()
