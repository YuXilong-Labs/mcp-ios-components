import unittest
import importlib


class TestComponentApiAndClassDetail(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_get_component_api_missing_and_empty(self):
        s = self._server()
        with s.INDEX_LOCK:
            s.INDEX = {"BTBaseKit": {"name": "BTBaseKit", "dir": "BTBaseKit", "summary": "", "description": "", "podspec": "", "files": [], "source_count": 0, "apis": []}}

        self.assertIn("不存在", s.get_component_api("Nope"))
        self.assertIn("未发现公开 API", s.get_component_api("BTBaseKit"))

    def test_get_component_api_truncation(self):
        s = self._server()

        # Monkeypatch output limit to keep test small.
        s.MAX_API_OUTPUT = 2

        apis = [
            {"kind": "method", "name": "m1", "declaration": "- (void)m1;", "file": "A.h", "line": 1, "comment": ""},
            {"kind": "method", "name": "m2", "declaration": "- (void)m2;", "file": "A.h", "line": 2, "comment": ""},
            {"kind": "method", "name": "m3", "declaration": "- (void)m3;", "file": "A.h", "line": 3, "comment": ""},
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
        self.assertIn("# BTBaseKit", out)
        self.assertIn("## A.h", out)
        self.assertIn("m1", out)
        self.assertIn("m2", out)
        self.assertNotIn("m3", out)
        self.assertIn("仅显示前", out)

    def test_get_class_detail_membership_by_file(self):
        s = self._server()

        apis = [
            {"kind": "interface", "name": "Foo", "declaration": "@interface Foo", "file": "Foo.h", "line": 10, "comment": ""},
            {"kind": "method", "name": "bar", "declaration": "- (void)bar;", "file": "Foo.h", "line": 20, "comment": ""},
            {"kind": "method", "name": "baz", "declaration": "- (void)baz;", "file": "Foo.m", "line": 30, "comment": ""},
            {"kind": "property", "name": "p", "declaration": "@property int p;", "file": "Foo.h", "line": 15, "comment": ""},
        ]

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
                    "apis": apis,
                }
            }

        out = s.get_class_detail("BTBaseKit", "Foo")
        self.assertIn("=== Foo (BTBaseKit) ===", out)
        self.assertIn("定义: Foo.h:10", out)
        self.assertIn("属性", out)
        self.assertIn("p", out)
        self.assertIn("公开方法", out)
        self.assertIn("bar", out)
        # baz is in a different file; current heuristic only groups members by definition file.
        self.assertNotIn("baz", out)

    def test_get_class_detail_not_found(self):
        s = self._server()
        with s.INDEX_LOCK:
            s.INDEX = {"BTBaseKit": {"name": "BTBaseKit", "dir": "BTBaseKit", "summary": "", "description": "", "podspec": "", "files": [], "source_count": 0, "apis": []}}

        out = s.get_class_detail("BTBaseKit", "Nope")
        self.assertIn("未找到类", out)

    def test_get_class_detail_missing_component_and_private_methods(self):
        s = self._server()
        out = s.get_class_detail("NoComp", "Foo")
        self.assertIn("不存在", out)

        apis = [
            {"kind": "class", "name": "Foo", "declaration": "class Foo", "file": "Foo.m", "line": 1, "comment": ""},
            {"kind": "func", "name": "inner", "declaration": "func inner()", "file": "Foo.m", "line": 2, "comment": ""},
        ]
        with s.INDEX_LOCK:
            s.INDEX = {
                "X": {
                    "name": "X",
                    "dir": "X",
                    "summary": "",
                    "description": "",
                    "podspec": "",
                    "files": [],
                    "source_count": 0,
                    "apis": apis,
                }
            }
        out2 = s.get_class_detail("X", "Foo")
        self.assertIn("内部方法", out2)


if __name__ == "__main__":
    unittest.main()
