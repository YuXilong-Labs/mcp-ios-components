import os
import tempfile
import unittest
import importlib
from unittest import mock


class TestAccessControlRuntime(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def _write_component(self, root, dirname, pod_name, extra_spec="", header="@interface Foo : NSObject\n@end\n"):
        comp = os.path.join(root, dirname)
        os.makedirs(os.path.join(comp, "Sources"), exist_ok=True)
        with open(os.path.join(comp, f"{pod_name}.podspec"), "w", encoding="utf-8") as f:
            f.write(
                "Pod::Spec.new do |s|\n"
                f"  s.name = '{pod_name}'\n"
                "  s.summary = 'sum'\n"
                f"  {extra_spec}\n"
                "end\n"
            )
        with open(os.path.join(comp, "Sources", "Foo.h"), "w", encoding="utf-8") as f:
            f.write(header)

    def test_discover_components_policy_and_mixup(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            self._write_component(d, "a", "AKit")
            self._write_component(d, "b", "BKit", "SUPPORT_MIXUP = ['VO']")
            self._write_component(d, "rtc", "BTRtcEngine")
            self._write_component(d, "c", "CryptoKit")

            ac = {
                "exclude_from_index": {"btrtcengine"},
                "api_only": {"cryptokit"},
                "config_path": "x",
            }
            comps, filtered_mixup, filtered_policy = s.discover_components(d, return_filtered=True, access_control=ac)
            self.assertIn("a", comps)
            self.assertIn("c", comps)
            self.assertNotIn("rtc", comps)
            self.assertIn("b", filtered_mixup)
            self.assertIn("rtc", filtered_policy)
            self.assertIn("c", filtered_policy)

    def test_discover_components_missing_dir_returns_triple(self):
        s = self._server()
        comps, filtered_mixup, filtered_policy = s.discover_components("/path/not/exist", return_filtered=True, access_control={"exclude_from_index": set(), "api_only": set()})
        self.assertEqual(comps, set())
        self.assertEqual(filtered_mixup, {})
        self.assertEqual(filtered_policy, {})

    def test_build_index_sets_access_mode(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            self._write_component(d, "ak", "AKit")
            self._write_component(d, "ck", "CryptoKit")
            ac = {
                "exclude_from_index": {"btrtcengine"},
                "api_only": {"cryptokit"},
                "config_path": "x",
            }
            with mock.patch.object(s, "load_access_control", return_value=ac):
                idx = s.build_index(d)

            self.assertEqual(idx["AKit"]["access_mode"], s.ACCESS_MODE_FULL)
            self.assertEqual(idx["CryptoKit"]["access_mode"], s.ACCESS_MODE_API_ONLY)

    def test_compute_hash_sensitive_to_access_control(self):
        s = self._server()
        with tempfile.TemporaryDirectory() as d:
            self._write_component(d, "ak", "AKit")
            components = {"ak"}
            h1 = s.compute_hash(d, components, {"exclude_from_index": {"btrtcengine"}, "api_only": set()})
            h2 = s.compute_hash(d, components, {"exclude_from_index": {"btrtcengine"}, "api_only": {"akit"}})
            self.assertNotEqual(h1, h2)

    def test_get_component_from_snapshot_and_is_api_only(self):
        s = self._server()

        snap = {
            "AKit": {"name": "AKit", "dir": "ak", "access_mode": s.ACCESS_MODE_FULL},
            "CryptoKit": {"name": "CryptoKit", "dir": "crypto", "access_mode": s.ACCESS_MODE_API_ONLY},
        }
        self.assertIsNone(s._get_component_from_snapshot(snap, ""))
        self.assertEqual(s._get_component_from_snapshot(snap, "crypto")["name"], "CryptoKit")
        self.assertTrue(s.is_api_only_component("CryptoKit", snap["CryptoKit"]))

        with s.INDEX_LOCK:
            s.INDEX = snap
        self.assertTrue(s.is_api_only_component("crypto"))
        self.assertFalse(s.is_api_only_component("AKit"))


if __name__ == "__main__":
    unittest.main()
