import json
import unittest
import importlib


class TestGetToolDocs(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_get_tool_docs_json_all_and_single(self):
        s = self._server()

        raw = s.get_tool_docs(format="json")
        data = json.loads(raw)
        self.assertTrue(data["ok"])
        self.assertIn("tools", data)
        names = [t["name"] for t in data["tools"]]
        self.assertIn("search_component", names)
        self.assertIn("audit_component_api_quality", names)

        raw_one = s.get_tool_docs(tool_name="search_component", format="json")
        one = json.loads(raw_one)
        self.assertTrue(one["ok"])
        self.assertIn("tool", one)
        self.assertEqual(one["tool"]["name"], "search_component")
        self.assertIn("signature", one["tool"])

    def test_get_tool_docs_unknown_tool_json(self):
        s = self._server()

        raw = s.get_tool_docs(tool_name="nope", format="json")
        data = json.loads(raw)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"], "unknown_tool")


if __name__ == "__main__":
    unittest.main()
