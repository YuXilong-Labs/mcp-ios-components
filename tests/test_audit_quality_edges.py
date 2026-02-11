import json
import unittest
import importlib


class TestAuditQualityEdges(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_audit_invalid_format_and_empty_index(self):
        s = self._server()
        bad = s.audit_component_api_quality(format="bad")
        self.assertIn("无效的 format", bad)

        with s.INDEX_LOCK:
            s.INDEX = {}
        txt = s.audit_component_api_quality(format="text")
        self.assertIn("暂无索引数据", txt)
        raw = s.audit_component_api_quality(format="json")
        data = json.loads(raw)
        self.assertFalse(data["ok"])

    def test_audit_unknown_component_and_text_summary(self):
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
                    "apis": [
                        {"kind": "method", "name": "x", "declaration": "- (void)x;", "file": "A.h", "line": 1, "comment": ""},
                        {"kind": "method", "name": "todoFix", "declaration": "- (void)todoFix;", "file": "A.h", "line": 2, "comment": "comment"},
                    ],
                }
            }

        raw = s.audit_component_api_quality(component_name="Nope", format="json")
        data = json.loads(raw)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "unknown_component")

        txt = s.audit_component_api_quality(component_name="BTBaseKit", format="text", limit="bad")
        self.assertIn("missing_comment", txt)
        self.assertIn("suspicious_naming", txt)


if __name__ == "__main__":
    unittest.main()
