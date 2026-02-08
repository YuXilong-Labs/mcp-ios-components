import json
import os
import unittest
from pathlib import Path


class TestFixtures(unittest.TestCase):
    def test_audit_fixture_schema(self):
        fixture = Path(__file__).resolve().parent / "fixtures" / "audit_BTBaseKit.json"
        if not fixture.exists():
            self.skipTest("fixture missing")

        data = json.loads(fixture.read_text(encoding="utf-8"))

        self.assertIn("ok", data)
        # Some fixtures may be created with older versions; accept ok missing.
        if "ok" in data:
            self.assertTrue(data["ok"])

        for key in ("component", "missing_comment", "suspicious_naming", "counts", "limit"):
            self.assertIn(key, data)

        self.assertIsInstance(data["missing_comment"], list)
        self.assertIsInstance(data["suspicious_naming"], list)
        self.assertIsInstance(data["counts"], dict)


if __name__ == "__main__":
    unittest.main()
