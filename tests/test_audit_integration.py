import os
import unittest
import importlib


class TestAuditIntegration(unittest.TestCase):
    def _load_server(self):
        # Ensure env is applied at import time.
        import mcp_server as s
        return importlib.reload(s)

    def test_audit_quality_schema(self):
        pods_dir = os.environ.get("IOS_PODS_DIR", "").strip()
        if not pods_dir or not os.path.isdir(pods_dir):
            self.skipTest("IOS_PODS_DIR not set or not found; skipping integration test")

        s = self._load_server()

        # Build index for the current pods_dir and load into global INDEX.
        s.PODS_DIR = pods_dir
        new_index = s.build_index(pods_dir)
        with s.INDEX_LOCK:
            s.INDEX = new_index

        # Audit should return stable JSON keys.
        include = os.environ.get("IOS_PODS_INCLUDE", "").strip()
        component = include.split(",")[0].strip() if include else ""
        raw = s.audit_component_api_quality(component_name=component, format="json", limit=20)

        data = s.json.loads(raw)
        self.assertTrue(data.get("ok"))
        self.assertIn("missing_comment", data)
        self.assertIn("suspicious_naming", data)
        self.assertIn("counts", data)


if __name__ == "__main__":
    unittest.main()
