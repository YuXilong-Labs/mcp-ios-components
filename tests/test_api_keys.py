import os
import tempfile
import unittest
import importlib
from unittest import mock


class TestApiKeys(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_hash_and_validate(self):
        s = self._server()
        h = s._hash_api_key("abc")
        self.assertEqual(len(h), 64)
        self.assertTrue(s.validate_api_key("abc", {h: "x"}))
        self.assertFalse(s.validate_api_key("bad", {h: "x"}))
        self.assertTrue(s.validate_api_key("", {}))

    def test_load_api_keys_from_env_and_file_formats(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            key_file = os.path.join(d, "keys.txt")
            raw = "rawkey"
            hashed = s._hash_api_key("hashedkey")
            with open(key_file, "w", encoding="utf-8") as f:
                f.write(f"alice:{raw}\n")
                f.write(f"bob:{hashed}\n")
                f.write(f"{hashed}\n")
                f.write("plainnohash\n")

            with mock.patch.dict(os.environ, {"MCP_API_KEYS": "k1,k2"}, clear=False):
                s.KEYS_FILE = key_file
                keys = s.load_api_keys()

            self.assertIn(s._hash_api_key("k1"), keys)
            self.assertIn(s._hash_api_key("k2"), keys)
            self.assertIn(s._hash_api_key(raw), keys)
            self.assertIn(hashed, keys)
            self.assertIn(s._hash_api_key("plainnohash"), keys)

    def test_generate_and_list_api_keys(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            key_file = os.path.join(d, ".api-keys")
            s.KEYS_FILE = key_file

            generated = s.generate_api_key("tester")
            self.assertTrue(generated.startswith("sk-btp-"))
            self.assertTrue(os.path.exists(key_file))

            listed = s.list_api_keys()
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["name"], "tester")

            # no file
            os.remove(key_file)
            self.assertEqual(s.list_api_keys(), [])


if __name__ == "__main__":
    unittest.main()
