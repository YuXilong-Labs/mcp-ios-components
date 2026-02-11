import os
import unittest
import importlib
from unittest import mock


class TestAccessControlConfig(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_resolve_config_path_and_normalize(self):
        s = self._server()

        rel = s._resolve_config_path("abc.yaml")
        self.assertTrue(rel.endswith("abc.yaml"))
        self.assertTrue(os.path.isabs(rel))

        abs_path = "/tmp/x.yaml"
        self.assertEqual(s._resolve_config_path(abs_path), abs_path)

        self.assertEqual(s.normalize_component_name("  BTBaseKit  "), "btbasekit")
        self.assertEqual(s.normalize_component_name(""), "")

    def test_extract_pod_name(self):
        s = self._server()
        content = "Pod::Spec.new do |s|\n  s.name = 'BTBaseKit'\nend\n"
        self.assertEqual(s._extract_pod_name_from_podspec_content(content, "fallback"), "BTBaseKit")
        self.assertEqual(s._extract_pod_name_from_podspec_content("", "fallback"), "fallback")

    def test_load_access_control_defaults(self):
        s = self._server()
        with mock.patch.object(s, "load_components_config", return_value={}):
            ac = s.load_access_control("")

        self.assertIn("btrtcengine", ac["exclude_from_index"])
        self.assertEqual(ac["api_only"], set())

    def test_load_access_control_merge_and_priority(self):
        s = self._server()
        cfg = {
            "access_control": {
                "exclude_from_index": ["BTRtcEngine", "  AA  "],
                "api_only": ["BTCryptoKit", "aa", "  BTEncryptKit  "],
            }
        }
        with mock.patch.object(s, "load_components_config", return_value=cfg):
            ac = s.load_access_control("components.yaml")

        # defaults + configured exclude
        self.assertIn("btrtcengine", ac["exclude_from_index"])
        self.assertIn("aa", ac["exclude_from_index"])
        # exclude wins over api_only
        self.assertNotIn("aa", ac["api_only"])
        self.assertIn("btcryptokit", ac["api_only"])
        self.assertIn("btencryptkit", ac["api_only"])

    def test_load_access_control_non_dict_or_bad_types(self):
        s = self._server()
        with mock.patch.object(s, "load_components_config", return_value={"access_control": "bad"}):
            ac = s.load_access_control("")
        self.assertIn("btrtcengine", ac["exclude_from_index"])
        self.assertEqual(ac["api_only"], set())


if __name__ == "__main__":
    unittest.main()
