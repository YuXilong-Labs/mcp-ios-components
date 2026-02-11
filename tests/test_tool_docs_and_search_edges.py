import json
import unittest
import importlib


class TestToolDocsAndSearchEdges(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_get_tool_docs_text_and_invalid_format(self):
        s = self._server()
        txt = s.get_tool_docs(format="text")
        self.assertIn("MCP 工具说明", txt)

        bad = s.get_tool_docs(format="bad")
        self.assertIn("无效的 format", bad)

        unknown_text = s.get_tool_docs(tool_name="unknown", format="text")
        self.assertIn("未知工具", unknown_text)

    def test_search_component_empty_index_and_limit_conversion(self):
        s = self._server()
        with s.INDEX_LOCK:
            s.INDEX = {}
        self.assertIn("暂无索引数据", s.search_component("abc"))

        with s.INDEX_LOCK:
            s.INDEX = {
                "A": {
                    "name": "A",
                    "dir": "A",
                    "summary": "",
                    "description": "",
                    "podspec": "",
                    "files": [],
                    "source_count": 0,
                    "apis": [
                        {"kind": "method", "name": "abc", "declaration": "- (void)abc;", "file": "A.h", "line": 1, "comment": ""},
                        {"kind": "method", "name": "abc2", "declaration": "- (void)abc2;", "file": "A.h", "line": 2, "comment": ""},
                    ],
                }
            }

        # invalid limit falls back to 50
        raw = s.search_component("abc", format="json", limit="x")
        data = json.loads(raw)
        self.assertTrue(data["ok"])

        # text truncated branch
        out = s.search_component("abc", format="text", limit=1)
        self.assertIn("仅显示前 1 条", out)

    def test_search_component_component_name_and_comment_preview(self):
        s = self._server()
        with s.INDEX_LOCK:
            s.INDEX = {
                "BTBaseKit": {
                    "name": "BTBaseKit",
                    "dir": "BTBaseKit",
                    "summary": "sum",
                    "description": "",
                    "podspec": "",
                    "files": [],
                    "source_count": 0,
                    "apis": [
                        {"kind": "method", "name": "clip", "declaration": "- (void)clip;", "file": "A.h", "line": 1, "comment": "/// first line\n/// second"}
                    ],
                }
            }

        raw = s.search_component("btbase", format="json", limit=5)
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        self.assertTrue(any(r["kind"] == "component" for r in data["results"]))

        out = s.search_component("clip", format="text", limit=5)
        self.assertIn("💬", out)


if __name__ == "__main__":
    unittest.main()
