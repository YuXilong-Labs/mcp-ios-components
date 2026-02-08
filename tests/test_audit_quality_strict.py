import json
import unittest
import importlib


class TestAuditQualityStrict(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_audit_quality_json_schema_and_reasons(self):
        s = self._server()

        # Seed a tiny index.
        apis = [
            {"kind": "method", "name": "a", "declaration": "- (void)a;", "file": "A.h", "line": 1, "comment": ""},
            {"kind": "method", "name": "todoFix", "declaration": "- (void)todoFix;", "file": "A.h", "line": 2, "comment": ""},
            {"kind": "method", "name": "goodName", "declaration": "- (void)goodName;", "file": "A.h", "line": 3, "comment": "some comment"},
        ]
        with s.INDEX_LOCK:
            s.INDEX = {"BTBaseKit": {"name": "BTBaseKit", "dir": "BTBaseKit", "summary": "", "description": "", "podspec": "", "files": [], "source_count": 0, "apis": apis}}

        raw = s.audit_component_api_quality(component_name="BTBaseKit", format="json", limit=50)
        data = json.loads(raw)

        self.assertTrue(data["ok"])
        for key in ("component", "limit", "rules", "missing_comment", "suspicious_naming", "counts"):
            self.assertIn(key, data)

        # Ensure each item has required keys.
        for item in data["missing_comment"]:
            for k in ("component", "kind", "name", "file", "line", "declaration"):
                self.assertIn(k, item)

        allowed = {"empty", "too_short", "too_generic", "trailing_digits", "placeholder", "starts_with_uppercase"}
        for item in data["suspicious_naming"]:
            self.assertIn("reason", item)
            self.assertIn(item["reason"], allowed)


if __name__ == "__main__":
    unittest.main()
