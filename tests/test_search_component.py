import json
import unittest
import importlib


class TestSearchComponent(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_search_component_json_schema_and_truncation(self):
        s = self._server()

        # Inject a tiny index directly (unit-level; no filesystem).
        with s.INDEX_LOCK:
            s.INDEX = {
                "BTBaseKit": {
                    "name": "BTBaseKit",
                    "dir": "BTBaseKit",
                    "summary": "",
                    "description": "",
                    "podspec": "BTBaseKit.podspec",
                    "files": [],
                    "source_count": 0,
                    "apis": [
                        {
                            "kind": "method",
                            "name": "tm_clipImage",
                            "declaration": "+ (UIImage *)tm_clipImage:(UIImage *)orImage withRadius:(CGFloat)radius;",
                            "file": "BTBaseKit/Extensions/UIKit/UIImage+BTExtension.h",
                            "line": 67,
                            "comment": "",
                        },
                        {
                            "kind": "method",
                            "name": "tm_clipImage",
                            "declaration": "+ (UIImage*)tm_clipImage:(UIImage *)orImage WithRadius:(int)radius borderWidth:(CGFloat)borderWidth borderColor:(UIColor*)borderColor;",
                            "file": "BTBaseKit/Extensions/UIKit/UIImage+BTExtension.h",
                            "line": 65,
                            "comment": "",
                        },
                        {
                            "kind": "interface",
                            "name": "UIImage",
                            "declaration": "@interface UIImage (BTExtension)",
                            "file": "BTBaseKit/Extensions/UIKit/UIImage+BTExtension.h",
                            "line": 32,
                            "comment": "",
                        },
                    ],
                }
            }

        raw = s.search_component(keyword="clip", format="json", limit=2)
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        self.assertEqual(data["keyword"], "clip")
        self.assertIn("results", data)
        self.assertLessEqual(len(data["results"]), 2)
        self.assertTrue(data["truncated"], "limit=2 should cause truncation for 3+ hits")

        # Validate result item shape
        item = data["results"][0]
        for k in ("component", "kind", "name", "file", "line", "declaration", "comment_preview"):
            self.assertIn(k, item)

    def test_search_component_errors(self):
        s = self._server()

        self.assertIn("关键词不能为空", s.search_component(keyword=" "))
        self.assertIn("无效的 kind", s.search_component(keyword="x", kind="badkind"))
        self.assertIn("无效的 format", s.search_component(keyword="x", format="badfmt"))

        # JSON no-hit result should be ok=false and empty results.
        with s.INDEX_LOCK:
            s.INDEX = {
                "C": {"name": "C", "dir": "C", "podspec": "", "summary": "", "description": "", "files": [], "source_count": 0, "apis": []}
            }
        raw = s.search_component(keyword="notfound", format="json", limit=5)
        data = json.loads(raw)
        self.assertFalse(data["ok"])
        self.assertEqual(data["results"], [])


if __name__ == "__main__":
    unittest.main()
