import json
import os
import tempfile
import unittest
import importlib
from unittest import mock


class TestLoadComponentsConfig(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_load_components_config_missing_yaml_json(self):
        s = self._server()
        self.assertEqual(s.load_components_config("/not/exist.yaml"), {})

        with tempfile.TemporaryDirectory() as d:
            j = os.path.join(d, "c.json")
            with open(j, "w", encoding="utf-8") as f:
                f.write(json.dumps({"components": {"A": {"repo": "x"}}}))
            out = s.load_components_config(j)
            self.assertIn("components", out)

            y = os.path.join(d, "c.yaml")
            with open(y, "w", encoding="utf-8") as f:
                f.write("components:\n  A:\n    repo: x\n")
            out2 = s.load_components_config(y)
            self.assertIn("components", out2)

    def test_load_components_config_yaml_importerror(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            y = os.path.join(d, "c.yaml")
            with open(y, "w", encoding="utf-8") as f:
                f.write("components:\n  A: x\n")

            real_import = __import__

            def fake_import(name, *args, **kwargs):
                if name == "yaml":
                    raise ImportError("no yaml")
                return real_import(name, *args, **kwargs)

            with mock.patch("builtins.__import__", side_effect=fake_import):
                out = s.load_components_config(y)
            self.assertEqual(out, {})


if __name__ == "__main__":
    unittest.main()
