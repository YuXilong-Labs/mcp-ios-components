import os
import tempfile
import unittest
import importlib


class TestDiscoverAndPodspec(unittest.TestCase):
    def _server(self):
        import mcp_server as s
        return importlib.reload(s)

    def test_discover_components_include_allowlist(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            # Create two components with minimal podspecs.
            os.makedirs(os.path.join(d, "FooKit"), exist_ok=True)
            with open(os.path.join(d, "FooKit", "FooKit.podspec"), "w", encoding="utf-8") as f:
                f.write("Pod::Spec.new do |s|\n  s.name = 'FooKit'\n  s.summary = 'foo'\nend\n")

            os.makedirs(os.path.join(d, "BarKit"), exist_ok=True)
            with open(os.path.join(d, "BarKit", "BarKit.podspec"), "w", encoding="utf-8") as f:
                f.write("Pod::Spec.new do |s|\n  s.name = 'BarKit'\n  s.summary = 'bar'\nend\n")

            os.environ["IOS_PODS_INCLUDE"] = "fookit"  # case-insensitive
            comps = s.discover_components(d)
            self.assertIn("FooKit", comps)
            self.assertNotIn("BarKit", comps)

        os.environ.pop("IOS_PODS_INCLUDE", None)

    def test_parse_podspec_fallback_and_name(self):
        s = self._server()

        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "btbasekit"), exist_ok=True)
            # Dir name != pod name; ensure .name is honored.
            with open(os.path.join(d, "btbasekit", "BTBaseKit.podspec"), "w", encoding="utf-8") as f:
                f.write("Pod::Spec.new do |s|\n  s.name = 'BTBaseKit'\n  s.summary = 'base'\n  s.description = 'desc'\nend\n")

            spec = s.parse_podspec(os.path.join(d, "btbasekit"), "btbasekit")
            self.assertEqual(spec.get("pod_name"), "BTBaseKit")
            self.assertEqual(spec.get("summary"), "base")
            self.assertEqual(spec.get("description"), "desc")
            self.assertTrue(spec.get("podspec"))


if __name__ == "__main__":
    unittest.main()
