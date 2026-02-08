import unittest


class TestHelpers(unittest.TestCase):
    def test_to_json_stable(self):
        # Import inside test to avoid importing MCP at collection time in other contexts.
        import mcp_server as s

        out = s._to_json({"b": 1, "a": 2})
        self.assertEqual(out, '{"a":2,"b":1}')

    def test_looks_suspicious_name(self):
        import mcp_server as s

        self.assertEqual(s._looks_suspicious_name(""), "empty")
        self.assertEqual(s._looks_suspicious_name("a"), "too_short")
        self.assertEqual(s._looks_suspicious_name("todoFix"), "placeholder")
        self.assertEqual(s._looks_suspicious_name("abc1"), "trailing_digits")
        # ObjC-style methods typically start with lowercase
        self.assertEqual(s._looks_suspicious_name("DoThing"), "starts_with_uppercase")
        # A normal looking name should pass
        self.assertEqual(s._looks_suspicious_name("tm_clipImage"), "")


if __name__ == "__main__":
    unittest.main()
